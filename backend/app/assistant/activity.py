from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import AssistantEvent, ProactiveAlert, AssistantAction


@dataclass
class ActivitySignal:
    kind: str
    score: float
    explanation: str


class ActivityMonitor:
    """
    Detects semantic signs that the user may be blocked.

    It intentionally does not infer frustration from mouse movement, camera,
    keystroke timing or other invasive telemetry. It relies on meaningful
    application events: repeated failures, repeated invalid attempts and
    loops without progress.
    """

    def __init__(self, max_events: int = 50) -> None:
        self.events: deque[AssistantEvent] = deque(maxlen=max_events)

    def add(self, event: AssistantEvent) -> None:
        self.events.append(event)

    def detect(self, now: datetime | None = None) -> list[ActivitySignal]:
        now = now or datetime.now(timezone.utc)
        window = [
            event
            for event in self.events
            if event.timestamp >= now - timedelta(minutes=5)
        ]

        signals: list[ActivitySignal] = []

        failures = [
            event for event in window
            if event.type in {
                "analysis.failed",
                "visualization.error",
                "transform.failed",
                "ml.training.failed",
                "query.failed",
            }
        ]

        if len(failures) >= 3:
            signatures = Counter(
                (
                    event.type,
                    str(event.payload.get("code") or event.payload.get("reason") or "")
                )
                for event in failures
            )
            (signature, count) = signatures.most_common(1)[0]
            if count >= 2:
                signals.append(
                    ActivitySignal(
                        kind="repeated_failure",
                        score=min(1.0, 0.55 + 0.15 * count),
                        explanation=(
                            f"Le même type d'échec ({signature[0]}) est apparu "
                            f"{count} fois récemment."
                        ),
                    )
                )

        success_types = {
            "analysis.completed",
            "visualization.created",
            "transform.completed",
            "ml.training.completed",
            "query.completed",
            "dataset.loaded",
        }
        latest_success = max(
            (event.timestamp for event in window if event.type in success_types),
            default=None,
        )
        retries = [
            event for event in window
            if event.type.endswith(".retried")
            and (latest_success is None or event.timestamp > latest_success)
        ]
        if len(retries) >= 3:
            signals.append(
                ActivitySignal(
                    kind="retry_loop",
                    score=min(1.0, 0.50 + 0.10 * len(retries)),
                    explanation=(
                        f"{len(retries)} nouvelles tentatives ont été effectuées "
                        "sans signal de réussite associé."
                    ),
                )
            )

        blockers = [
            event for event in window
            if event.type in {
                "analysis.failed", "visualization.error", "transform.failed",
                "ml.training.failed", "query.failed",
            }
            and (latest_success is None or event.timestamp > latest_success)
        ]
        if len(blockers) >= 4:
            screens = Counter(str(event.payload.get("screen") or "") for event in blockers)
            screen, count = screens.most_common(1)[0]
            signals.append(
                ActivitySignal(
                    kind="stalled_workflow",
                    score=min(1.0, 0.60 + 0.08 * count),
                    explanation=(
                        f"{len(blockers)} blocages se sont accumulés sans progression récente"
                        + (f" sur {screen}." if screen else ".")
                    ),
                )
            )

        return signals


def alerts_from_activity(signals: list[ActivitySignal]) -> list[ProactiveAlert]:
    alerts: list[ProactiveAlert] = []
    for signal in signals:
        if signal.score < 0.65:
            continue
        alerts.append(
            ProactiveAlert(
                title="Je peux vous aider à débloquer cette étape",
                message=signal.explanation,
                severity="warning",
                speak=False,
                actionLabel="Diagnostiquer",
                action=AssistantAction(
                    tool="diagnose_analysis_failure",
                    label="Analyser ce qui bloque",
                    risk="read",
                    args={"signal": signal.kind, "score": signal.score},
                ),
            )
        )
    return alerts
