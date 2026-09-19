from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


@dataclass
class SessionMemory:
    session_id: str
    workspace_id: str | None = None
    objective: str | None = None
    current_task: str | None = None
    active_entities: dict[str, str] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    # Compact conversational state. This deliberately stores semantic summaries
    # rather than the raw chat transcript.
    last_intent: str | None = None
    last_entities: dict[str, Any] = field(default_factory=dict)
    recent_columns: list[str] = field(default_factory=list)
    recent_intents: list[dict[str, Any]] = field(default_factory=list)
    last_result_summary: str | None = None

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SessionMemoryStore:
    """
    Compact working memory for the assistant.

    This is deliberately not a raw conversation archive. Durable enterprise
    memory should be persisted through the DataVision metadata layer with
    retention and tenant policies.
    """

    def __init__(self) -> None:
        self._items: dict[str, SessionMemory] = {}
        self._lock = RLock()

    def get_or_create(
        self,
        session_id: str,
        workspace_id: str | None = None,
    ) -> SessionMemory:
        with self._lock:
            item = self._items.get(session_id)
            if item is None:
                item = SessionMemory(
                    session_id=session_id,
                    workspace_id=workspace_id,
                )
                self._items[session_id] = item
            elif workspace_id is not None:
                item.workspace_id = workspace_id
            item.updated_at = datetime.now(timezone.utc)
            return item

    def set_objective(
        self,
        session_id: str,
        objective: str,
    ) -> SessionMemory:
        with self._lock:
            item = self.get_or_create(session_id)
            item.objective = objective.strip() or None
            item.updated_at = datetime.now(timezone.utc)
            return item

    def remember_fact(
        self,
        session_id: str,
        key: str,
        value: Any,
    ) -> SessionMemory:
        with self._lock:
            item = self.get_or_create(session_id)
            item.facts[key] = value
            item.updated_at = datetime.now(timezone.utc)
            return item

    def remember_focus_column(
        self,
        session_id: str,
        column: str | None,
    ) -> SessionMemory:
        with self._lock:
            item = self.get_or_create(session_id)
            if column:
                cleaned = str(column).strip()
                if cleaned:
                    item.recent_columns = [
                        value
                        for value in item.recent_columns
                        if value.casefold() != cleaned.casefold()
                    ]
                    item.recent_columns.insert(0, cleaned)
                    item.recent_columns = item.recent_columns[:8]
                    item.active_entities["column"] = cleaned
            item.updated_at = datetime.now(timezone.utc)
            return item

    def remember_turn(
        self,
        session_id: str,
        *,
        intent: str,
        entities: dict[str, Any] | None = None,
        result_summary: str | None = None,
    ) -> SessionMemory:
        with self._lock:
            item = self.get_or_create(session_id)
            item.last_intent = intent
            item.last_entities = dict(entities or {})
            item.recent_intents.insert(
                0,
                {
                    "intent": intent,
                    "entities": dict(entities or {}),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            item.recent_intents = item.recent_intents[:10]
            if result_summary:
                item.last_result_summary = result_summary
            item.updated_at = datetime.now(timezone.utc)
            return item

    def record_decision(
        self,
        session_id: str,
        *,
        action: str,
        result: str,
        reversible: bool,
    ) -> SessionMemory:
        with self._lock:
            item = self.get_or_create(session_id)
            item.decisions.append(
                {
                    "action": action,
                    "result": result,
                    "reversible": reversible,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            item.decisions = item.decisions[-30:]
            item.updated_at = datetime.now(timezone.utc)
            return item
