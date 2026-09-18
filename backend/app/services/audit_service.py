from __future__ import annotations

import uuid
from typing import Any

from app.services.metadata_store import execute, fetch_all, json_dumps, json_loads, utcnow


def record_event(event_type: str, *, user_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, resource_type: str | None = None, resource_id: str | None = None, outcome: str = "success", payload: dict[str, Any] | None = None) -> str:
    event_id = str(uuid.uuid4())
    execute("""
        INSERT INTO audit_logs(id,organization_id,workspace_id,user_id,event_type,resource_type,resource_id,outcome,payload_json,created_at)
        VALUES(:id,:org,:ws,:user,:event,:rtype,:rid,:outcome,:payload,:created)
    """, {
        "id": event_id, "org": organization_id, "ws": workspace_id, "user": user_id,
        "event": event_type, "rtype": resource_type, "rid": resource_id, "outcome": outcome,
        "payload": json_dumps(payload or {}), "created": utcnow(),
    })
    return event_id


def list_events(*, organization_id: str | None = None, workspace_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {"limit": max(1, min(limit, 1000))}
    if organization_id:
        clauses.append("organization_id=:org")
        params["org"] = organization_id
    if workspace_id:
        clauses.append("workspace_id=:ws")
        params["ws"] = workspace_id
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = fetch_all(f"SELECT * FROM audit_logs{where} ORDER BY created_at DESC LIMIT :limit", params)
    for row in rows:
        row["payload"] = json_loads(row.pop("payload_json", "{}"), {})
    return rows
