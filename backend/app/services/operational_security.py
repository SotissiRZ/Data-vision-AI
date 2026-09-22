from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.services.audit_service import record_event
from app.services.identity_service import list_secrets, rotate_secret
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

PRODUCT_VERSION = "2.69.0"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){1,3}", value.strip()):
        raise ValueError("Version de release invalide")
    return tuple(int(part) for part in value.split("."))


def _redacted_rotation_policy(item: dict[str, Any]) -> dict[str, Any]:
    reference = dict(item.get("reference") or {})
    rotation = dict(reference.get("rotation") or {})
    mode = str(rotation.get("mode") or "manual").lower()
    days = max(1, min(3650, int(rotation.get("days") or get_settings().secret_rotation_default_days)))
    latest = item.get("latest_version") or {}
    created = _parse_dt(latest.get("created_at"))
    due_at = created + timedelta(days=days) if created else None
    now = datetime.now(timezone.utc)
    eligible = item.get("provider") == "local_encrypted" and mode == "generated"
    return {
        "secret_id": item.get("id"),
        "workspace_id": item.get("workspace_id"),
        "name": item.get("name"),
        "provider": item.get("provider"),
        "mode": mode,
        "days": days,
        "eligible_for_automatic_rotation": eligible,
        "current_version": int(item.get("current_version") or 0),
        "last_rotated_at": latest.get("created_at"),
        "due_at": due_at.isoformat() if due_at else None,
        "due": bool(eligible and due_at and due_at <= now),
    }


def secret_rotation_status(workspace_id: str | None = None) -> dict[str, Any]:
    if workspace_id:
        workspace_ids = [workspace_id]
    else:
        workspace_ids = [str(r["id"]) for r in fetch_all("SELECT id FROM workspaces ORDER BY id")]
    items: list[dict[str, Any]] = []
    for ws in workspace_ids:
        items.extend(_redacted_rotation_policy(item) for item in list_secrets(ws))
    due = [item for item in items if item["due"]]
    return {
        "enabled": bool(get_settings().secret_auto_rotation_enabled),
        "workspace_id": workspace_id,
        "secret_count": len(items),
        "automatic_eligible_count": sum(1 for item in items if item["eligible_for_automatic_rotation"]),
        "due_count": len(due),
        "secrets": items,
    }


def rotate_due_secrets(actor_id: str, *, workspace_id: str | None = None, confirm: bool = False) -> dict[str, Any]:
    status = secret_rotation_status(workspace_id)
    due = [item for item in status["secrets"] if item["due"]]
    if confirm and not get_settings().secret_auto_rotation_enabled:
        raise PermissionError("La rotation automatique des secrets est désactivée")
    results: list[dict[str, Any]] = []
    for item in due:
        event_id = str(uuid.uuid4())
        if not confirm:
            results.append({"secret_id": item["secret_id"], "workspace_id": item["workspace_id"], "status": "planned", "due_at": item["due_at"]})
            continue
        generated = secrets.token_urlsafe(max(16, int(get_settings().secret_rotation_generated_bytes)))
        try:
            rotated = rotate_secret(actor_id, str(item["workspace_id"]), str(item["secret_id"]), value=generated)
            new_version = int(rotated.get("current_version") or 0)
            execute(
                """INSERT INTO secret_rotation_events(id,workspace_id,secret_id,status,previous_version,new_version,due_at,created_by,created_at,details_json)
                   VALUES(:id,:ws,:secret,'rotated',:previous,:new,:due,:actor,:now,:details)""",
                {"id": event_id, "ws": item["workspace_id"], "secret": item["secret_id"], "previous": item["current_version"], "new": new_version,
                 "due": item["due_at"], "actor": actor_id, "now": utcnow(), "details": json_dumps({"mode": "generated", "provider": item["provider"]})},
            )
            record_event("secret.auto_rotate", user_id=actor_id, workspace_id=str(item["workspace_id"]), resource_type="secret", resource_id=str(item["secret_id"]), payload={"previous_version": item["current_version"], "new_version": new_version})
            results.append({"secret_id": item["secret_id"], "workspace_id": item["workspace_id"], "status": "rotated", "new_version": new_version})
        except Exception as exc:
            execute(
                """INSERT INTO secret_rotation_events(id,workspace_id,secret_id,status,previous_version,new_version,due_at,created_by,created_at,details_json)
                   VALUES(:id,:ws,:secret,'failed',:previous,NULL,:due,:actor,:now,:details)""",
                {"id": event_id, "ws": item["workspace_id"], "secret": item["secret_id"], "previous": item["current_version"], "due": item["due_at"],
                 "actor": actor_id, "now": utcnow(), "details": json_dumps({"error": type(exc).__name__})},
            )
            results.append({"secret_id": item["secret_id"], "workspace_id": item["workspace_id"], "status": "failed", "error": type(exc).__name__})
    return {"confirmed": confirm, "due_count": len(due), "results": results}


def list_secret_rotation_events(workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM secret_rotation_events WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(500, int(limit)))},
    )
    out = []
    for row in rows:
        item = dict(row)
        item["details"] = json_loads(item.pop("details_json", "{}"), {})
        out.append(item)
    return out


def _rollback_webhook_url() -> str:
    url = get_settings().release_rollback_webhook_url.strip()
    if not url:
        raise RuntimeError("RELEASE_ROLLBACK_WEBHOOK_URL non configurée")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Le webhook de rollback doit être une URL HTTPS sans credentials intégrés")
    return url


def create_rollback_plan(actor_id: str, *, target_version: str, reason: str, artifact_sha256: str = "", current_version: str = PRODUCT_VERSION) -> dict[str, Any]:
    settings = get_settings()
    if not settings.release_rollback_enabled:
        raise PermissionError("Le rollback de release est désactivé")
    current = _version_tuple(current_version)
    target = _version_tuple(target_version)
    if target >= current:
        raise ValueError("Le rollback exige une version cible strictement antérieure")
    if artifact_sha256 and not re.fullmatch(r"[a-fA-F0-9]{64}", artifact_sha256):
        raise ValueError("SHA-256 d'artefact invalide")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(2, settings.release_rollback_confirmation_ttl_minutes))
    plan_id = str(uuid.uuid4())
    execute(
        """INSERT INTO release_rollback_events(id,current_version,target_version,status,reason,confirmation_token_hash,expires_at,executor_mode,artifact_sha256,result_json,created_by,created_at)
           VALUES(:id,:current,:target,'planned',:reason,:token,:expires,:mode,:sha,:result,:actor,:now)""",
        {"id": plan_id, "current": current_version, "target": target_version, "reason": reason.strip(), "token": token_hash,
         "expires": expires.isoformat(), "mode": settings.release_rollback_executor, "sha": artifact_sha256.lower(), "result": "{}", "actor": actor_id, "now": now.isoformat()},
    )
    record_event("release.rollback.plan", user_id=actor_id, resource_type="release", resource_id=plan_id, payload={"current_version": current_version, "target_version": target_version, "executor_mode": settings.release_rollback_executor})
    return {"plan_id": plan_id, "current_version": current_version, "target_version": target_version, "expires_at": expires.isoformat(), "executor_mode": settings.release_rollback_executor, "confirmation_token": token}


def confirm_rollback(actor_id: str, *, plan_id: str, confirmation_token: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM release_rollback_events WHERE id=:id", {"id": plan_id})
    if not row:
        raise KeyError("Plan de rollback introuvable")
    if row.get("status") != "planned":
        raise ValueError("Ce plan de rollback n'est plus confirmable")
    expires = _parse_dt(row.get("expires_at"))
    if not expires or expires <= datetime.now(timezone.utc):
        execute("UPDATE release_rollback_events SET status='expired' WHERE id=:id", {"id": plan_id})
        raise ValueError("Plan de rollback expiré")
    candidate = hashlib.sha256(confirmation_token.encode()).hexdigest()
    if not hmac.compare_digest(candidate, str(row["confirmation_token_hash"])):
        raise PermissionError("Jeton de confirmation invalide")
    mode = str(row.get("executor_mode") or "plan_only")
    result: dict[str, Any]
    if mode == "plan_only":
        result = {"executed": False, "message": "Plan confirmé. Exécution externe/manuelle requise.", "target_version": row["target_version"]}
        status = "confirmed_manual"
    elif mode == "webhook":
        url = _rollback_webhook_url()
        body_obj = {"event": "datavision.release.rollback", "plan_id": plan_id, "current_version": row["current_version"], "target_version": row["target_version"], "artifact_sha256": row.get("artifact_sha256") or "", "reason": row.get("reason") or ""}
        body = json.dumps(body_obj, separators=(",", ":"), sort_keys=True).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "DataVision-Rollback/2.63"}
        secret = get_settings().release_rollback_webhook_secret
        if secret:
            headers["X-DataVision-Signature-SHA256"] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with httpx.Client(timeout=max(2, get_settings().release_rollback_timeout_seconds), follow_redirects=False) as client:
            response = client.post(url, content=body, headers=headers)
            response.raise_for_status()
        result = {"executed": True, "status_code": response.status_code, "target_version": row["target_version"]}
        status = "executed"
    else:
        raise ValueError("Mode d'exécution rollback non supporté")
    now = utcnow()
    execute("UPDATE release_rollback_events SET status=:status,result_json=:result,confirmed_at=:now WHERE id=:id", {"status": status, "result": json_dumps(result), "now": now, "id": plan_id})
    record_event("release.rollback.confirm", user_id=actor_id, resource_type="release", resource_id=plan_id, payload={"status": status, "target_version": row["target_version"]})
    return {"plan_id": plan_id, "status": status, "result": result, "confirmed_at": now}


def rollback_drill(actor_id: str, *, target_version: str, artifact_sha256: str = "", current_version: str = PRODUCT_VERSION) -> dict[str, Any]:
    target = _version_tuple(target_version)
    current = _version_tuple(current_version)
    checks = {
        "target_is_older": target < current,
        "artifact_sha256_valid": (not artifact_sha256) or bool(re.fullmatch(r"[a-fA-F0-9]{64}", artifact_sha256)),
        "executor_mode_valid": get_settings().release_rollback_executor in {"plan_only", "webhook"},
        "webhook_configured_if_required": get_settings().release_rollback_executor != "webhook" or bool(get_settings().release_rollback_webhook_url.strip()),
    }
    ok = all(checks.values())
    record_event("release.rollback.drill", user_id=actor_id, resource_type="release", resource_id=target_version, outcome="success" if ok else "failed", payload=checks)
    return {"status": "passed" if ok else "failed", "current_version": current_version, "target_version": target_version, "checks": checks, "executed": False}
