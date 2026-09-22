from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.services.connector_service import get_source
from app.services.metadata_store import connection, execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow


SUPPORTED_CDC_FORMATS = {"canonical", "debezium-json"}
SUPPORTED_CDC_OPERATIONS = {"c", "u", "d", "r", "create", "update", "delete", "read", "upsert"}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _partition_key(value: Any) -> str:
    if value in (None, ""):
        return "default"
    if isinstance(value, (dict, list)):
        return _stable_json(value)
    return str(value)


def _occurred_at(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
    except Exception:
        text = str(value)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return text[:120]


def _offset_rank(value: Any) -> tuple[str, Any] | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return ("number", Decimal(text))
    except (InvalidOperation, ValueError):
        pass
    if "/" in text:
        left, right = text.split("/", 1)
        try:
            return ("number", Decimal((int(left, 16) << 32) + int(right, 16)))
        except Exception:
            pass
    return ("opaque", text)


def _is_stale_offset(candidate: Any, checkpoint: Any) -> bool:
    if checkpoint in (None, ""):
        return False
    a, b = _offset_rank(candidate), _offset_rank(checkpoint)
    if not a or not b:
        return False
    if a[0] == b[0] == "number":
        return a[1] <= b[1]
    # Opaque resume tokens are not safely orderable. Equal token is duplicate/stale;
    # a different token is accepted and becomes the new checkpoint.
    return a[1] == b[1]


def canonicalize_cdc_event(raw_event: dict[str, Any], *, event_format: str = "debezium-json") -> dict[str, Any]:
    if event_format not in SUPPORTED_CDC_FORMATS:
        raise ValueError(f"Format CDC non supporté: {event_format}")
    if not isinstance(raw_event, dict):
        raise ValueError("Chaque événement CDC doit être un objet JSON.")

    if event_format == "debezium-json":
        payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else raw_event
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        op = str(payload.get("op") or "").lower()
        before = payload.get("before") if isinstance(payload.get("before"), dict) else None
        after = payload.get("after") if isinstance(payload.get("after"), dict) else None
        partition = raw_event.get("partition")
        if partition in (None, ""):
            partition = {
                key: source.get(key)
                for key in ("server_id", "server", "db", "schema", "table", "file")
                if source.get(key) not in (None, "")
            } or "default"
        offset = raw_event.get("offset")
        if offset in (None, ""):
            offset = next((source.get(key) for key in ("lsn", "pos", "sequence", "ts_ms") if source.get(key) not in (None, "")), None)
        ts_value = payload.get("ts_ms") or source.get("ts_ms")
        explicit_event_id = raw_event.get("event_id") or payload.get("event_id")
    else:
        op = str(raw_event.get("op") or raw_event.get("operation") or "").lower()
        before = raw_event.get("before") if isinstance(raw_event.get("before"), dict) else None
        after = raw_event.get("after") if isinstance(raw_event.get("after"), dict) else None
        partition = raw_event.get("partition", "default")
        offset = raw_event.get("offset")
        ts_value = raw_event.get("ts_ms") or raw_event.get("occurred_at")
        explicit_event_id = raw_event.get("event_id")

    if op not in SUPPORTED_CDC_OPERATIONS:
        raise ValueError(f"Opération CDC invalide: {op or 'absente'}")
    normalized_op = "delete" if op in {"d", "delete"} else "upsert"
    if normalized_op == "delete" and not (before or after):
        raise ValueError("Un delete CDC doit contenir before ou after pour identifier la clé primaire.")
    if normalized_op == "upsert" and not after:
        raise ValueError("Un événement create/update/read CDC doit contenir after.")
    if offset in (None, ""):
        raise ValueError("Offset CDC requis pour permettre la reprise exacte.")

    canonical = {
        "partition": _partition_key(partition),
        "offset": str(offset),
        "op": normalized_op,
        "before": before,
        "after": after,
        "occurred_at": _occurred_at(ts_value),
    }
    canonical["event_id"] = str(explicit_event_id or _sha256(canonical))
    canonical["payload_sha256"] = _sha256(canonical)
    return canonical


def _primary_key(source: dict[str, Any]) -> list[str]:
    value = (source.get("source_options") or {}).get("primary_key")
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list) or not value:
        raise ValueError("La source CDC doit définir source_options.primary_key.")
    return [str(item) for item in value]


def _row_key(row: dict[str, Any], primary_key: list[str]) -> tuple[Any, ...]:
    missing = [col for col in primary_key if col not in row]
    if missing:
        raise ValueError("Clé primaire CDC absente: " + ", ".join(missing))
    return tuple(row.get(col) for col in primary_key)


def _schema_of(frame: pd.DataFrame) -> dict[str, str]:
    return {str(col): str(dtype) for col, dtype in frame.dtypes.items()}


def _schema_drift(previous: dict[str, str] | None, current: dict[str, str]) -> dict[str, Any]:
    previous = previous or {}
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    changed = [
        {"column": col, "before": previous[col], "after": current[col]}
        for col in sorted(set(previous) & set(current))
        if previous[col] != current[col]
    ]
    return {"detected": bool(previous and (added or removed or changed)), "added": added, "removed": removed, "type_changed": changed}


def _existing_checkpoint(source_id: str, partition: str) -> dict[str, Any] | None:
    return fetch_one(
        "SELECT * FROM cdc_checkpoints WHERE source_id=:source AND partition_key=:partition",
        {"source": source_id, "partition": partition},
    )


def cdc_status(workspace_id: str, source_id: str) -> dict[str, Any]:
    source = get_source(workspace_id, source_id)
    if source.get("refresh_mode") != "cdc":
        raise ValueError("Cette source n'est pas configurée en mode CDC.")
    checkpoints = fetch_all(
        "SELECT partition_key,offset_value,event_id,updated_at FROM cdc_checkpoints WHERE workspace_id=:ws AND source_id=:source ORDER BY partition_key",
        {"ws": workspace_id, "source": source_id},
    )
    batches = fetch_all(
        "SELECT id,status,events_received,events_applied,duplicates,stale_events,dataset_id_after,started_at,finished_at,error FROM cdc_batches WHERE workspace_id=:ws AND source_id=:source ORDER BY started_at DESC LIMIT 25",
        {"ws": workspace_id, "source": source_id},
    )
    counts = fetch_one(
        "SELECT COUNT(*) AS n FROM cdc_events WHERE workspace_id=:ws AND source_id=:source AND status='applied'",
        {"ws": workspace_id, "source": source_id},
    ) or {"n": 0}
    return {
        "source_id": source_id,
        "dataset_id": source.get("dataset_id"),
        "primary_key": _primary_key(source),
        "checkpoints": checkpoints,
        "recent_batches": batches,
        "events_applied_total": int(counts.get("n") or 0),
    }


def ingest_cdc_events(
    workspace_id: str,
    source_id: str,
    *,
    actor_id: str,
    events: list[dict[str, Any]],
    event_format: str = "debezium-json",
    dry_run: bool = False,
) -> dict[str, Any]:
    from app.services.storage import load_dataframe_raw, save_dataframe_source, save_dataframe_version
    from app.services.workspace_service import bind_dataset

    source = get_source(workspace_id, source_id)
    if source.get("refresh_mode") != "cdc":
        raise ValueError("La source doit être configurée avec refresh_mode=cdc.")
    if not events:
        raise ValueError("Le lot CDC est vide.")
    if len(events) > 5000:
        raise ValueError("Un lot CDC est limité à 5000 événements.")

    primary_key = _primary_key(source)
    canonical = [canonicalize_cdc_event(item, event_format=event_format) for item in events]
    batch_sha = _sha256([item["payload_sha256"] for item in canonical])
    existing_batch = fetch_one(
        "SELECT * FROM cdc_batches WHERE source_id=:source AND batch_sha256=:sha AND status='completed'",
        {"source": source_id, "sha": batch_sha},
    )
    if existing_batch and not dry_run:
        return {
            "idempotent": True,
            "batch_id": existing_batch["id"],
            "dataset_id": existing_batch.get("dataset_id_after"),
            "events_received": int(existing_batch.get("events_received") or 0),
            "events_applied": int(existing_batch.get("events_applied") or 0),
            "duplicates": int(existing_batch.get("duplicates") or 0),
            "stale_events": int(existing_batch.get("stale_events") or 0),
            "checkpoints": json_loads(existing_batch.get("checkpoint_json"), {}),
        }

    checkpoint_cache: dict[str, dict[str, Any] | None] = {}
    accepted: list[dict[str, Any]] = []
    duplicates = 0
    stale = 0
    seen_batch_ids: set[str] = set()
    for event in canonical:
        event_id = event["event_id"]
        if event_id in seen_batch_ids:
            duplicates += 1
            continue
        seen_batch_ids.add(event_id)
        prior = fetch_one(
            "SELECT status FROM cdc_events WHERE workspace_id=:ws AND source_id=:source AND event_id=:event",
            {"ws": workspace_id, "source": source_id, "event": event_id},
        )
        if prior and prior.get("status") == "applied":
            duplicates += 1
            continue
        partition = event["partition"]
        if partition not in checkpoint_cache:
            checkpoint_cache[partition] = _existing_checkpoint(source_id, partition)
        checkpoint = checkpoint_cache[partition]
        if checkpoint and _is_stale_offset(event["offset"], checkpoint.get("offset_value")):
            stale += 1
            continue
        accepted.append(event)
        checkpoint_cache[partition] = {
            "offset_value": event["offset"],
            "event_id": event_id,
        }

    before_id = source.get("dataset_id")
    if before_id:
        current = load_dataframe_raw(before_id)
        state: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in current.where(current.notna(), None).to_dict(orient="records"):
            state[_row_key(row, primary_key)] = dict(row)
    else:
        state = {}

    for event in accepted:
        record = event["after"] if event["op"] == "upsert" else (event["before"] or event["after"])
        assert isinstance(record, dict)
        key = _row_key(record, primary_key)
        if event["op"] == "delete":
            state.pop(key, None)
        else:
            state[key] = dict(record)

    ordered = sorted(state.values(), key=lambda row: tuple(str(row.get(col)) for col in primary_key))
    if ordered:
        materialized = pd.DataFrame(ordered)
    elif before_id:
        materialized = current.iloc[0:0].copy()
    else:
        columns = sorted({key for event in accepted for record in (event.get("before"), event.get("after")) if isinstance(record, dict) for key in record})
        materialized = pd.DataFrame(columns=columns)
    schema = _schema_of(materialized)
    drift = _schema_drift(source.get("schema"), schema)
    if drift["detected"] and source.get("schema_drift_policy") == "fail" and (drift["removed"] or drift["type_changed"]):
        raise ValueError(f"Schema drift CDC bloquant: {drift}")

    checkpoint_payload = {
        partition: {"offset": value.get("offset_value"), "event_id": value.get("event_id")}
        for partition, value in checkpoint_cache.items()
        if value
    }
    preview = {
        "idempotent": False,
        "dry_run": bool(dry_run),
        "batch_sha256": batch_sha,
        "events_received": len(canonical),
        "events_applied": len(accepted),
        "duplicates": duplicates,
        "stale_events": stale,
        "rows_after": len(materialized),
        "schema_drift": drift,
        "checkpoints": checkpoint_payload,
    }
    if dry_run:
        return preview

    batch_id = str(uuid.uuid4())
    started = utcnow()
    execute(
        """INSERT INTO cdc_batches(id,workspace_id,source_id,batch_sha256,status,events_received,events_applied,duplicates,stale_events,dataset_id_before,started_at)
           VALUES(:id,:ws,:source,:sha,'running',:received,:applied,:duplicates,:stale,:before,:started)""",
        {"id": batch_id, "ws": workspace_id, "source": source_id, "sha": batch_sha, "received": len(canonical), "applied": len(accepted), "duplicates": duplicates, "stale": stale, "before": before_id, "started": started},
    )
    try:
        if accepted:
            if before_id:
                meta = save_dataframe_version(
                    before_id,
                    materialized,
                    {"type": "cdc_ingestion", "label": f"CDC · {source['name']}", "source_id": source_id, "batch_id": batch_id, "events_applied": len(accepted), "batch_sha256": batch_sha},
                    governance_materialized=False,
                )
            else:
                meta = save_dataframe_source(
                    materialized,
                    source["name"],
                    {"connector_id": source["connector_id"], "source_id": source_id, "workspace_id": workspace_id, "source_kind": source["source_kind"], "table_name": source.get("table_name"), "refresh_mode": "cdc", "cdc_batch_id": batch_id},
                )
            after_id = meta["id"]
            bind_dataset(actor_id, workspace_id, after_id)
        else:
            after_id = before_id

        finished = utcnow()
        with connection() as conn:
            for event in accepted:
                conn.execute(
                    text(
                        """INSERT INTO cdc_events(id,workspace_id,source_id,batch_id,event_id,partition_key,offset_value,operation,payload_sha256,status,dataset_id,occurred_at,created_at)
                           VALUES(:id,:ws,:source,:batch,:event,:partition,:offset,:op,:sha,'applied',:dataset,:occurred,:created)"""
                    ),
                    {"id": str(uuid.uuid4()), "ws": workspace_id, "source": source_id, "batch": batch_id, "event": event["event_id"], "partition": event["partition"], "offset": event["offset"], "op": event["op"], "sha": event["payload_sha256"], "dataset": after_id, "occurred": event.get("occurred_at"), "created": finished},
                )
            for partition, value in checkpoint_payload.items():
                params = {"ws": workspace_id, "source": source_id, "partition": partition, "offset": str(value["offset"]), "event": str(value["event_id"]), "updated": finished}
                updated = conn.execute(
                    text("UPDATE cdc_checkpoints SET offset_value=:offset,event_id=:event,updated_at=:updated,workspace_id=:ws WHERE source_id=:source AND partition_key=:partition"), params
                )
                if getattr(updated, "rowcount", 0) == 0:
                    conn.execute(
                        text("INSERT INTO cdc_checkpoints(workspace_id,source_id,partition_key,offset_value,event_id,updated_at) VALUES(:ws,:source,:partition,:offset,:event,:updated)"), params
                    )
            conn.execute(
                text("UPDATE cdc_batches SET status='completed',dataset_id_after=:after,checkpoint_json=:checkpoint,finished_at=:finished WHERE id=:id"),
                {"after": after_id, "checkpoint": json_dumps(checkpoint_payload), "finished": finished, "id": batch_id},
            )
            conn.execute(
                text("UPDATE connector_sources SET dataset_id=:dataset,schema_json=:schema,status='healthy',last_refresh_finished_at=:finished,last_success_at=:finished,last_error=NULL,last_rows_fetched=:rows,schema_drift_json=:drift,updated_at=:finished WHERE id=:id"),
                {"dataset": after_id, "schema": json_dumps(schema), "finished": finished, "rows": len(accepted), "drift": json_dumps(drift), "id": source_id},
            )
            conn.execute(
                text("""INSERT INTO refresh_runs(id,workspace_id,source_id,connector_id,dataset_id_before,dataset_id_after,mode,status,trigger_type,triggered_by,job_id,rows_fetched,rows_written,watermark_after_json,schema_drift_json,started_at,finished_at)
                VALUES(:id,:ws,:source,:connector,:before,:after,'cdc','completed','cdc',:actor,:job,:fetched,:written,:watermark,:drift,:started,:finished)"""),
                {"id": str(uuid.uuid4()), "ws": workspace_id, "source": source_id, "connector": source["connector_id"], "before": before_id, "after": after_id, "actor": actor_id, "job": f"cdc:{batch_id}", "fetched": len(canonical), "written": len(accepted), "watermark": json_dumps(checkpoint_payload), "drift": json_dumps(drift), "started": started, "finished": finished},
            )
        if after_id:
            try:
                from app.services.data_reliability import register_lineage_edge
                register_lineage_edge(workspace_id, "source", source_id, "dataset", after_id, "cdc_materialized_as", {"batch_id": batch_id, "events_applied": len(accepted)})
            except Exception:
                pass
        return {**preview, "batch_id": batch_id, "dataset_id": after_id, "finished_at": finished}
    except Exception as exc:
        finished = utcnow()
        execute("UPDATE cdc_batches SET status='failed',error=:error,finished_at=:finished WHERE id=:id", {"error": str(exc)[:1800], "finished": finished, "id": batch_id})
        execute("UPDATE connector_sources SET status='error',last_error=:error,updated_at=:finished WHERE id=:id", {"error": str(exc)[:1800], "finished": finished, "id": source_id})
        raise
