from __future__ import annotations

from .models import AgentTurnStep, CriticFinding, CriticReport


class DeterministicCritic:
    """
    First-pass critic over execution traces.

    A future AI critic may enrich explanations, but deterministic invariants
    remain authoritative.
    """

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

        return CriticReport(status=status, findings=findings)
