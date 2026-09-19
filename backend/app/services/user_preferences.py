from __future__ import annotations

from typing import Any

from app.services.metadata_store import execute, fetch_one, json_dumps, json_loads, utcnow

_ALLOWED_MODES = {"normal", "comfortable", "large"}


def _sanitize(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    result: dict[str, Any] = {}

    mode = raw.get("accessibility_mode")
    if mode in _ALLOWED_MODES:
        result["accessibility_mode"] = mode

    zoom = raw.get("ui_zoom")
    if zoom is not None:
        try:
            value = int(zoom)
        except (TypeError, ValueError):
            value = 100
        result["ui_zoom"] = max(90, min(value, 140))

    compact = raw.get("compact_navigation")
    if isinstance(compact, bool):
        result["compact_navigation"] = compact

    return result


def get_user_preferences(user_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT preferences_json,updated_at FROM user_preferences WHERE user_id=:id",
        {"id": user_id},
    )
    if not row:
        return {
            "preferences": {},
            "updated_at": None,
            "storage": "profile",
        }
    return {
        "preferences": _sanitize(
            json_loads(row.get("preferences_json"), {})
        ),
        "updated_at": row.get("updated_at"),
        "storage": "profile",
    }


def save_user_preferences(
    user_id: str,
    preferences: dict[str, Any],
) -> dict[str, Any]:
    current = get_user_preferences(user_id)["preferences"]
    merged = _sanitize({**current, **dict(preferences or {})})
    now = utcnow()
    exists = fetch_one(
        "SELECT user_id FROM user_preferences WHERE user_id=:id",
        {"id": user_id},
    )
    if exists:
        execute(
            "UPDATE user_preferences SET preferences_json=:prefs,updated_at=:updated WHERE user_id=:id",
            {"prefs": json_dumps(merged), "updated": now, "id": user_id},
        )
    else:
        execute(
            "INSERT INTO user_preferences(user_id,preferences_json,updated_at) VALUES(:id,:prefs,:updated)",
            {"id": user_id, "prefs": json_dumps(merged), "updated": now},
        )
    return {
        "preferences": merged,
        "updated_at": now,
        "storage": "profile",
    }
