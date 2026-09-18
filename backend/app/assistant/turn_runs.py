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
