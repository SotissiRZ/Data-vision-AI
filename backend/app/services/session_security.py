from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.services.audit_service import record_event
from app.services.metadata_store import execute, fetch_all, fetch_one, utcnow


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _ensure_tables() -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS organization_security_policies (
            organization_id TEXT PRIMARY KEY,
            idle_timeout_minutes INTEGER NOT NULL,
            max_session_hours INTEGER NOT NULL,
            max_active_sessions INTEGER NOT NULL,
            trusted_device_days INTEGER NOT NULL,
            require_managed_device INTEGER NOT NULL DEFAULT 0,
            updated_by TEXT,
            updated_at TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS auth_session_posture (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_hash TEXT NOT NULL,
            device_label TEXT,
            mfa_verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS auth_trusted_devices (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            device_hash TEXT NOT NULL,
            label TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            trusted_until TEXT NOT NULL,
            revoked_at TEXT,
            UNIQUE(organization_id,user_id,device_hash)
        )"""
    )


def _device_hash(user_agent: str = "", device_label: str = "") -> str:
    material = f"{(user_agent or '').strip().lower()}\n{(device_label or '').strip().lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def default_policy() -> dict[str, Any]:
    cfg = get_settings()
    return {
        "idle_timeout_minutes": max(5, int(cfg.session_idle_minutes)),
        "max_session_hours": max(1, int(cfg.session_max_hours)),
        "max_active_sessions": max(1, int(cfg.session_max_active_per_user)),
        "trusted_device_days": max(1, int(cfg.trusted_device_days)),
        "require_managed_device": bool(cfg.managed_device_default_required),
    }


def _org_admin(actor_id: str, organization_id: str) -> None:
    row = fetch_one(
        "SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user",
        {"org": organization_id, "user": actor_id},
    )
    if not row or row.get("role") not in {"owner", "admin"}:
        raise PermissionError("Administration de l’organisation requise.")


def get_organization_security_policy(organization_id: str) -> dict[str, Any]:
    _ensure_tables()
    row = fetch_one(
        "SELECT * FROM organization_security_policies WHERE organization_id=:org",
        {"org": organization_id},
    )
    out = default_policy()
    out.update(row or {})
    out["organization_id"] = organization_id
    out["require_managed_device"] = bool(out.get("require_managed_device"))
    out["source"] = "organization" if row else "defaults"
    return out


def save_organization_security_policy(
    actor_id: str,
    organization_id: str,
    *,
    idle_timeout_minutes: int,
    max_session_hours: int,
    max_active_sessions: int,
    trusted_device_days: int,
    require_managed_device: bool,
) -> dict[str, Any]:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    policy = {
        "idle_timeout_minutes": max(5, min(int(idle_timeout_minutes), 10080)),
        "max_session_hours": max(1, min(int(max_session_hours), 24 * 90)),
        "max_active_sessions": max(1, min(int(max_active_sessions), 100)),
        "trusted_device_days": max(1, min(int(trusted_device_days), 365)),
        "require_managed_device": bool(require_managed_device),
    }
    now = utcnow()
    existing = fetch_one(
        "SELECT organization_id FROM organization_security_policies WHERE organization_id=:org",
        {"org": organization_id},
    )
    params = {"org": organization_id, "actor": actor_id, "now": now, **policy, "managed": 1 if policy["require_managed_device"] else 0}
    if existing:
        execute(
            """UPDATE organization_security_policies SET idle_timeout_minutes=:idle_timeout_minutes,
               max_session_hours=:max_session_hours,max_active_sessions=:max_active_sessions,
               trusted_device_days=:trusted_device_days,require_managed_device=:managed,
               updated_by=:actor,updated_at=:now WHERE organization_id=:org""",
            params,
        )
    else:
        execute(
            """INSERT INTO organization_security_policies(
               organization_id,idle_timeout_minutes,max_session_hours,max_active_sessions,
               trusted_device_days,require_managed_device,updated_by,updated_at
               ) VALUES(:org,:idle_timeout_minutes,:max_session_hours,:max_active_sessions,
               :trusted_device_days,:managed,:actor,:now)""",
            params,
        )
    record_event(
        "security.session_policy_updated",
        user_id=actor_id,
        organization_id=organization_id,
        resource_type="organization_security_policy",
        resource_id=organization_id,
        payload=policy,
    )
    return get_organization_security_policy(organization_id)


def _effective_user_policy(user_id: str) -> dict[str, Any]:
    _ensure_tables()
    orgs = fetch_all(
        "SELECT organization_id FROM organization_members WHERE user_id=:user",
        {"user": user_id},
    )
    policies = [get_organization_security_policy(str(x["organization_id"])) for x in orgs]
    if not policies:
        return {**default_policy(), "organization_ids": []}
    return {
        "idle_timeout_minutes": min(int(p["idle_timeout_minutes"]) for p in policies),
        "max_session_hours": min(int(p["max_session_hours"]) for p in policies),
        "max_active_sessions": min(int(p["max_active_sessions"]) for p in policies),
        "trusted_device_days": min(int(p["trusted_device_days"]) for p in policies),
        "require_managed_device": any(bool(p["require_managed_device"]) for p in policies),
        "organization_ids": [str(p["organization_id"]) for p in policies],
    }


def _device_is_trusted(user_id: str, device_hash: str, organization_ids: list[str]) -> bool:
    if not organization_ids:
        return True
    now = datetime.now(timezone.utc)
    for organization_id in organization_ids:
        policy = get_organization_security_policy(organization_id)
        if not policy["require_managed_device"]:
            continue
        row = fetch_one(
            """SELECT trusted_until,revoked_at FROM auth_trusted_devices
               WHERE organization_id=:org AND user_id=:user AND device_hash=:hash""",
            {"org": organization_id, "user": user_id, "hash": device_hash},
        )
        expiry = _parse_dt(row.get("trusted_until") if row else None)
        if not row or row.get("revoked_at") or not expiry or expiry <= now:
            return False
    return True


def register_session_posture(
    user_id: str,
    session_id: str,
    *,
    user_agent: str = "",
    device_label: str = "",
    mfa_verified: bool = False,
) -> dict[str, Any]:
    _ensure_tables()
    policy = _effective_user_policy(user_id)
    device_hash = _device_hash(user_agent, device_label)
    if policy["require_managed_device"] and not _device_is_trusted(user_id, device_hash, list(policy["organization_ids"])):
        raise PermissionError("Cet appareil n’est pas approuvé par la politique de l’organisation.")
    execute(
        """INSERT INTO auth_session_posture(session_id,user_id,device_hash,device_label,mfa_verified,created_at)
           VALUES(:session,:user,:hash,:label,:mfa,:now)""",
        {
            "session": session_id,
            "user": user_id,
            "hash": device_hash,
            "label": (device_label or "")[:160],
            "mfa": 1 if mfa_verified else 0,
            "now": utcnow(),
        },
    )
    active = fetch_all(
        "SELECT id,created_at FROM auth_sessions WHERE user_id=:user AND revoked_at IS NULL ORDER BY created_at DESC",
        {"user": user_id},
    )
    limit = int(policy["max_active_sessions"])
    for stale in active[limit:]:
        execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": stale["id"]})
    return {"device_hash": device_hash, "policy": policy}


def validate_session_security(user_id: str, session_id: str, session_row: dict[str, Any]) -> dict[str, Any]:
    _ensure_tables()
    policy = _effective_user_policy(user_id)
    now = datetime.now(timezone.utc)
    last_seen = _parse_dt(session_row.get("last_seen_at"))
    created = _parse_dt(session_row.get("created_at"))
    if last_seen and last_seen + timedelta(minutes=int(policy["idle_timeout_minutes"])) <= now:
        execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": session_id})
        raise ValueError("Session expirée après inactivité")
    if created and created + timedelta(hours=int(policy["max_session_hours"])) <= now:
        execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": session_id})
        raise ValueError("Durée maximale de session dépassée")
    posture = fetch_one("SELECT * FROM auth_session_posture WHERE session_id=:id", {"id": session_id})
    if posture and policy["require_managed_device"]:
        if not _device_is_trusted(user_id, str(posture["device_hash"]), list(policy["organization_ids"])):
            execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": session_id})
            raise ValueError("Appareil non approuvé")
    return {"policy": policy, "posture": posture}


def list_trusted_devices(actor_id: str, organization_id: str) -> list[dict[str, Any]]:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    rows = fetch_all(
        """SELECT d.id,d.user_id,u.email,d.label,d.first_seen_at,d.last_seen_at,d.trusted_until,d.revoked_at
           FROM auth_trusted_devices d JOIN users u ON u.id=d.user_id
           WHERE d.organization_id=:org ORDER BY d.last_seen_at DESC""",
        {"org": organization_id},
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        expiry = _parse_dt(row.get("trusted_until"))
        row["active"] = not bool(row.get("revoked_at")) and bool(expiry and expiry > now)
    return rows


def trust_session_device(actor_id: str, organization_id: str, session_id: str, *, label: str = "") -> dict[str, Any]:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    posture = fetch_one("SELECT * FROM auth_session_posture WHERE session_id=:id", {"id": session_id})
    if not posture:
        raise KeyError("Posture de session introuvable.")
    membership = fetch_one(
        "SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user",
        {"org": organization_id, "user": posture["user_id"]},
    )
    if not membership:
        raise PermissionError("La session n’appartient pas à cette organisation.")
    policy = get_organization_security_policy(organization_id)
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=int(policy["trusted_device_days"]))
    existing = fetch_one(
        "SELECT id FROM auth_trusted_devices WHERE organization_id=:org AND user_id=:user AND device_hash=:hash",
        {"org": organization_id, "user": posture["user_id"], "hash": posture["device_hash"]},
    )
    device_id = str(existing["id"]) if existing else str(uuid.uuid4())
    params = {
        "id": device_id,
        "org": organization_id,
        "user": posture["user_id"],
        "hash": posture["device_hash"],
        "label": (label or posture.get("device_label") or "Appareil approuvé")[:160],
        "now": now.isoformat(),
        "until": until.isoformat(),
    }
    if existing:
        execute(
            """UPDATE auth_trusted_devices SET label=:label,last_seen_at=:now,trusted_until=:until,revoked_at=NULL
               WHERE id=:id""",
            params,
        )
    else:
        execute(
            """INSERT INTO auth_trusted_devices(id,organization_id,user_id,device_hash,label,first_seen_at,last_seen_at,trusted_until,revoked_at)
               VALUES(:id,:org,:user,:hash,:label,:now,:now,:until,NULL)""",
            params,
        )
    record_event(
        "security.device_trusted",
        user_id=actor_id,
        organization_id=organization_id,
        resource_type="trusted_device",
        resource_id=device_id,
        payload={"session_id": session_id, "subject_user_id": posture["user_id"]},
    )
    return {**params, "active": True}


def revoke_trusted_device(actor_id: str, organization_id: str, device_id: str) -> None:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    row = fetch_one(
        "SELECT id,user_id,device_hash FROM auth_trusted_devices WHERE id=:id AND organization_id=:org",
        {"id": device_id, "org": organization_id},
    )
    if not row:
        raise KeyError("Appareil approuvé introuvable.")
    execute("UPDATE auth_trusted_devices SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": device_id})
    sessions = fetch_all(
        """SELECT p.session_id FROM auth_session_posture p JOIN auth_sessions s ON s.id=p.session_id
           WHERE p.user_id=:user AND p.device_hash=:hash AND s.revoked_at IS NULL""",
        {"user": row["user_id"], "hash": row["device_hash"]},
    )
    for item in sessions:
        execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": item["session_id"]})
    record_event(
        "security.device_revoked",
        user_id=actor_id,
        organization_id=organization_id,
        resource_type="trusted_device",
        resource_id=device_id,
    )


def internal_metrics_token_valid(value: str) -> bool:
    expected = str(get_settings().otel_internal_metrics_token or "")
    if not expected:
        return get_settings().app_env != "production" and not value
    if expected.startswith("change-this-"):
        return get_settings().app_env != "production" and (not value or hmac.compare_digest(expected, value))
    return hmac.compare_digest(expected, value or "")
