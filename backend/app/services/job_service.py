from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any


from app.core.config import get_settings
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

QUEUE_KEY = "datavision:jobs"
RETRY_QUEUE_KEY = "datavision:jobs:retry"


def _redis():
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Le paquet redis n'est pas installé dans cet environnement") from exc
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)


def queue_status() -> dict[str, Any]:
    try:
        r = _redis()
        ok = bool(r.ping())
        depth = int(r.llen(QUEUE_KEY)) if ok else None
        return {"available": ok, "queue_depth": depth, "backend": "redis"}
    except Exception as exc:
        return {"available": False, "queue_depth": None, "backend": "redis", "error": str(exc)}


def submit_job(*, user_id: str, organization_id: str | None, workspace_id: str | None, job_type: str, dataset_id: str | None, payload: dict[str, Any], max_retries: int = 2, retry_backoff_seconds: int = 15) -> dict[str, Any]:
    if job_type not in {"automl", "ai_analysis", "forecast", "report", "proactive_scan", "connector_refresh", "action_delivery"}:
        raise ValueError("Type de job non supporté")
    max_retries = max(0, min(int(max_retries), 5))
    retry_backoff_seconds = max(1, min(int(retry_backoff_seconds), 3600))
    job_payload = dict(payload or {})
    job_payload["_job_options"] = {"max_retries": max_retries, "retry_backoff_seconds": retry_backoff_seconds}
    job_id = str(uuid.uuid4()); now = utcnow()
    execute("""INSERT INTO jobs(id,organization_id,workspace_id,user_id,job_type,status,progress,dataset_id,payload_json,created_at,cancel_requested)
             VALUES(:id,:org,:ws,:user,:type,'queued',0,:ds,:payload,:created,0)""",
            {"id": job_id, "org": organization_id, "ws": workspace_id, "user": user_id, "type": job_type, "ds": dataset_id, "payload": json_dumps(job_payload), "created": now})
    try:
        _redis().rpush(QUEUE_KEY, job_id)
    except Exception as exc:
        execute("UPDATE jobs SET status='failed',error=:error,finished_at=:finished WHERE id=:id", {"error": f"Redis indisponible: {exc}", "finished": utcnow(), "id": job_id})
        raise RuntimeError("Redis est indisponible; le job n'a pas été mis en file.") from exc
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM jobs WHERE id=:id", {"id": job_id})
    if not row:
        raise KeyError("Job introuvable")
    row["payload"] = json_loads(row.pop("payload_json", "{}"), {})
    row["result"] = json_loads(row.pop("result_json", None), None)
    row["cancel_requested"] = bool(row.get("cancel_requested"))
    return row


def list_jobs(user_id: str, workspace_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"user": user_id, "limit": max(1, min(limit, 500))}
    where = "user_id=:user"
    if workspace_id:
        where += " AND workspace_id=:ws"; params["ws"] = workspace_id
    rows = fetch_all(f"SELECT * FROM jobs WHERE {where} ORDER BY created_at DESC LIMIT :limit", params)
    for row in rows:
        row["payload"] = json_loads(row.pop("payload_json", "{}"), {})
        row["result"] = json_loads(row.pop("result_json", None), None)
        row["cancel_requested"] = bool(row.get("cancel_requested"))
    return rows


def request_cancel(job_id: str, user_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT user_id,status FROM jobs WHERE id=:id", {"id": job_id})
    if not row: raise KeyError("Job introuvable")
    if row["user_id"] != user_id: raise PermissionError("Vous ne pouvez pas annuler ce job.")
    if row["status"] in {"completed", "failed", "cancelled"}: return get_job(job_id)
    immediate = row["status"] in {"queued", "retry_wait"}
    execute("UPDATE jobs SET cancel_requested=1,status=:status,finished_at=CASE WHEN :immediate=1 THEN :finished ELSE finished_at END WHERE id=:id", {"status": "cancelled" if immediate else "cancel_requested", "immediate": 1 if immediate else 0, "finished": utcnow(), "id": job_id})
    if immediate:
        try: _redis().zrem(RETRY_QUEUE_KEY, job_id)
        except Exception: pass
    return get_job(job_id)


def _update(job_id: str, **fields: Any) -> None:
    if not fields: return
    parts=[]; params={"id":job_id}
    for key,value in fields.items():
        parts.append(f"{key}=:{key}"); params[key]=value
    execute(f"UPDATE jobs SET {', '.join(parts)} WHERE id=:id", params)


def _attempt_number(job_id: str) -> int:
    row = fetch_one("SELECT COUNT(*) AS n FROM job_attempts WHERE job_id=:job", {"job": job_id})
    return int(row.get("n") or 0) + 1 if row else 1


def _start_attempt(job_id: str) -> tuple[str, int, float]:
    attempt_id = str(uuid.uuid4())
    number = _attempt_number(job_id)
    execute("INSERT INTO job_attempts(id,job_id,attempt_number,status,started_at) VALUES(:id,:job,:n,'running',:started)", {"id": attempt_id, "job": job_id, "n": number, "started": utcnow()})
    return attempt_id, number, time.perf_counter()


def _finish_attempt(attempt_id: str, status: str, started_perf: float, *, error: str | None = None, scheduled_retry_at: str | None = None) -> float:
    latency = (time.perf_counter() - started_perf) * 1000.0
    execute("UPDATE job_attempts SET status=:status,error=:error,latency_ms=:latency,scheduled_retry_at=:retry,finished_at=:finished WHERE id=:id", {"status": status, "error": error, "latency": latency, "retry": scheduled_retry_at, "finished": utcnow(), "id": attempt_id})
    return latency


def enqueue_due_retries(now_ts: float | None = None, limit: int = 100) -> int:
    """Move retry-wait jobs whose backoff expired back to the main Redis queue.

    Uses a sorted set so retries do not block a worker thread while waiting.
    """
    now_ts = float(now_ts if now_ts is not None else time.time())
    try:
        r = _redis()
        ids = r.zrangebyscore(RETRY_QUEUE_KEY, 0, now_ts, start=0, num=max(1, min(limit, 1000)))
        moved = 0
        for job_id in ids:
            if r.zrem(RETRY_QUEUE_KEY, job_id):
                current = get_job(job_id)
                if current.get("cancel_requested") or current.get("status") == "cancelled":
                    continue
                _update(job_id, status="queued", progress=0)
                r.rpush(QUEUE_KEY, job_id)
                moved += 1
        return moved
    except Exception:
        return 0


def _retry_policy(job: dict[str, Any]) -> tuple[int, int]:
    opts = (job.get("payload") or {}).get("_job_options") or {}
    return max(0, min(int(opts.get("max_retries", 2)), 5)), max(1, min(int(opts.get("retry_backoff_seconds", 15)), 3600))


def _schedule_retry(job: dict[str, Any], attempt_number: int, exc: Exception) -> tuple[bool, str | None]:
    max_retries, base = _retry_policy(job)
    # attempt 1 + max_retries additional attempts
    if attempt_number > max_retries:
        return False, None
    delay = min(3600, base * (2 ** max(0, attempt_number - 1)))
    due_ts = time.time() + delay
    due_iso = datetime.fromtimestamp(due_ts, timezone.utc).isoformat()
    try:
        _redis().zadd(RETRY_QUEUE_KEY, {job["id"]: due_ts})
        _update(job["id"], status="retry_wait", progress=0, error=f"{exc} | retry {attempt_number}/{max_retries} planifié dans {delay}s")
        return True, due_iso
    except Exception:
        return False, None


def run_job(job_id: str) -> dict[str, Any]:
    from app.services.storage import load_dataframe, get_meta
    from app.services.modeling import automl_train
    from app.services.ai_analyst import AnalystContext, analyze_dataset
    from app.services.analysis_history import save_analysis
    from app.services.semantic_layer import get_semantic_model
    from app.services.forecasting import forecast_series
    from app.services.report_builder import build_report
    from app.services.proactive_intelligence import scan as proactive_scan
    from app.services.connector_service import refresh_source as connector_refresh
    from app.services.auth_service import has_permission
    from app.services.governed_actions import execute_action_run

    job = get_job(job_id)
    if job["cancel_requested"] or job["status"] == "cancelled":
        _update(job_id, status="cancelled", finished_at=utcnow())
        return get_job(job_id)
    _update(job_id, status="running", progress=5, started_at=utcnow(), error=None)
    attempt_id, attempt_number, attempt_started = _start_attempt(job_id)
    payload = dict(job["payload"] or {})
    payload.pop("_job_options", None)
    dataset_id = job.get("dataset_id")
    access_token = None
    try:
        from app.services.tenant_access import context_for_job, set_access_context, reset_access_context, authorize_dataset
        access_ctx = context_for_job(job["user_id"], job.get("workspace_id"))
        access_token = set_access_context(access_ctx)
        if access_ctx:
            if job["job_type"] == "connector_refresh":
                if not has_permission(access_ctx.user_id, access_ctx.workspace_id, "refresh:run"):
                    raise PermissionError("Permission insuffisante: refresh:run")
                if dataset_id:
                    authorize_dataset(dataset_id, "dataset:write", access_ctx)
            elif dataset_id:
                required = "model:run" if job["job_type"] == "automl" else "analysis:run"
                authorize_dataset(dataset_id, required, access_ctx)
        if job["job_type"] == "automl":
            if not dataset_id:
                raise ValueError("dataset_id requis pour AutoML")
            _update(job_id, progress=15)
            df = load_dataframe(dataset_id)
            meta = get_meta(dataset_id)
            context = {
                "id": meta["id"], "name": meta["original_name"], "format": meta["extension"],
                "version": meta.get("version", 1), "parent_id": meta.get("parent_id"),
                "root_id": meta.get("root_id", meta["id"]), "operation": meta.get("operation"),
            }
            result = automl_train(df, dataset_context=context, **payload)
        elif job["job_type"] == "ai_analysis":
            if not dataset_id:
                raise ValueError("dataset_id requis pour AI Analyst")
            _update(job_id, progress=15)
            df = load_dataframe(dataset_id)
            meta = get_meta(dataset_id)
            dataset = {
                "id": meta["id"], "name": meta["original_name"], "format": meta["extension"],
                "version": meta.get("version", 1), "parent_id": meta.get("parent_id"),
                "root_id": meta.get("root_id", meta["id"]), "operation": meta.get("operation"),
            }
            ctx = AnalystContext(
                dataset=dataset,
                question=str(payload.get("question", "Analyse ce dataset")),
                target=payload.get("target"),
                date_column=payload.get("date_column"),
                variables=payload.get("variables", []),
                group=payload.get("group"),
                horizon=int(payload.get("horizon", 12)),
                mode=str(payload.get("mode", "auto")),
                semantic_model=get_semantic_model(dataset_id, df),
            )
            result = analyze_dataset(df, ctx)
            save_analysis(result)
        elif job["job_type"] == "forecast":
            if not dataset_id:
                raise ValueError("dataset_id requis pour le forecasting")
            _update(job_id, progress=15)
            df = load_dataframe(dataset_id)
            result = forecast_series(df, **payload)
        elif job["job_type"] == "report":
            if not dataset_id:
                raise ValueError("dataset_id requis pour le rapport")
            _update(job_id, progress=15)
            result = build_report(dataset_id, **payload)
        elif job["job_type"] == "proactive_scan":
            if not dataset_id:
                raise ValueError("dataset_id requis pour le scan proactif")
            _update(job_id, progress=15)
            df = load_dataframe(dataset_id)
            result = proactive_scan(dataset_id, df, payload.get("watch_ids") or None, bool(payload.get("auto_configure", True)))
        elif job["job_type"] == "connector_refresh":
            if not job.get("workspace_id"):
                raise ValueError("workspace_id requis pour le refresh connecteur")
            source_id = str(payload.get("source_id") or "")
            if not source_id:
                raise ValueError("source_id requis pour le refresh connecteur")
            _update(job_id, progress=15)
            result = connector_refresh(job["workspace_id"], source_id, actor_id=job["user_id"], trigger=str(payload.get("trigger") or "manual"), job_id=job_id)
        elif job["job_type"] == "action_delivery":
            if not job.get("workspace_id"):
                raise ValueError("workspace_id requis pour une action gouvernée")
            if not has_permission(access_ctx.user_id, access_ctx.workspace_id, "actions:trigger") if access_ctx else False:
                raise PermissionError("Permission insuffisante: actions:trigger")
            action_run_id = str(payload.get("action_run_id") or "")
            if not action_run_id:
                raise ValueError("action_run_id requis")
            action_row = fetch_one("SELECT workspace_id FROM action_runs WHERE id=:id", {"id": action_run_id})
            if not action_row or str(action_row.get("workspace_id")) != str(job.get("workspace_id")):
                raise PermissionError("Action hors du workspace du job")
            _update(job_id, progress=20)
            result = execute_action_run(action_run_id)
        else:
            raise ValueError("Type de job non supporté")
        current = get_job(job_id)
        if current["cancel_requested"]:
            _update(job_id, status="cancelled", progress=100, finished_at=utcnow())
            latency = _finish_attempt(attempt_id, "cancelled", attempt_started)
            telemetry_status = "cancelled"
        else:
            _update(job_id, status="completed", progress=100, result_json=json_dumps(result), finished_at=utcnow())
            latency = _finish_attempt(attempt_id, "completed", attempt_started)
            telemetry_status = "completed"
        try:
            from app.services.operational_intelligence import record_telemetry
            record_telemetry(event_kind="job", name=job["job_type"], status=telemetry_status, workspace_id=job.get("workspace_id"), organization_id=job.get("organization_id"), user_id=job.get("user_id"), feature="Background Jobs", latency_ms=latency, resource_type="job", resource_id=job_id, metadata={"attempt": attempt_number, "dataset_id": dataset_id})
        except Exception:
            pass
    except Exception as exc:
        latest = get_job(job_id)
        scheduled, retry_at = _schedule_retry(latest, attempt_number, exc) if not latest.get("cancel_requested") else (False, None)
        if scheduled:
            latency = _finish_attempt(attempt_id, "retry_wait", attempt_started, error=str(exc), scheduled_retry_at=retry_at)
        else:
            _update(job_id, status="failed", error=str(exc), finished_at=utcnow())
            latency = _finish_attempt(attempt_id, "failed", attempt_started, error=str(exc))
        try:
            from app.services.operational_intelligence import record_telemetry
            record_telemetry(event_kind="job", name=job["job_type"], status="retry_wait" if scheduled else "failed", workspace_id=job.get("workspace_id"), organization_id=job.get("organization_id"), user_id=job.get("user_id"), feature="Background Jobs", latency_ms=latency, resource_type="job", resource_id=job_id, metadata={"attempt": attempt_number, "dataset_id": dataset_id, "error": str(exc), "scheduled_retry_at": retry_at})
        except Exception:
            pass
    finally:
        if access_token is not None:
            try:
                reset_access_context(access_token)
            except Exception:
                pass
    return get_job(job_id)

