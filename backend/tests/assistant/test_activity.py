from datetime import datetime, timezone

from app.assistant.activity import ActivityMonitor
from app.assistant.models import AssistantEvent


def test_repeated_failure_detected():
    monitor = ActivityMonitor()
    for _ in range(3):
        monitor.add(
            AssistantEvent(
                type="analysis.failed",
                timestamp=datetime.now(timezone.utc),
                payload={"code": "INVALID_TYPE"},
            )
        )

    signals = monitor.detect()
    assert any(signal.kind == "repeated_failure" for signal in signals)


def test_single_failure_not_stuck():
    monitor = ActivityMonitor()
    monitor.add(
        AssistantEvent(
            type="analysis.failed",
            timestamp=datetime.now(timezone.utc),
            payload={"code": "INVALID_TYPE"},
        )
    )
    assert monitor.detect() == []
