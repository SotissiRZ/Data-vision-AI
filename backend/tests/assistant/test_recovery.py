from app.assistant.models import AgentTurnStep
from app.assistant.recovery import RecoveryPolicy


def test_transient_error_retries_once():
    decision = RecoveryPolicy().decide(
        AgentTurnStep(
            tool="x",
            label="x",
            status="failed",
            error="worker unavailable",
        )
    )
    assert decision.action == "retry_once"


def test_domain_error_stops():
    decision = RecoveryPolicy().decide(
        AgentTurnStep(
            tool="x",
            label="x",
            status="failed",
            error="column age does not exist",
        )
    )
    assert decision.action == "stop"
