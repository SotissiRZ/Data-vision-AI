from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_settings


def _dir() -> Path:
    path = get_settings().data_root / "saved_visualizations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_visualization(dataset_id: str, dataset_version: int, title: str, visualization: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": str(uuid4()),
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "title": (title or visualization.get("title") or "Visualisation DataVision").strip(),
        "created_at": _now(),
        "visualization": visualization,
    }
    (_dir() / f"{item['id']}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return item


def list_visualizations(dataset_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _dir().glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if item.get("dataset_id") == dataset_id:
            rows.append(item)
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return rows


def get_visualization(visualization_id: str) -> dict[str, Any]:
    path = _dir() / f"{visualization_id}.json"
    if not path.exists():
        raise FileNotFoundError(visualization_id)
    return json.loads(path.read_text(encoding="utf-8"))
