from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


def _dir() -> Path:
    path = get_settings().data_root / "analyses"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_analysis(result: dict[str, Any]) -> dict[str, Any]:
    session_id = str(result.get("session_id") or "").strip()
    dataset_id = str(result.get("provenance", {}).get("dataset_id") or "").strip()
    if not session_id or not dataset_id:
        raise ValueError("Analyse sans session_id ou dataset_id")
    path = _dir() / f"{session_id}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


def get_analysis(session_id: str) -> dict[str, Any]:
    path = _dir() / f"{session_id}.json"
    if not path.exists():
        raise FileNotFoundError(session_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_analyses(dataset_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _dir().glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        provenance = item.get("provenance", {})
        if provenance.get("dataset_id") != dataset_id:
            continue
        rows.append({
            "session_id": item.get("session_id"),
            "question": item.get("question"),
            "intent": item.get("intent"),
            "mode": item.get("mode"),
            "answer": item.get("answer"),
            "critic_status": item.get("critic", {}).get("status"),
            "executed_at": provenance.get("executed_at"),
            "dataset_version": provenance.get("dataset_version"),
            "tools_executed": provenance.get("tools_executed", []),
            "findings_count": len(item.get("findings", [])),
        })
    rows.sort(key=lambda x: x.get("executed_at") or "", reverse=True)
    return rows
