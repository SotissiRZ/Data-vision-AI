from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.preparation import apply_operation
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


def save_lineage_as_pipeline(dataset_id: str, name: str) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("Le nom du pipeline est requis.")
    lineage = get_lineage(dataset_id)
    operations: list[dict[str, Any]] = []
    for meta in lineage:
        operation = meta.get("operation") or {}
        kind = str(operation.get("type", ""))
        if kind in {"", "upload"}:
            continue
        if kind.startswith("combine_"):
            raise ValueError("Un pipeline contenant une combinaison multi-dataset ne peut pas encore être enregistré comme pipeline réutilisable.")
        params = operation.get("params") or {}
        # The persisted operation metadata is designed to be replayable.
        operations.append({"type": kind, **params})
    if not operations:
        raise ValueError("Aucune transformation à enregistrer dans ce pipeline.")
    pipeline_id = str(uuid.uuid4())
    source = get_meta(dataset_id)
    payload = {
        "id": pipeline_id,
        "name": name,
        "created_at": _now(),
        "source_root_id": source.get("root_id") or source["id"],
        "source_dataset_id": dataset_id,
        "steps": operations,
        "steps_count": len(operations),
    }
    _path(pipeline_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def run_pipeline(dataset_id: str, pipeline_id: str) -> dict[str, Any]:
    pipeline = get_pipeline(pipeline_id)
    steps = pipeline.get("steps") or []
    if not steps:
        raise ValueError("Ce pipeline ne contient aucune étape.")
    current_id = dataset_id
    frame = load_dataframe(dataset_id)
    executed: list[dict[str, Any]] = []
    for step in steps:
        frame, operation = apply_operation(frame, step)
        meta = save_dataframe_version(current_id, frame, operation)
        current_id = meta["id"]
        executed.append({"dataset_id": current_id, "version": meta["version"], "operation": operation})
    return {"pipeline": pipeline, "dataset_id": current_id, "executed": executed}
