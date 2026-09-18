from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from .executor import GovernedToolExecutor
from .models import ActionRun, AssistantAction, AssistantContext


class ActionRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, ActionRun] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        action: AssistantAction,
        context: AssistantContext,
        session_id: str | None,
    ) -> ActionRun:
        run = ActionRun(
            action=action,
            context=context,
            session_id=session_id,
            reversible=action.risk == "reversible",
        )
        with self._lock:
            self._runs[run.id] = run
        return run.model_copy(deep=True)

    def get(self, run_id: str) -> ActionRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run else None

    def save(self, run: ActionRun) -> ActionRun:
        run.updated_at = datetime.now(timezone.utc)
        with self._lock:
            self._runs[run.id] = run
        return run.model_copy(deep=True)


class ActionLifecycleManager:
    """
    Coordinates proposal, confirmation and execution.

    Production integration must additionally persist the action in the existing
    DataVision audit log and dataset lineage/versioning systems.
    """

    def __init__(
        self,
        *,
        executor: GovernedToolExecutor,
        store: ActionRunStore,
    ) -> None:
        self.executor = executor
        self.store = store

    def propose(
        self,
        *,
        action: AssistantAction,
        context: AssistantContext,
        session_id: str | None,
    ) -> ActionRun:
        run = self.store.create(
            action=action,
            context=context,
            session_id=session_id,
        )

        decision = self.executor.prepare(action, context)
        run.reason = decision.reason

        if decision.status == "deny":
            run.status = "failed"
            run.error = decision.reason
        elif decision.status == "confirmation_required":
            run.status = "waiting_confirmation"
        else:
            run.status = "ready"

        return self.store.save(run)

    def confirm(self, run_id: str, confirmed: bool) -> ActionRun:
        run = self._require(run_id)

        if run.status != "waiting_confirmation":
            raise ValueError("Cette action n'attend pas de confirmation.")

        if not confirmed:
            run.status = "cancelled"
            run.reason = "Action refusée par l'utilisateur."
            return self.store.save(run)

        run.status = "ready"
        run.reason = "Confirmation utilisateur reçue."
        return self.store.save(run)

    def execute(self, run_id: str) -> ActionRun:
        run = self._require(run_id)

        if run.status != "ready":
            raise ValueError(f"Action non exécutable dans l'état {run.status}.")

        run.status = "running"
        self.store.save(run)

        try:
            decision = self.executor.execute(
                run.action,
                run.context,
                confirmed=True,
            )
            if decision.status != "executed":
                run.status = "failed"
                run.error = decision.reason
                return self.store.save(run)

            run.status = "succeeded"
            run.result = decision.result

            # Real host handlers may return an undo/rollback token.
            if isinstance(decision.result, dict):
                rollback_token = decision.result.get("rollback_token")
                if rollback_token:
                    run.rollback_token = str(rollback_token)

            return self.store.save(run)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            return self.store.save(run)

    def mark_rolled_back(self, run_id: str, reason: str | None = None) -> ActionRun:
        run = self._require(run_id)

        if not run.reversible:
            raise ValueError("Cette action n'est pas déclarée réversible.")
        if run.status != "succeeded":
            raise ValueError("Seule une action réussie peut être marquée comme annulée.")

        run.status = "rolled_back"
        run.reason = reason or "Rollback confirmé par le moteur DataVision."
        return self.store.save(run)

    def _require(self, run_id: str) -> ActionRun:
        run = self.store.get(run_id)
        if run is None:
            raise KeyError(f"Action run introuvable : {run_id}")
        return run
