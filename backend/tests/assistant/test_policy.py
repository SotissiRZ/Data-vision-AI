from app.assistant.models import AssistantAction, AssistantContext
from app.assistant.policy import evaluate_action_policy


def test_read_action_allowed():
    result = evaluate_action_policy(
        AssistantAction(tool="profile_dataset", label="Profiler", risk="read"),
        AssistantContext(workspaceId="ws_test"),
    )
    assert result.decision == "allow"


def test_destructive_action_needs_confirmation():
    result = evaluate_action_policy(
        AssistantAction(tool="delete_column", label="Supprimer", risk="destructive"),
        AssistantContext(workspaceId="ws_test"),
    )
    assert result.decision == "confirmation_required"


def test_audit_bypass_denied():
    result = evaluate_action_policy(
        AssistantAction(tool="disable_audit_log", label="Désactiver audit"),
        AssistantContext(workspaceId="ws_test"),
    )
    assert result.decision == "deny"
