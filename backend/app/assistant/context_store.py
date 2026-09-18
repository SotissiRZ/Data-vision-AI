from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock

from .models import AssistantContext, AssistantEvent


class InMemoryAssistantContextStore:
    """
    Dev/test store only.

    Enterprise integration should replace this with the existing tenant-aware
    Redis/PostgreSQL infrastructure so that sessions and audit policy remain
    coherent with DataVision.
    """

    def __init__(self, max_events: int = 25) -> None:
        self._max_events = max_events
        self._contexts: dict[str, AssistantContext] = {}
        self._events: dict[str, deque[AssistantEvent]] = defaultdict(
            lambda: deque(maxlen=max_events)
        )
        self._lock = RLock()

    def _key(self, context: AssistantContext) -> str:
        return context.workspaceId or "__anonymous__"

    def update(self, context: AssistantContext, event: AssistantEvent | None = None):
        key = self._key(context)
        with self._lock:
            if event is not None:
                self._events[key].append(event)
            merged = context.model_copy(deep=True)
            merged.recentEvents = list(self._events[key])
            self._contexts[key] = merged
            return merged

    def get(self, workspace_id: str | None) -> AssistantContext | None:
        key = workspace_id or "__anonymous__"
        with self._lock:
            value = self._contexts.get(key)
            return value.model_copy(deep=True) if value else None
