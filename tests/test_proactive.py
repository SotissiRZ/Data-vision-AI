from app.assistant.models import AssistantContext, AssistantEvent
from app.assistant.proactive import evaluate_proactive_event


def test_leakage_is_critical_and_spoken():
    alerts = evaluate_proactive_event(
        AssistantEvent(
            type="ml.leakage.detected",
            severity="critical",
            payload={"target": "churn", "feature": "final_status"},
        ),
        AssistantContext(workspaceId="ws_test"),
    )
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].speak is True


def test_high_missing_ratio_is_critical():
    alerts = evaluate_proactive_event(
        AssistantEvent(
            type="dataset.quality.issue",
            payload={"rule": "missing_ratio", "column": "income", "value": 0.62},
        ),
        AssistantContext(workspaceId="ws_test"),
    )
    assert alerts[0].severity == "critical"


def test_small_missing_ratio_is_suggestion():
    alerts = evaluate_proactive_event(
        AssistantEvent(
            type="dataset.quality.issue",
            payload={"rule": "missing_ratio", "column": "income", "value": 0.02},
        ),
        AssistantContext(workspaceId="ws_test"),
    )
    assert alerts[0].severity == "suggestion"
