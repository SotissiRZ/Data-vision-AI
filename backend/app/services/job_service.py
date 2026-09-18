from __future__ import annotations

import json
import uuid
from typing import Any


from app.core.config import get_settings
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

QUEUE_KEY = "datavision:jobs"


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


def submit_job(*, user_id: str, organization_id: str | None, workspace_id: str | None, job_type: str, dataset_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    if job_type not in {"automl", "ai_analysis", "forecast", "report", "proactive_scan"}:
        raise ValueError("Type de job non supporté")
    job_id = str(uuid.uuid4()); now = utcnow()
    execute("""INSERT INTO jobs(id,organization_id,workspace_id,user_id,job_type,status,progress,dataset_id,payload_json,created_at,cancel_requested)
             VALUES(:id,:org,:ws,:user,:type,'queued',0,:ds,:payload,:created,0)""",
            {"id": job_id, "org": organization_id, "ws": workspace_id, "user": user_id, "type": job_type, "ds": dataset_id, "payload": json_dumps(payload), "created": now})
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
    execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,finished_at=CASE WHEN status='queued' THEN :finished ELSE finished_at END WHERE id=:id", {"finished": utcnow(), "id": job_id})
    return get_job(job_id)


def _update(job_id: str, **fields: Any) -> None:
    if not fields: return
    parts=[]; params={"id":job_id}
    for key,value in fields.items():
        parts.append(f"{key}=:{key}"); params[key]=value
    execute(f"UPDATE jobs SET {', '.join(parts)} WHERE id=:id", params)


def run_job(job_id: str) -> dict[str, Any]:
    from app.services.storage import load_dataframe, get_meta
    from app.services.modeling import automl_train
    from app.services.ai_analyst import AnalystContext, analyze_dataset
    from app.services.analysis_history import save_analysis
    from app.services.semantic_layer import get_semantic_model
    from app.services.forecasting import forecast_series
    from app.services.report_builder import build_report
    from app.services.proactive_intelligence import scan as proactive_scan

    job = get_job(job_id)
    if job["cancel_requested"] or job["status"] == "cancelled":
        _update(job_id, status="cancelled", finished_at=utcnow())
        return get_job(job_id)
    _update(job_id, status="running", progress=5, started_at=utcnow())
    payload = job["payload"]
    dataset_id = job.get("dataset_id")
    access_token = None
    try:
        from app.services.tenant_access import context_for_job, set_access_context, reset_access_context, authorize_dataset
        access_ctx = context_for_job(job["user_id"], job.get("workspace_id"))
        access_token = set_access_context(access_ctx)
        if access_ctx and dataset_id:
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
        else:
            raise ValueError("Type de job non supporté")
        current = get_job(job_id)
        if current["cancel_requested"]:
            _update(job_id, status="cancelled", progress=100, finished_at=utcnow())
        else:
            _update(job_id, status="completed", progress=100, result_json=json_dumps(result), finished_at=utcnow())
    except Exception as exc:
        _update(job_id, status="failed", error=str(exc), finished_at=utcnow())
    finally:
        if access_token is not None:
            try:
                reset_access_context(access_token)
            except Exception:
                pass
    return get_job(job_id)

