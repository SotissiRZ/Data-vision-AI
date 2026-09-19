from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from .models import AgentTurnRun


class AgentTurnRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, AgentTurnRun] = {}
        self._lock = RLock()

    def create(self, run: AgentTurnRun) -> AgentTurnRun:
        with self._lock:
            self._runs[run.id] = run
        return run.model_copy(deep=True)

    def get(self, run_id: str) -> AgentTurnRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run else None

    def save(self, run: AgentTurnRun) -> AgentTurnRun:
        run.updated_at = datetime.now(timezone.utc)
        with self._lock:
            self._runs[run.id] = run
        return run.model_copy(deep=True)

    def latest_for_session(
        self,
        session_id: str,
        *,
        statuses: set[str] | None = None,
    ) -> AgentTurnRun | None:
        with self._lock:
            items = [
                run
                for run in self._runs.values()
                if run.session_id == session_id
                and (statuses is None or run.status in statuses)
            ]
            if not items:
                return None
            items.sort(
                key=lambda run: (run.updated_at, run.created_at),
                reverse=True,
            )
            return items[0].model_copy(deep=True)
