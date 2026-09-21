from __future__ import annotations

import time

from app.core.config import get_settings
from app.services.job_service import QUEUE_KEY, run_job, submit_job, enqueue_due_retries
from app.services.metadata_store import init_metadata_store, fetch_one, fetch_all
from app.services.connector_service import claim_due_schedules, get_source
from app.services.governed_actions import process_due_runs
from app.services.model_registry import LOCAL_ACTOR, LOCAL_WORKSPACE, claim_due_monitor_schedules


def _enqueue_due_refreshes() -> None:
    """Claim due schedules atomically and enqueue tenant-aware connector refresh jobs."""
    for schedule in claim_due_schedules(limit=20):
        try:
            ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": schedule["workspace_id"]})
            source = get_source(schedule["workspace_id"], schedule["source_id"])
            submit_job(
                user_id=schedule["created_by"],
                organization_id=ws.get("organization_id") if ws else None,
                workspace_id=schedule["workspace_id"],
                job_type="connector_refresh",
                dataset_id=source.get("dataset_id"),
                payload={"source_id": schedule["source_id"], "trigger": "scheduled", "schedule_id": schedule["id"]},
            )
        except Exception as exc:
            print(f"Refresh scheduler error for {schedule.get('source_id')}: {exc}", flush=True)



def _enqueue_due_model_monitors() -> None:
    for schedule in claim_due_monitor_schedules(limit=20):
        try:
            is_local = schedule["workspace_id"] == LOCAL_WORKSPACE
            ws = None if is_local else fetch_one(
                "SELECT organization_id FROM workspaces WHERE id=:id",
                {"id": schedule["workspace_id"]},
            )
            submit_job(
                user_id=LOCAL_ACTOR if is_local else schedule["created_by"],
                organization_id=ws.get("organization_id") if ws else None,
                workspace_id=None if is_local else schedule["workspace_id"],
                job_type="model_monitor",
                dataset_id=schedule["current_dataset_id"],
                payload={
                    "model_id": schedule["model_id"],
                    "current_dataset_id": schedule["current_dataset_id"],
                    "policy": schedule.get("policy") or {},
                    "trigger": "scheduled",
                    "schedule_id": schedule["id"],
                },
            )
        except Exception as exc:
            print(
                f"Model monitor scheduler error for {schedule.get('model_id')}: {exc}",
                flush=True,
            )



def _run_sre_sweep() -> None:
    settings = get_settings()
    if not settings.sre_auto_alerts_enabled:
        return
    from app.services.sre_operations import emit_sre_alerts

    rows = fetch_all(
        """SELECT w.id AS workspace_id,w.organization_id,wm.user_id
           FROM workspaces w
           JOIN workspace_members wm ON wm.workspace_id=w.id
           WHERE wm.role IN ('owner','admin')
           ORDER BY CASE wm.role WHEN 'owner' THEN 0 ELSE 1 END"""
    )
    seen: set[str] = set()
    for row in rows:
        workspace_id = str(row["workspace_id"])
        if workspace_id in seen:
            continue
        seen.add(workspace_id)
        try:
            emit_sre_alerts(str(row["user_id"]), workspace_id, hours=1)
        except Exception as exc:
            print(f"SRE sweep error for {workspace_id}: {exc}", flush=True)

def main():
    init_metadata_store()
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Le paquet redis est requis pour lancer le worker") from exc
    r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    print("DataVision worker ready", flush=True)
    next_scheduler_check = 0.0
    next_sre_check = 0.0
    while True:
        try:
            now = time.monotonic()
            if now >= next_scheduler_check:
                _enqueue_due_refreshes()
                _enqueue_due_model_monitors()
                enqueue_due_retries()
                process_due_runs()
                next_scheduler_check = now + 30.0
            if now >= next_sre_check:
                _run_sre_sweep()
                next_sre_check = now + max(60, get_settings().sre_check_interval_seconds)
            item = r.blpop(QUEUE_KEY, timeout=5)
            if not item:
                continue
            _, job_id = item
            print(f"Running job {job_id}", flush=True)
            run_job(job_id)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Worker error: {exc}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
