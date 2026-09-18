from __future__ import annotations

import time

from app.core.config import get_settings
from app.services.job_service import QUEUE_KEY, run_job, submit_job
from app.services.metadata_store import init_metadata_store, fetch_one
from app.services.connector_service import claim_due_schedules, get_source


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


def main():
    init_metadata_store()
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Le paquet redis est requis pour lancer le worker") from exc
    r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    print("DataVision worker ready", flush=True)
    next_scheduler_check = 0.0
    while True:
        try:
            now = time.monotonic()
            if now >= next_scheduler_check:
                _enqueue_due_refreshes()
                next_scheduler_check = now + 30.0
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
