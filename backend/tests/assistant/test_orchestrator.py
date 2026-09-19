from app.assistant.host_bridge import DataVisionHostBridges, bind_registry_to_host
from app.assistant.models import AgentTurnRequest, AssistantContext
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import build_default_registry


class FakeDataBridge:
    def profile_dataset(self, *, context, **kwargs):
        return {"rows": 100, "columns": 5}

    def inspect_missing_values(self, *, context, **kwargs):
        return {"missing_total": 0}

    def apply_reversible_transform(self, *, context, **kwargs):
        return {"ok": True}

    def merge_datasets(self, *, context, **kwargs):
        return {"ok": True}

    def delete_column(self, *, context, **kwargs):
        return {"ok": True}


def build_test_orchestrator():
    registry = build_default_registry()
    bind_registry_to_host(
        registry,
        DataVisionHostBridges(data=FakeDataBridge()),
    )
    return build_orchestrator(registry=registry)


def test_analyze_dataset_executes_safe_steps():
    orchestrator = build_test_orchestrator()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "completed"
    assert [s.status for s in response.steps] == ["succeeded", "succeeded"]


def test_visualize_without_selection_needs_context():
    orchestrator = build_test_orchestrator()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Fais un graphique",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "needs_clarification"


def test_unknown_without_context_needs_clarification():
    orchestrator = build_test_orchestrator()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Fais quelque chose",
            context=AssistantContext(),
        )
    )
    assert response.status == "needs_clarification"


def test_predict_without_task_needs_clarification():
    orchestrator = build_test_orchestrator()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Je veux prédire la cible revenu",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "needs_clarification"
    assert "classification" in response.message.lower()
