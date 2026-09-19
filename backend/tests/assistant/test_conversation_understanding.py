from app.assistant.host_bridge import DataVisionHostBridges, bind_registry_to_host
from app.assistant.intent import resolve_intent
from app.assistant.models import AgentTurnRequest, AssistantContext
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import build_default_registry


class FakeDataBridge:
    def profile_dataset(self, *, context, **kwargs):
        return {
            "rows": 700,
            "columns_count": 8,
            "duplicates": 0,
            "columns": [],
        }

    def inspect_missing_values(self, *, context, **kwargs):
        return {
            "rows": 700,
            "columns": [
                {"column": "a", "missing": 0},
                {"column": "b", "missing": 0},
            ],
        }

    def apply_reversible_transform(self, *, context, **kwargs):
        return {"status": "ok"}

    def merge_datasets(self, *, context, **kwargs):
        return {"status": "ok"}

    def delete_column(self, *, context, **kwargs):
        return {"status": "ok"}


def build_runtime():
    registry = build_default_registry()
    bind_registry_to_host(
        registry,
        DataVisionHostBridges(data=FakeDataBridge()),
    )
    return build_orchestrator(registry=registry)


def test_active_dataset_does_not_force_analysis_for_unknown_question():
    intent = resolve_intent(
        "tu as accès à internet?",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "capabilities"


def test_results_question_is_detected():
    intent = resolve_intent(
        "où sont les résultats ?",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "show_results"


def test_unknown_question_does_not_trigger_dataset_analysis():
    orchestrator = build_runtime()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Pourquoi le ciel est bleu ?",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "needs_clarification"
    assert response.steps == []
    assert "analyse par défaut" in response.message


def test_analysis_returns_real_result_summary():
    orchestrator = build_runtime()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "completed"
    assert "700 lignes" in response.message
    assert "8 variables" in response.message
    assert "aucune cellule manquante" in response.message
    assert "aucun doublon" in response.message


def test_followup_where_are_results_uses_previous_turn():
    orchestrator = build_runtime()

    first = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert first.status == "completed"

    followup = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="où sont les résultats ?",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert followup.status == "completed"
    assert followup.steps == []
    assert "700 lignes" in followup.message
    assert "8 variables" in followup.message


def test_internet_question_answers_capabilities_without_tools():
    orchestrator = build_runtime()
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="tu as accès à internet?",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "completed"
    assert response.steps == []
    assert "navigation Internet générale" in response.message
