from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sites() -> list[dict[str, Any]]:
    settings = get_settings()
    try:
        raw = json.loads(settings.multi_cluster_sites_json or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("MULTI_CLUSTER_SITES_JSON invalide") from exc
    if not isinstance(raw, list):
        raise RuntimeError("MULTI_CLUSTER_SITES_JSON doit être une liste")
    sites: list[dict[str, Any]] = []
    ids: set[str] = set()
    primary_count = 0
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RuntimeError(f"Cluster #{idx + 1} invalide")
        cluster_id = str(item.get("id") or "").strip()
        if not cluster_id or cluster_id in ids:
            raise RuntimeError("Chaque cluster doit avoir un id unique")
        ids.add(cluster_id)
        role = str(item.get("role") or "standby").strip().lower()
        if role not in {"primary", "standby"}:
            raise RuntimeError(f"Rôle invalide pour {cluster_id}")
        primary_count += int(role == "primary")
        sites.append({
            "id": cluster_id,
            "name": str(item.get("name") or cluster_id),
            "region": str(item.get("region") or "unknown"),
            "role": role,
            "enabled": bool(item.get("enabled", True)),
            "backup_target": str(item.get("backup_target") or cluster_id),
            "endpoint": str(item.get("endpoint") or ""),
        })
    if sites and primary_count != 1:
        raise RuntimeError("La topologie multi-cluster doit déclarer exactement un primary")
    return sites


def _site(cluster_id: str) -> dict[str, Any]:
    for site in _sites():
        if site["id"] == cluster_id:
            return site
    raise KeyError("Cluster introuvable")


def _configured_primary() -> str | None:
    return next((site["id"] for site in _sites() if site["role"] == "primary" and site["enabled"]), None)


def _active_cluster(workspace_id: str) -> str | None:
    row = fetch_one("SELECT active_cluster_id FROM cluster_control_state WHERE workspace_id=:ws", {"ws": workspace_id})
    return str(row["active_cluster_id"]) if row and row.get("active_cluster_id") else _configured_primary()


def _latest_verified_replication(target_name: str) -> dict[str, Any] | None:
    return fetch_one(
        "SELECT * FROM backup_replications WHERE target_name=:target AND verification_status='verified' "
        "ORDER BY verified_at DESC, completed_at DESC LIMIT 1",
        {"target": target_name},
    )


def cluster_topology_status(workspace_id: str) -> dict[str, Any]:
    settings = get_settings()
    sites = _sites()
    active = _active_cluster(workspace_id)
    enriched = []
    for site in sites:
        repl = _latest_verified_replication(site["backup_target"])
        enriched.append({
            **site,
            "active": site["id"] == active,
            "latest_verified_backup_at": repl.get("verified_at") if repl else None,
            "latest_verified_backup_id": repl.get("backup_id") if repl else None,
        })
    return {
        "workspace_id": workspace_id,
        "enabled": bool(settings.multi_cluster_failover_enabled),
        "executor": settings.multi_cluster_failover_executor,
        "configured_clusters": len(sites),
        "active_cluster_id": active,
        "clusters": enriched,
    }


def _replication_fresh(replication: dict[str, Any] | None) -> tuple[bool, float | None]:
    if not replication:
        return False, None
    dt = _parse_dt(replication.get("verified_at") or replication.get("completed_at"))
    if not dt:
        return False, None
    age = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
    return age <= get_settings().multi_cluster_backup_max_age_hours, round(age, 2)


def create_failover_plan(actor_user_id: str, workspace_id: str, *, target_cluster_id: str, reason: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.multi_cluster_failover_enabled:
        raise PermissionError("La bascule multi-cluster est désactivée")
    target = _site(target_cluster_id)
    if not target["enabled"]:
        raise PermissionError("Le cluster cible est désactivé")
    source = _active_cluster(workspace_id)
    if not source:
        raise RuntimeError("Aucun cluster primary actif n'est déterminable")
    if source == target_cluster_id:
        raise ValueError("Le cluster cible est déjà actif")
    replication = _latest_verified_replication(target["backup_target"])
    fresh, age_hours = _replication_fresh(replication)
    if settings.multi_cluster_require_verified_backup and not fresh:
        raise RuntimeError("Aucune réplication vérifiée et suffisamment récente n'est disponible dans la région cible")
    token = secrets.token_urlsafe(32)
    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(1, settings.multi_cluster_confirmation_ttl_minutes))
    checks = {
        "target_enabled": True,
        "verified_backup_required": bool(settings.multi_cluster_require_verified_backup),
        "verified_backup_present": bool(replication),
        "verified_backup_fresh": fresh,
        "verified_backup_age_hours": age_hours,
        "verified_backup_id": replication.get("backup_id") if replication else None,
        "target_region": target["region"],
    }
    execute(
        "INSERT INTO cluster_failover_events(id,workspace_id,source_cluster_id,target_cluster_id,status,reason,confirmation_token_hash,expires_at,executor_mode,result_json,created_by,created_at,confirmed_at) "
        "VALUES(:id,:ws,:source,:target,'planned',:reason,:token,:expires,:executor,:result,:user,:created,NULL)",
        {
            "id": plan_id, "ws": workspace_id, "source": source, "target": target_cluster_id,
            "reason": str(reason or "operational failover")[:1000], "token": hashlib.sha256(token.encode()).hexdigest(),
            "expires": expires.isoformat(), "executor": settings.multi_cluster_failover_executor,
            "result": json_dumps({"preflight": checks}), "user": actor_user_id, "created": now.isoformat(),
        },
    )
    return {
        "id": plan_id,
        "status": "planned",
        "workspace_id": workspace_id,
        "source_cluster_id": source,
        "target_cluster_id": target_cluster_id,
        "expires_at": expires.isoformat(),
        "confirmation_token": token,
        "confirmation_required": True,
        "executor": settings.multi_cluster_failover_executor,
        "preflight": checks,
    }


def _execute_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.multi_cluster_failover_webhook_url or not settings.multi_cluster_failover_webhook_secret:
        raise RuntimeError("Le webhook de bascule n'est pas configuré")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(settings.multi_cluster_failover_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    import httpx
    headers = {"content-type": "application/json", "x-datavision-signature": f"sha256={signature}"}
    try:
        from app.services.trace_context import current_trace_context
        trace = current_trace_context()
        if trace:
            headers["traceparent"] = trace.traceparent
            headers["x-request-id"] = trace.request_id
    except Exception:
        pass
    response = httpx.post(
        settings.multi_cluster_failover_webhook_url,
        content=raw,
        headers=headers,
        timeout=max(2, settings.multi_cluster_failover_webhook_timeout_seconds),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Webhook de bascule en échec ({response.status_code}): {response.text[:300]}")
    return {"delivery": "webhook", "status_code": response.status_code}


def confirm_failover(actor_user_id: str, workspace_id: str, *, plan_id: str, confirmation_token: str) -> dict[str, Any]:
    settings = get_settings()
    row = fetch_one("SELECT * FROM cluster_failover_events WHERE id=:id AND workspace_id=:ws", {"id": plan_id, "ws": workspace_id})
    if not row:
        raise KeyError("Plan de bascule introuvable")
    if row.get("status") != "planned":
        raise ValueError("Ce plan n'est plus confirmable")
    expires = _parse_dt(row.get("expires_at"))
    if not expires or expires < datetime.now(timezone.utc):
        execute("UPDATE cluster_failover_events SET status='expired' WHERE id=:id", {"id": plan_id})
        raise PermissionError("Le jeton de confirmation a expiré")
    supplied = hashlib.sha256(str(confirmation_token).encode()).hexdigest()
    if not hmac.compare_digest(str(row.get("confirmation_token_hash") or ""), supplied):
        raise PermissionError("Jeton de confirmation invalide")
    payload = {
        "event_id": plan_id,
        "workspace_id": workspace_id,
        "source_cluster_id": row["source_cluster_id"],
        "target_cluster_id": row["target_cluster_id"],
        "reason": row.get("reason"),
        "requested_by": row.get("created_by"),
        "confirmed_by": actor_user_id,
        "confirmed_at": utcnow(),
    }
    executor = str(row.get("executor_mode") or settings.multi_cluster_failover_executor)
    if executor == "webhook":
        execution = _execute_webhook(payload)
        traffic_switched = True
    elif executor == "control_plane_only":
        execution = {"delivery": "control_plane_only", "external_traffic_switch_required": True}
        traffic_switched = False
    else:
        raise RuntimeError("MULTI_CLUSTER_FAILOVER_EXECUTOR invalide")
    existing = fetch_one("SELECT workspace_id FROM cluster_control_state WHERE workspace_id=:ws", {"ws": workspace_id})
    if existing:
        execute(
            "UPDATE cluster_control_state SET active_cluster_id=:cluster,updated_at=:updated,updated_by=:user WHERE workspace_id=:ws",
            {"cluster": row["target_cluster_id"], "updated": utcnow(), "user": actor_user_id, "ws": workspace_id},
        )
    else:
        execute(
            "INSERT INTO cluster_control_state(workspace_id,active_cluster_id,updated_at,updated_by) VALUES(:ws,:cluster,:updated,:user)",
            {"ws": workspace_id, "cluster": row["target_cluster_id"], "updated": utcnow(), "user": actor_user_id},
        )
    result = {**json_loads(row.get("result_json") or "{}", {}), "execution": execution, "traffic_switched": traffic_switched}
    execute(
        "UPDATE cluster_failover_events SET status='confirmed',result_json=:result,confirmed_at=:confirmed WHERE id=:id",
        {"result": json_dumps(result), "confirmed": utcnow(), "id": plan_id},
    )
    return {"id": plan_id, "status": "confirmed", **payload, "executor": executor, **result}


def list_failovers(workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id,workspace_id,source_cluster_id,target_cluster_id,status,reason,expires_at,executor_mode,result_json,created_by,created_at,confirmed_at "
        "FROM cluster_failover_events WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(int(limit), 200))},
    )
    for row in rows:
        row["result"] = json_loads(row.pop("result_json", "{}"), {})
    return rows
