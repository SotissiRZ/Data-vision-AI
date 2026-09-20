from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.preparation import apply_operation, combine_dataframes
from app.services.storage import get_lineage, get_meta, load_dataframe, save_dataframe_version


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir() -> Path:
    path = get_settings().data_root / "pipelines"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(pipeline_id: str) -> Path:
    return _dir() / f"{pipeline_id}.json"


def list_pipelines() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _dir().glob("*.json"):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return rows


def get_pipeline(pipeline_id: str) -> dict[str, Any]:
    path = _path(pipeline_id)
    if not path.exists():
        raise FileNotFoundError(pipeline_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _combine_step(operation: dict[str, Any]) -> dict[str, Any]:
    kind = str(operation.get("type") or "")
    mapping = {
        "combine_merge": "merge",
        "combine_concat_rows": "concat_rows",
        "combine_concat_columns": "concat_columns",
    }
    combine_type = mapping.get(kind)
    if not combine_type:
        raise ValueError(f"Combinaison de pipeline non reconnue: {kind}")
    params = dict(operation.get("params") or {})
    other_dataset_id = str(params.pop("other_dataset_id", "") or "")
    if not other_dataset_id:
        raise ValueError("La combinaison ne contient pas l'identifiant du dataset secondaire.")
    other_meta = get_meta(other_dataset_id)
    # Runtime-only provenance fields are stored at the step level, not sent back
    # into combine_dataframes().
    params.pop("other_dataset_version", None)
    params.pop("other_dataset_root_id", None)
    params.pop("renamed_overlaps", None)
    return {
        "type": "combine_dataset",
        "combine_type": combine_type,
        "other_dataset_id": other_dataset_id,
        "other_dataset_root_id": other_meta.get("root_id") or other_meta["id"],
        "other_dataset_version": int(other_meta.get("version", 1)),
        "other_dataset_name": other_meta.get("source_name") or other_meta.get("original_name"),
        "operation": {"type": combine_type, **params},
    }


def _pipeline_step(operation: dict[str, Any]) -> dict[str, Any]:
    kind = str(operation.get("type", ""))
    if kind.startswith("combine_"):
        return _combine_step(operation)
    params = dict(operation.get("params") or {})
    return {"type": "transform", "operation": {"type": kind, **params}}


def save_lineage_as_pipeline(dataset_id: str, name: str) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("Le nom du pipeline est requis.")
    lineage = get_lineage(dataset_id)
    steps: list[dict[str, Any]] = []
    dependencies: dict[str, dict[str, Any]] = {}
    for meta in lineage:
        # The first lineage node is the immutable source, regardless of whether
        # it originated from upload, connector ingestion, feature materialization, etc.
        # Source operations are provenance, not replayable transformations.
        if not meta.get("parent_id"):
            continue
        operation = meta.get("operation") or {}
        kind = str(operation.get("type", ""))
        if not kind:
            continue
        step = _pipeline_step(operation)
        steps.append(step)
        if step["type"] == "combine_dataset":
            root_id = str(step["other_dataset_root_id"])
            dependencies[root_id] = {
                "root_id": root_id,
                "dataset_id": step["other_dataset_id"],
                "version": step["other_dataset_version"],
                "name": step.get("other_dataset_name"),
            }
    if not steps:
        raise ValueError("Aucune transformation à enregistrer dans ce pipeline.")
    pipeline_id = str(uuid.uuid4())
    source = get_meta(dataset_id)
    payload = {
        "id": pipeline_id,
        "name": name,
        "created_at": _now(),
        "source_root_id": source.get("root_id") or source["id"],
        "source_dataset_id": dataset_id,
        "steps": steps,
        "steps_count": len(steps),
        "multi_dataset": bool(dependencies),
        "dependencies": list(dependencies.values()),
        "format_version": 2,
    }
    _path(pipeline_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _resolve_secondary(step: dict[str, Any], bindings: dict[str, str]) -> str:
    stored_id = str(step.get("other_dataset_id") or "")
    root_id = str(step.get("other_dataset_root_id") or "")
    candidate = bindings.get(root_id) or bindings.get(stored_id) or stored_id
    if not candidate:
        raise ValueError("Dataset secondaire absent du pipeline.")
    # Fail early with a useful error if a binding references a missing dataset.
    get_meta(candidate)
    return candidate


def _execute_in_memory(
    dataset_id: str,
    pipeline: dict[str, Any],
    bindings: dict[str, str],
) -> tuple[Any, list[dict[str, Any]]]:
    frame = load_dataframe(dataset_id)
    trace: list[dict[str, Any]] = []
    for index, raw_step in enumerate(pipeline.get("steps") or [], start=1):
        step = dict(raw_step or {})
        before_rows, before_cols = int(len(frame)), int(len(frame.columns))
        if step.get("type") == "combine_dataset":
            other_id = _resolve_secondary(step, bindings)
            right = load_dataframe(other_id)
            op = dict(step.get("operation") or {})
            frame, operation = combine_dataframes(frame, right, op)
            operation.setdefault("params", {})["other_dataset_id"] = other_id
            other_meta = get_meta(other_id)
            operation["params"]["other_dataset_version"] = int(other_meta.get("version", 1))
            operation["params"]["other_dataset_root_id"] = other_meta.get("root_id") or other_meta["id"]
        else:
            op = dict(step.get("operation") or step)
            frame, operation = apply_operation(frame, op)
        trace.append({
            "index": index,
            "operation": operation,
            "rows_before": before_rows,
            "rows_after": int(len(frame)),
            "columns_before": before_cols,
            "columns_after": int(len(frame.columns)),
        })
    return frame, trace


def validate_pipeline(dataset_id: str, pipeline_id: str, bindings: dict[str, str] | None = None) -> dict[str, Any]:
    pipeline = get_pipeline(pipeline_id)
    steps = pipeline.get("steps") or []
    if not steps:
        raise ValueError("Ce pipeline ne contient aucune étape.")
    frame, trace = _execute_in_memory(dataset_id, pipeline, dict(bindings or {}))
    return {
        "pipeline_id": pipeline_id,
        "valid": True,
        "steps_count": len(trace),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "trace": trace,
    }


def run_pipeline(dataset_id: str, pipeline_id: str, bindings: dict[str, str] | None = None) -> dict[str, Any]:
    pipeline = get_pipeline(pipeline_id)
    steps = pipeline.get("steps") or []
    if not steps:
        raise ValueError("Ce pipeline ne contient aucune étape.")
    resolved_bindings = dict(bindings or {})

    # Preflight every step in memory first. A deterministic transformation error
    # therefore cannot leave a partially persisted branch behind.
    _, validation_trace = _execute_in_memory(dataset_id, pipeline, resolved_bindings)

    current_id = dataset_id
    frame = load_dataframe(dataset_id)
    executed: list[dict[str, Any]] = []
    for raw_step in steps:
        step = dict(raw_step or {})
        if step.get("type") == "combine_dataset":
            other_id = _resolve_secondary(step, resolved_bindings)
            right = load_dataframe(other_id)
            frame, operation = combine_dataframes(frame, right, dict(step.get("operation") or {}))
            operation.setdefault("params", {})["other_dataset_id"] = other_id
            other_meta = get_meta(other_id)
            operation["params"]["other_dataset_version"] = int(other_meta.get("version", 1))
            operation["params"]["other_dataset_root_id"] = other_meta.get("root_id") or other_meta["id"]
        else:
            frame, operation = apply_operation(frame, dict(step.get("operation") or step))
        meta = save_dataframe_version(current_id, frame, operation)
        current_id = meta["id"]
        executed.append({"dataset_id": current_id, "version": meta["version"], "operation": operation})
    return {
        "pipeline": pipeline,
        "dataset_id": current_id,
        "executed": executed,
        "validation": {
            "status": "pass",
            "trace": validation_trace,
        },
        "bindings": resolved_bindings,
    }
