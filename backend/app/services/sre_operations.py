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

    from app.services.backup_service import object_store_status

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


def emit_sre_alerts(actor_user_id: str, workspace_id: str, *, hours: int = 24) -> dict[str, Any]:
    status = capture_sre_snapshot(workspace_id, hours=hours)
    emitted = 0
    if status["alerts"]:
        from app.services.governed_actions import dispatch_event
        bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        for alert in status["alerts"]:
            event_id = hashlib.sha256(f"{workspace_id}:{alert['code']}:{bucket}".encode()).hexdigest()[:32]
            result = dispatch_event(
                actor_user_id,
                workspace_id,
                event_type="sre_slo_breach",
                event_id=event_id,
                payload={**alert, "workspace_id": workspace_id, "window_hours": hours},
                enqueue=True,
            )
            emitted += len(result.get("runs") or [])
    return {**status, "governed_action_runs": emitted}


def list_sre_snapshots(workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM sre_alert_snapshots WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(int(limit), 200))},
    )
    for row in rows:
        row["alerts"] = json_loads(row.pop("alerts_json", "[]"), [])
        row["error_budget"] = json_loads(row.pop("error_budget_json", "{}"), {})
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
