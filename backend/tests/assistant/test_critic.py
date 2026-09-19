from app.assistant.critic import DeterministicCritic
from app.assistant.models import AgentTurnStep


def test_critic_fails_on_failed_step():
    report = DeterministicCritic().review([
        AgentTurnStep(
            tool="profile_dataset",
            label="Profiler",
            status="failed",
            error="boom",
        )
    ])
    assert report.status == "fail"
    assert report.findings[0].code == "STEP_FAILED"


def test_critic_warns_on_confirmation():
    report = DeterministicCritic().review([
        AgentTurnStep(
            tool="export_dataset",
            label="Exporter",
            status="waiting_confirmation",
        )
    ])
    assert report.status == "warning"
