from __future__ import annotations

from dataclasses import dataclass

from .models import AgentTurnStep


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str


class RecoveryPolicy:
    """
    Conservative recovery: only retry explicitly transient failures.

    Domain/data errors are never blindly retried.
    """

    TRANSIENT_MARKERS = (
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "rate limit",
        "worker unavailable",
    )

    def decide(self, step: AgentTurnStep) -> RecoveryDecision:
        if step.status != "failed":
            return RecoveryDecision("none", "L'étape n'est pas en échec.")

        error = (step.error or "").lower()
        if any(marker in error for marker in self.TRANSIENT_MARKERS):
            return RecoveryDecision(
                "retry_once",
                "Erreur transitoire reconnue; une seule nouvelle tentative est autorisée.",
            )

        return RecoveryDecision(
            "stop",
            "L'erreur n'est pas classée transitoire; l'agent ne doit pas réessayer aveuglément.",
        )
