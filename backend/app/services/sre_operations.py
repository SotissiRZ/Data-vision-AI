from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.services.job_service import queue_status, submit_job
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow
from app.services.operational_intelligence import operational_overview


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _age_hours(value: str | None) -> float | None:
    dt = _parse_dt(value)
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)


def _latest_backup() -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id,status,kind,archive_path,sha256,database_backend,size_bytes,started_at,completed_at,details_json "
        "FROM backup_runs ORDER BY started_at DESC LIMIT 1"
    )
    if not row:
        return None
    row["details"] = json_loads(row.pop("details_json", "{}"), {})
    row["age_hours"] = round(_age_hours(row.get("completed_at") or row.get("started_at")) or 0.0, 2)
    return row


def _latest_restore_drill() -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id,backup_id,status,archive_sha256,checks_json,started_at,completed_at FROM restore_drills "
        "ORDER BY started_at DESC LIMIT 1"
    )
    if not row:
        return None
    row["checks"] = json_loads(row.pop("checks_json", "{}"), {})
    row["age_hours"] = round(_age_hours(row.get("completed_at") or row.get("started_at")) or 0.0, 2)
    return row


def _error_budget(availability: float | None, target: float, hours: int) -> dict[str, Any]:
    window_minutes = max(1.0, float(hours) * 60.0)
    allowed = window_minutes * max(0.0, 1.0 - target / 100.0)
    if availability is None:
        return {
            "target_pct": target,
            "window_hours": hours,
            "allowed_bad_minutes": round(allowed, 2),
            "consumed_bad_minutes": None,
            "remaining_bad_minutes": round(allowed, 2),
            "burn_rate": None,
        }
    consumed = window_minutes * max(0.0, 1.0 - float(availability) / 100.0)
    remaining = allowed - consumed
    return {
        "target_pct": target,
        "window_hours": hours,
        "allowed_bad_minutes": round(allowed, 2),
        "consumed_bad_minutes": round(consumed, 2),
        "remaining_bad_minutes": round(remaining, 2),
        "burn_rate": round(consumed / allowed, 3) if allowed > 0 else None,
    }


def _alert(code: str, severity: str, title: str, detail: str, observed: Any = None, target: Any = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "detail": detail,
        "observed": observed,
        "target": target,
    }


def sre_status(workspace_id: str, *, hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(int(hours), 24 * 30))
    settings = get_settings()
    overview = operational_overview(workspace_id, hours=hours)
    queue = queue_status()
    backup = _latest_backup()
    drill = _latest_restore_drill()
    alerts: list[dict[str, Any]] = []

    indicators = overview.get("slo", {}).get("indicators", {})
    availability = indicators.get("api_availability", {})
    latency = indicators.get("api_p95_latency", {})
    jobs = indicators.get("job_success", {})
    refresh = indicators.get("refresh_success", {})

    if availability.get("value") is not None and not availability.get("met"):
        value = float(availability["value"])
        target = float(availability.get("target") or 99.0)
        alerts.append(_alert("api_availability", "critical" if value < target - 1.0 else "high", "Disponibilité API sous le SLO", f"{value:.3f}% sur {hours} h", value, target))
    if latency.get("value") is not None and not latency.get("met"):
        alerts.append(_alert("api_p95_latency", "high", "Latence API P95 au-dessus du SLO", f"{float(latency['value']):.0f} ms", latency["value"], latency.get("target")))
    if jobs.get("value") is not None and not jobs.get("met"):
        alerts.append(_alert("job_success", "high", "Taux de succès des jobs dégradé", f"{float(jobs['value']):.2f}%", jobs["value"], jobs.get("target")))
    if refresh.get("value") is not None and not refresh.get("met"):
        alerts.append(_alert("refresh_success", "medium", "Taux de succès des refresh dégradé", f"{float(refresh['value']):.2f}%", refresh["value"], refresh.get("target")))

    queue_depth = queue.get("queue_depth")
    if queue.get("available") and queue_depth is not None and int(queue_depth) >= settings.sre_queue_alert_depth:
        severity = "high" if int(queue_depth) >= settings.sre_queue_alert_depth * 3 else "medium"
        alerts.append(_alert("queue_backlog", severity, "File de jobs en backlog", f"{queue_depth} jobs en attente", int(queue_depth), settings.sre_queue_alert_depth))
    if not queue.get("available"):
        alerts.append(_alert("queue_unavailable", "critical", "Redis / file de jobs indisponible", str(queue.get("error") or "Redis ne répond pas")))

    backup_age = backup.get("age_hours") if backup else None
    if not backup or backup.get("status") != "completed":
        alerts.append(_alert("backup_missing", "high", "Sauvegarde récente absente", "Aucune sauvegarde complète récente n'est disponible"))
    elif backup_age is not None and float(backup_age) > settings.sre_backup_max_age_hours:
        alerts.append(_alert("backup_stale", "high", "Sauvegarde trop ancienne", f"Dernière sauvegarde il y a {float(backup_age):.1f} h", backup_age, settings.sre_backup_max_age_hours))

    drill_age = drill.get("age_hours") if drill else None
    max_drill_age = settings.sre_restore_drill_max_age_hours
    if not drill or drill.get("status") != "passed":
        alerts.append(_alert("restore_drill_missing", "medium", "Test de restauration non validé", "Aucun restore drill récent n'est validé"))
    elif drill_age is not None and float(drill_age) > max_drill_age:
        alerts.append(_alert("restore_drill_stale", "medium", "Test de restauration trop ancien", f"Dernier test il y a {float(drill_age):.1f} h", drill_age, max_drill_age))

    target = float(availability.get("target") or 99.0)
    budget = _error_budget(availability.get("value"), target, hours)
    if budget.get("burn_rate") is not None and float(budget["burn_rate"]) >= settings.sre_error_budget_burn_alert:
        alerts.append(_alert("error_budget_burn", "critical", "Budget d'erreur consommé trop vite", f"Burn rate {float(budget['burn_rate']):.2f}×", budget["burn_rate"], settings.sre_error_budget_burn_alert))

    from app.services.backup_service import object_store_status, replication_targets_status

    result = {
        "workspace_id": workspace_id,
        "window_hours": hours,
        "status": "critical" if any(a["severity"] == "critical" for a in alerts) else ("attention" if alerts else "healthy"),
        "alerts": alerts,
        "error_budget": budget,
        "queue": queue,
        "backup": backup,
        "restore_drill": drill,
        "object_store": object_store_status(),
        "replication": replication_targets_status(),
        "alert_routes": {"configured": len(list_sre_alert_routes(workspace_id))},
        "multi_cluster": __import__("app.services.multi_cluster", fromlist=["cluster_topology_status"]).cluster_topology_status(workspace_id),
        "autoscaling": {
            "worker_mode": settings.sre_worker_autoscaling_mode,
            "queue_name": "datavision:jobs",
            "queue_alert_depth": settings.sre_queue_alert_depth,
        },
        "chaos": {
            "enabled": settings.sre_chaos_enabled,
            "max_probe_jobs": settings.sre_chaos_max_probe_jobs,
        },
    }
    return result


def capture_sre_snapshot(workspace_id: str, *, hours: int = 24) -> dict[str, Any]:
    status = sre_status(workspace_id, hours=hours)
    snapshot_id = str(uuid.uuid4())
    execute(
        "INSERT INTO sre_alert_snapshots(id,workspace_id,status,alerts_json,error_budget_json,created_at) "
        "VALUES(:id,:ws,:status,:alerts,:budget,:created)",
        {
            "id": snapshot_id,
            "ws": workspace_id,
            "status": status["status"],
            "alerts": json_dumps(status["alerts"]),
            "budget": json_dumps(status["error_budget"]),
            "created": utcnow(),
        },
    )
    status["snapshot_id"] = snapshot_id
    return status


def _severity_rank(value: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(str(value).lower(), 2)


def list_sre_alert_routes(workspace_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM sre_alert_routes WHERE workspace_id=:ws ORDER BY name,id",
        {"ws": workspace_id},
    )
    for row in rows:
        row["enabled"] = bool(row.get("enabled"))
        row["route"] = json_loads(row.pop("route_json", "{}"), {})
    return rows


def save_sre_alert_route(
    workspace_id: str,
    *,
    name: str,
    min_severity: str = "medium",
    event_type: str = "sre_slo_breach",
    enabled: bool = True,
    codes: list[str] | None = None,
    route_id: str | None = None,
) -> dict[str, Any]:
    severity = str(min_severity).lower()
    if severity not in {"info", "low", "medium", "high", "critical"}:
        raise ValueError("min_severity invalide")
    event_type = str(event_type or "sre_slo_breach").strip()
    if not event_type or len(event_type) > 120:
        raise ValueError("event_type invalide")
    clean_codes = sorted({str(code).strip() for code in (codes or []) if str(code).strip()})
    now = utcnow()
    route_id = route_id or str(uuid.uuid4())
    existing = fetch_one("SELECT id FROM sre_alert_routes WHERE id=:id AND workspace_id=:ws", {"id": route_id, "ws": workspace_id})
    payload = json_dumps({"codes": clean_codes})
    if existing:
        execute(
            "UPDATE sre_alert_routes SET name=:name,enabled=:enabled,min_severity=:severity,event_type=:event,route_json=:route,updated_at=:updated WHERE id=:id AND workspace_id=:ws",
            {"name": name.strip()[:180], "enabled": 1 if enabled else 0, "severity": severity, "event": event_type, "route": payload, "updated": now, "id": route_id, "ws": workspace_id},
        )
    else:
        execute(
            "INSERT INTO sre_alert_routes(id,workspace_id,name,enabled,min_severity,event_type,route_json,created_at,updated_at) VALUES(:id,:ws,:name,:enabled,:severity,:event,:route,:created,:updated)",
            {"id": route_id, "ws": workspace_id, "name": name.strip()[:180], "enabled": 1 if enabled else 0, "severity": severity, "event": event_type, "route": payload, "created": now, "updated": now},
        )
    return next(route for route in list_sre_alert_routes(workspace_id) if route["id"] == route_id)


def delete_sre_alert_route(workspace_id: str, route_id: str) -> bool:
    row = fetch_one("SELECT id FROM sre_alert_routes WHERE id=:id AND workspace_id=:ws", {"id": route_id, "ws": workspace_id})
    if not row:
        return False
    execute("DELETE FROM sre_alert_routes WHERE id=:id AND workspace_id=:ws", {"id": route_id, "ws": workspace_id})
    return True


def _matching_routes(workspace_id: str, alert: dict[str, Any]) -> list[dict[str, Any]]:
    routes = [route for route in list_sre_alert_routes(workspace_id) if route.get("enabled")]
    if not routes:
        return [{"id": "default", "name": "Default", "min_severity": get_settings().sre_default_alert_route_min_severity, "event_type": "sre_slo_breach", "route": {"codes": []}}]
    result = []
    for route in routes:
        if _severity_rank(alert.get("severity", "medium")) < _severity_rank(route.get("min_severity", "medium")):
            continue
        codes = set((route.get("route") or {}).get("codes") or [])
        if codes and alert.get("code") not in codes:
            continue
        result.append(route)
    return result


def emit_sre_alerts(actor_user_id: str, workspace_id: str, *, hours: int = 24) -> dict[str, Any]:
    status = capture_sre_snapshot(workspace_id, hours=hours)
    emitted = 0
    routed = 0
    if status["alerts"]:
        from app.services.governed_actions import dispatch_event
        bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        for alert in status["alerts"]:
            for route in _matching_routes(workspace_id, alert):
                event_id = hashlib.sha256(f"{workspace_id}:{route['id']}:{alert['code']}:{bucket}".encode()).hexdigest()[:32]
                result = dispatch_event(
                    actor_user_id,
                    workspace_id,
                    event_type=str(route.get("event_type") or "sre_slo_breach"),
                    event_id=event_id,
                    payload={**alert, "workspace_id": workspace_id, "window_hours": hours, "sre_route_id": route["id"], "sre_route_name": route.get("name")},
                    enqueue=True,
                )
                emitted += len(result.get("runs") or [])
                routed += 1
    return {**status, "governed_action_runs": emitted, "routed_alert_events": routed}


def list_sre_snapshots(workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM sre_alert_snapshots WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(int(limit), 200))},
    )
    for row in rows:
        row["alerts"] = json_loads(row.pop("alerts_json", "[]"), [])
        row["error_budget"] = json_loads(row.pop("error_budget_json", "{}"), {})
    return rows



def _dependency_loss_checks() -> dict[str, Any]:
    settings = get_settings()
    queue = queue_status()
    return {
        "mode": "non_destructive_fault_model",
        "redis": {
            "currently_available": bool(queue.get("available")),
            "expected_when_unavailable": "critical_alert_queue_unavailable",
            "worker_recovery": "redis_blpop_retry_loop",
        },
        "object_store": {
            "primary": "local_backup_retained_when_remote_upload_fails",
            "replication": "per_target_failure_isolated_and_audited",
        },
        "database": {
            "readiness_policy": "schema_migrations_must_be_ready",
            "backup_policy": "pg_dump_required" if settings.backup_require_database_dump else "best_effort",
        },
    }


def run_dr_drill(actor_user_id: str, workspace_id: str, *, organization_id: str | None = None, mode: str = "continuity") -> dict[str, Any]:
    settings = get_settings()
    if not settings.sre_dr_enabled:
        raise PermissionError("Les exercices DR orchestrés sont désactivés. Activez SRE_DR_ENABLED explicitement.")
    allowed = {item.strip().lower() for item in settings.sre_dr_allowed_envs.split(",") if item.strip()}
    if settings.app_env.strip().lower() not in allowed:
        raise PermissionError(f"Exercice DR interdit dans APP_ENV={settings.app_env}")
    if mode not in {"continuity", "restore_only"}:
        raise ValueError("Mode DR non supporté")
    drill_id = str(uuid.uuid4())
    started = utcnow()
    execute(
        "INSERT INTO dr_drills(id,workspace_id,status,mode,checks_json,created_by,started_at,completed_at) VALUES(:id,:ws,'running',:mode,:checks,:user,:started,NULL)",
        {"id": drill_id, "ws": workspace_id, "mode": mode, "checks": "{}", "user": actor_user_id, "started": started},
    )
    checks: dict[str, Any] = {}
    try:
        from app.services.backup_service import latest_backup_archive, run_restore_drill, replication_targets_status, list_backup_replications
        restore = run_restore_drill(latest_backup_archive())
        checks["restore_drill"] = restore
        checks["replication_targets"] = replication_targets_status()
        checks["recent_replications"] = list_backup_replications(backup_id=restore.get("backup_id"), limit=50)
        if mode == "continuity" and settings.sre_dr_include_dependency_loss_checks:
            checks["dependency_loss"] = _dependency_loss_checks()
            probe = submit_job(
                user_id=actor_user_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                job_type="sre_probe",
                dataset_id=None,
                payload={"drill_id": drill_id, "sequence": 1, "scenario": "dependency_recovery_path"},
                max_retries=0,
            )
            checks["recovery_probe_job_id"] = probe["id"]
        execute(
            "UPDATE dr_drills SET status='passed',checks_json=:checks,completed_at=:completed WHERE id=:id",
            {"checks": json_dumps(checks), "completed": utcnow(), "id": drill_id},
        )
        return {"id": drill_id, "status": "passed", "mode": mode, "checks": checks}
    except Exception as exc:
        checks["error"] = str(exc)
        execute(
            "UPDATE dr_drills SET status='failed',checks_json=:checks,completed_at=:completed WHERE id=:id",
            {"checks": json_dumps(checks), "completed": utcnow(), "id": drill_id},
        )
        raise


def list_dr_drills(workspace_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM dr_drills WHERE workspace_id=:ws ORDER BY started_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(int(limit), 100))},
    )
    for row in rows:
        row["checks"] = json_loads(row.pop("checks_json", "{}"), {})
    return rows


def run_chaos_drill(actor_user_id: str, workspace_id: str, *, scenario: str, intensity: int = 5, organization_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.sre_chaos_enabled:
        raise PermissionError("Les exercices de chaos sont désactivés. Activez SRE_CHAOS_ENABLED explicitement.")
    if scenario not in {"queue_backlog", "readiness_snapshot"}:
        raise ValueError("Scénario de chaos non supporté")
    drill_id = str(uuid.uuid4())
    started = utcnow()
    result: dict[str, Any]
    if scenario == "queue_backlog":
        count = max(1, min(int(intensity), settings.sre_chaos_max_probe_jobs))
        jobs = [
            submit_job(
                user_id=actor_user_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                job_type="sre_probe",
                dataset_id=None,
                payload={"drill_id": drill_id, "sequence": idx + 1},
                max_retries=0,
            )
            for idx in range(count)
        ]
        result = {"scenario": scenario, "probe_jobs": [job["id"] for job in jobs], "count": count}
    else:
        result = {"scenario": scenario, "sre_status": sre_status(workspace_id, hours=1)}
    execute(
        "INSERT INTO chaos_drills(id,workspace_id,scenario,status,intensity,result_json,created_by,started_at,completed_at) "
        "VALUES(:id,:ws,:scenario,'completed',:intensity,:result,:user,:started,:completed)",
        {
            "id": drill_id,
            "ws": workspace_id,
            "scenario": scenario,
            "intensity": max(1, int(intensity)),
            "result": json_dumps(result),
            "user": actor_user_id,
            "started": started,
            "completed": utcnow(),
        },
    )
    return {"id": drill_id, "status": "completed", **result}


def list_chaos_drills(workspace_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM chaos_drills WHERE workspace_id=:ws ORDER BY started_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(int(limit), 100))},
    )
    for row in rows:
        row["result"] = json_loads(row.pop("result_json", "{}"), {})
    return rows
