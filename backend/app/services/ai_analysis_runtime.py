from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
import uuid
from typing import Any, AsyncIterator

from app.core.config import get_settings
from app.services.ai_analyst import AnalystContext, AnalysisCancelled, analyze_dataset
from app.services.analysis_history import save_analysis
from app.services.metadata_store import execute, fetch_one, json_dumps, json_loads, utcnow
from app.services.semantic_layer import get_semantic_model
from app.services.storage import get_meta, load_dataframe
from app.services.tenant_access import (
    DataAccessContext,
    current_access_context,
    reset_access_context,
    set_access_context,
)

ENGINE_VERSION = "ai_analyst_v228"
_LOCK = threading.Lock()
_SEMAPHORE = threading.BoundedSemaphore(4)
_THREADS: dict[str, threading.Thread] = {}


def _semantic_revision(dataset_id: str, meta: dict[str, Any]) -> str:
    root_id = str(meta.get("root_id") or meta.get("id") or dataset_id)
    path = get_settings().data_root / "semantic" / f"{root_id}.json"
    if not path.exists():
        return "auto:1"
    try:
        stat = path.stat()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return f"file:{payload.get('version', 1)}:{stat.st_mtime_ns}:{stat.st_size}"
    except Exception:
        return "file:unknown"


def _canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": str(payload.get("question") or "").strip(),
        "target": payload.get("target") or None,
        "date_column": payload.get("date_column") or None,
        "variables": sorted(str(x) for x in (payload.get("variables") or [])),
        "group": payload.get("group") or None,
        "horizon": int(payload.get("horizon") or 12),
        "mode": str(payload.get("mode") or "auto"),
    }


def _cache_key(dataset_id: str, meta: dict[str, Any], payload: dict[str, Any]) -> str:
    document = {
        "engine": ENGINE_VERSION,
        "dataset_id": dataset_id,
        "dataset_version": int(meta.get("version") or 1),
        "semantic_revision": _semantic_revision(dataset_id, meta),
        "payload": _canonical_payload(payload),
    }
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hydrate(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["payload"] = json_loads(item.pop("payload_json", "{}"), {})
    item["result"] = json_loads(item.pop("result_json", None), None)
    item["cancel_requested"] = bool(item.get("cancel_requested"))
    item["cached"] = bool(item.get("cached"))
    item["progress"] = int(item.get("progress") or 0)
    return item


def get_analysis_run(run_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM ai_analysis_runs WHERE id=:id", {"id": run_id})
    if not row:
        raise KeyError("Exécution AI Analyst introuvable.")
    return _hydrate(row) or {}


def _update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    parts: list[str] = []
    params: dict[str, Any] = {"id": run_id, "updated_at": utcnow()}
    for key, value in fields.items():
        parts.append(f"{key}=:{key}")
        params[key] = value
    parts.append("updated_at=:updated_at")
    execute(f"UPDATE ai_analysis_runs SET {', '.join(parts)} WHERE id=:id", params)


def _cancel_requested(run_id: str) -> bool:
    row = fetch_one(
        "SELECT cancel_requested,status FROM ai_analysis_runs WHERE id=:id",
        {"id": run_id},
    )
    return bool(row and (row.get("cancel_requested") or row.get("status") == "cancelled"))


def _cache_lookup(cache_key: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT result_json FROM ai_analysis_cache WHERE cache_key=:key",
        {"key": cache_key},
    )
    if not row:
        return None
    execute(
        "UPDATE ai_analysis_cache SET hit_count=hit_count+1,last_hit_at=:hit WHERE cache_key=:key",
        {"hit": utcnow(), "key": cache_key},
    )
    result = json_loads(row.get("result_json"), None)
    if isinstance(result, dict):
        result.setdefault("runtime", {})
        result["runtime"].update({"cache_hit": True, "engine_version": ENGINE_VERSION})
    return result


def _cache_store(cache_key: str, dataset_id: str, meta: dict[str, Any], result: dict[str, Any]) -> None:
    semantic_revision = _semantic_revision(dataset_id, meta)
    existing = fetch_one(
        "SELECT cache_key FROM ai_analysis_cache WHERE cache_key=:key",
        {"key": cache_key},
    )
    params = {
        "key": cache_key,
        "dataset": dataset_id,
        "version": int(meta.get("version") or 1),
        "semantic": semantic_revision,
        "engine": ENGINE_VERSION,
        "result": json_dumps(result),
        "created": utcnow(),
    }
    if existing:
        execute(
            "UPDATE ai_analysis_cache SET result_json=:result,created_at=:created,last_hit_at=:created WHERE cache_key=:key",
            params,
        )
    else:
        execute(
            """
            INSERT INTO ai_analysis_cache(
              cache_key,dataset_id,dataset_version,semantic_version,engine_version,
              result_json,created_at,last_hit_at,hit_count
            ) VALUES(
              :key,:dataset,:version,:semantic,:engine,:result,:created,NULL,0
            )
            """,
            params,
        )


def submit_analysis_run(dataset_id: str, payload: dict[str, Any], *, use_cache: bool = True) -> dict[str, Any]:
    meta = get_meta(dataset_id)
    canonical = _canonical_payload(payload)
    if not canonical["question"]:
        raise ValueError("La question analytique ne peut pas être vide.")
    key = _cache_key(dataset_id, meta, canonical)
    access = current_access_context()

    if use_cache:
        cached = _cache_lookup(key)
        if cached is not None:
            run_id = str(uuid.uuid4())
            now = utcnow()
            execute(
                """
                INSERT INTO ai_analysis_runs(
                  id,dataset_id,dataset_version,workspace_id,organization_id,user_id,
                  cache_key,status,progress,stage,current_tool,cancel_requested,cached,
                  payload_json,result_json,error,created_at,started_at,finished_at,updated_at
                ) VALUES(
                  :id,:dataset,:version,:ws,:org,:user,:cache,'completed',100,
                  'Résultat restauré du cache',NULL,0,1,:payload,:result,NULL,
                  :created,:created,:created,:created
                )
                """,
                {
                    "id": run_id,
                    "dataset": dataset_id,
                    "version": int(meta.get("version") or 1),
                    "ws": access.workspace_id if access else None,
                    "org": access.organization_id if access else None,
                    "user": access.user_id if access else None,
                    "cache": key,
                    "payload": json_dumps(canonical),
                    "result": json_dumps(cached),
                    "created": now,
                },
            )
            return get_analysis_run(run_id)

    params: dict[str, Any] = {"key": key}
    where = "cache_key=:key AND status IN ('queued','running','cancel_requested')"
    if access:
        where += " AND workspace_id=:ws AND user_id=:user"
        params.update({"ws": access.workspace_id, "user": access.user_id})
    else:
        where += " AND workspace_id IS NULL AND user_id IS NULL"
    existing = fetch_one(
        f"SELECT id FROM ai_analysis_runs WHERE {where} ORDER BY created_at DESC",
        params,
    )
    if existing:
        return get_analysis_run(str(existing["id"]))

    run_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """
        INSERT INTO ai_analysis_runs(
          id,dataset_id,dataset_version,workspace_id,organization_id,user_id,
          cache_key,status,progress,stage,current_tool,cancel_requested,cached,
          payload_json,result_json,error,created_at,started_at,finished_at,updated_at
        ) VALUES(
          :id,:dataset,:version,:ws,:org,:user,:cache,'queued',0,
          'En attente',NULL,0,0,:payload,NULL,NULL,:created,NULL,NULL,:created
        )
        """,
        {
            "id": run_id,
            "dataset": dataset_id,
            "version": int(meta.get("version") or 1),
            "ws": access.workspace_id if access else None,
            "org": access.organization_id if access else None,
            "user": access.user_id if access else None,
            "cache": key,
            "payload": json_dumps(canonical),
            "created": now,
        },
    )
    def runner() -> None:
        with _SEMAPHORE:
            _run_analysis(run_id, dataset_id, canonical, access, key)

    thread = threading.Thread(
        target=runner,
        name=f"dv-ai-analysis-{run_id[:8]}",
        daemon=True,
    )
    with _LOCK:
        _THREADS[run_id] = thread
    thread.start()
    return get_analysis_run(run_id)


def _run_analysis(
    run_id: str,
    dataset_id: str,
    payload: dict[str, Any],
    access: DataAccessContext | None,
    cache_key: str,
) -> None:
    token = None
    started_perf = time.perf_counter()
    try:
        if access is not None:
            token = set_access_context(access)
        if _cancel_requested(run_id):
            _update_run(run_id, status="cancelled", progress=100, stage="Annulée avant démarrage", finished_at=utcnow())
            return

        _update_run(run_id, status="running", progress=5, stage="Chargement du dataset gouverné", started_at=utcnow())
        frame = load_dataframe(dataset_id)
        meta = get_meta(dataset_id)
        semantic = get_semantic_model(dataset_id, frame)
        context = AnalystContext(
            dataset={
                "id": meta["id"],
                "name": meta["original_name"],
                "format": meta["extension"],
                "version": meta.get("version", 1),
                "parent_id": meta.get("parent_id"),
                "root_id": meta.get("root_id", meta["id"]),
                "operation": meta.get("operation"),
            },
            question=payload["question"],
            target=payload.get("target"),
            date_column=payload.get("date_column"),
            variables=payload.get("variables") or [],
            group=payload.get("group"),
            horizon=int(payload.get("horizon") or 12),
            mode=str(payload.get("mode") or "auto"),
            semantic_model=semantic,
        )

        def progress(event: dict[str, Any]) -> None:
            _update_run(
                run_id,
                progress=max(5, min(int(event.get("progress") or 5), 95)),
                stage=str(event.get("stage") or "Analyse en cours")[:500],
                current_tool=str(event.get("tool"))[:120] if event.get("tool") else None,
            )

        result = analyze_dataset(
            frame,
            context,
            progress_callback=progress,
            cancel_check=lambda: _cancel_requested(run_id),
        )
        result.setdefault("runtime", {})
        result["runtime"].update(
            {
                "cache_key": cache_key,
                "cache_hit": False,
                "elapsed_ms": round((time.perf_counter() - started_perf) * 1000.0, 2),
                "engine_version": ENGINE_VERSION,
            }
        )
        save_analysis(result)
        _cache_store(cache_key, dataset_id, meta, result)
        _update_run(
            run_id,
            status="completed",
            progress=100,
            stage="Analyse terminée",
            current_tool=None,
            result_json=json_dumps(result),
            finished_at=utcnow(),
        )
    except AnalysisCancelled:
        _update_run(run_id, status="cancelled", progress=100, stage="Analyse annulée", current_tool=None, finished_at=utcnow())
    except Exception as exc:
        _update_run(
            run_id,
            status="failed",
            progress=100,
            stage="Analyse interrompue",
            current_tool=None,
            error=f"{type(exc).__name__}: {str(exc)[:2000]}",
            finished_at=utcnow(),
        )
    finally:
        if token is not None:
            reset_access_context(token)
        with _LOCK:
            _THREADS.pop(run_id, None)


def cancel_analysis_run(run_id: str) -> dict[str, Any]:
    run = get_analysis_run(run_id)
    if run["status"] in {"completed", "failed", "cancelled"}:
        return run
    next_status = "cancelled" if run["status"] == "queued" else "cancel_requested"
    updates: dict[str, Any] = {
        "cancel_requested": 1,
        "status": next_status,
        "stage": "Annulation demandée" if next_status == "cancel_requested" else "Analyse annulée",
    }
    if next_status == "cancelled":
        updates.update({"finished_at": utcnow(), "progress": 100})
    _update_run(run_id, **updates)
    return get_analysis_run(run_id)


def assert_run_access(run: dict[str, Any]) -> None:
    access = current_access_context()
    if access is None:
        if run.get("workspace_id") or run.get("user_id"):
            raise PermissionError("Cette exécution appartient à un workspace gouverné.")
        return
    if str(run.get("workspace_id") or "") != access.workspace_id:
        raise PermissionError("Exécution AI Analyst hors du workspace actif.")
    if run.get("user_id") and str(run.get("user_id")) != access.user_id:
        raise PermissionError("Cette exécution AI Analyst appartient à un autre utilisateur.")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def stream_analysis_events(run_id: str) -> AsyncIterator[str]:
    last_signature: tuple[Any, ...] | None = None
    while True:
        run = get_analysis_run(run_id)
        signature = (
            run.get("status"), run.get("progress"), run.get("stage"),
            run.get("current_tool"), bool(run.get("result")), run.get("error"),
        )
        if signature != last_signature:
            payload = {
                "id": run["id"],
                "status": run["status"],
                "progress": run["progress"],
                "stage": run.get("stage"),
                "current_tool": run.get("current_tool"),
                "cached": run.get("cached", False),
                "error": run.get("error"),
            }
            if run["status"] == "completed":
                payload["result"] = run.get("result")
            yield _sse("analysis", payload)
            last_signature = signature
        if run["status"] in {"completed", "failed", "cancelled"}:
            yield _sse("done", {"status": run["status"], "id": run_id})
            return
        await asyncio.sleep(0.25)
