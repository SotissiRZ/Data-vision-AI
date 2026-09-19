from app.assistant.models import AgentTurnStep
from app.assistant.orchestrator import AgentOrchestrator


def test_success_message_singular():
    steps = [
        AgentTurnStep(
            tool="profile_dataset",
            label="Profilage",
            status="succeeded",
        )
    ]
    message = AgentOrchestrator._success_message(
        "analyze_dataset",
        steps,
    )
    assert message == "Analyse terminée. 1 étape exécutée et validée."
    assert "(s)" not in message


def test_success_message_plural():
    steps = [
        AgentTurnStep(
            tool=f"tool_{i}",
            label=f"Étape {i}",
            status="succeeded",
        )
        for i in range(3)
    ]
    message = AgentOrchestrator._success_message(
        "analyze_dataset",
        steps,
    )
    assert message == "Analyse terminée. 3 étapes exécutées et validées."
    assert "(s)" not in message
