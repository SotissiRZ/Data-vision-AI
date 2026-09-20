from __future__ import annotations

from typing import TYPE_CHECKING

from .models import AgentTurnStep, CriticFinding, CriticReport

if TYPE_CHECKING:
    from .agents import MultiAgentCoordinator


class DeterministicCritic:
    """
    Deterministic critic over execution traces.

    Numerical results remain authoritative in the underlying DataVision tools;
    this critic validates execution invariants and never recomputes metrics.
    """

    reviewed_by = "critic_agent"

    def review(self, steps: list[AgentTurnStep]) -> CriticReport:
        findings: list[CriticFinding] = []

        for step in steps:
            if step.status == "failed":
                findings.append(
                    CriticFinding(
                        severity="critical",
                        code="STEP_FAILED",
                        message=step.error or f"L'étape {step.label} a échoué.",
                        step_id=step.id,
                    )
                )

            if step.status == "waiting_confirmation":
                findings.append(
                    CriticFinding(
                        severity="warning",
                        code="HUMAN_CONFIRMATION_REQUIRED",
                        message=f"L'étape « {step.label} » attend une confirmation humaine.",
                        step_id=step.id,
                    )
                )

            if step.status == "succeeded" and step.result is None:
                findings.append(
                    CriticFinding(
                        severity="warning",
                        code="EMPTY_RESULT",
                        message=f"L'étape « {step.label} » est terminée sans résultat exploitable.",
                        step_id=step.id,
                    )
                )

        if any(f.severity == "critical" for f in findings):
            status = "fail"
        elif findings:
            status = "warning"
        else:
            status = "pass"

        return CriticReport(
            status=status,
            findings=findings,
            reviewed_by="critic_agent",
            checked_step_count=len(steps),
        )


class MultiAgentCritic(DeterministicCritic):
    """Critic Agent that also verifies deterministic specialist delegation."""

    def __init__(self, coordinator: "MultiAgentCoordinator") -> None:
        self.coordinator = coordinator

    def review(self, steps: list[AgentTurnStep]) -> CriticReport:
        base = super().review(steps)
        findings = [*base.findings, *self.coordinator.review_execution(steps)]
        if any(item.severity == "critical" for item in findings):
            status = "fail"
        elif findings:
            status = "warning"
        else:
            status = "pass"
        return CriticReport(
            status=status,
            findings=findings,
            reviewed_by="critic_agent",
            checked_step_count=len(steps),
        )
