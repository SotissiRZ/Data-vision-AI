from __future__ import annotations

from pathlib import Path

from app.assistant.artifact_memory import remember_run_artifacts, recent_artifacts, compact_artifacts
from app.assistant.intent import resolve_intent
from app.assistant.memory import SessionMemoryStore
from app.assistant.models import AgentIntent, AgentTurnRun, AgentTurnStep, AssistantContext
from app.assistant.reference_resolver import resolve_references


def _context() -> AssistantContext:
    return AssistantContext(
        workspaceId="ws1",
        activeDatasetId="ds1",
        activeDatasetVersionId="1",
        screen="visual",
        uiState={
            "datasetName": "sales.csv",
            "datasetSchema": [
                {"name": "Date", "dtype": "object"},
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
                {"name": "Margin", "dtype": "float64"},
            ],
        },
    )


def _run(session: str, step: AgentTurnStep) -> AgentTurnRun:
    return AgentTurnRun(
        session_id=session,
        request_message="test",
        context=_context(),
        intent=AgentIntent(name="artifact_context", confidence=0.99),
        steps=[step],
        current_step_index=1,
        status="completed",
    )


def _remember_chart(memory: SessionMemoryStore, chart_id: str, column: str, chart_type: str = "line") -> None:
    remember_run_artifacts(
        memory,
        "s1",
        _run(
            "s1",
            AgentTurnStep(
                tool="create_visualization",
                label=f"Graphique {column}",
                args={"x": column, "chart_type": chart_type},
                status="succeeded",
                result={"chart_type": chart_type, "visualization_id": chart_id},
            ),
        ),
    )


def _remember_model(memory: SessionMemoryStore, model_id: str, algorithm: str, target: str) -> None:
    remember_run_artifacts(
        memory,
        "s1",
        _run(
            "s1",
            AgentTurnStep(
                tool="run_automl",
                label=f"Modèle {algorithm}",
                args={"target": target, "algorithm": algorithm},
                status="succeeded",
                result={"model_id": model_id, "algorithm": algorithm, "r2": 0.8},
            ),
        ),
    )


def _remember_test(memory: SessionMemoryStore, column: str, statistic: float) -> None:
    remember_run_artifacts(
        memory,
        "s1",
        _run(
            "s1",
            AgentTurnStep(
                tool="run_statistical_test",
                label=f"Test {column}",
                args={"x": column, "test": "pearson"},
                status="succeeded",
                result={"test": "pearson", "statistic": statistic, "p_value": 0.02},
            ),
        ),
    )


def _resolve(message: str, memory: SessionMemoryStore):
    context = _context()
    intent = resolve_intent(message, context)
    return resolve_references(
        message=message,
        intent=intent,
        context=context,
        memory=memory.get_or_create("s1"),
    )


def test_stable_kind_ordinals_are_assigned_in_creation_order():
    memory = SessionMemoryStore()
    _remember_chart(memory, "chart-a", "Sales")
    _remember_chart(memory, "chart-b", "Profit")
    _remember_chart(memory, "chart-c", "Margin")
    charts = recent_artifacts(memory.get_or_create("s1"), kind="chart")
    by_id = {item["chart_id"]: item for item in charts}
    assert by_id["chart-a"]["kind_sequence"] == 1
    assert by_id["chart-b"]["kind_sequence"] == 2
    assert by_id["chart-c"]["kind_sequence"] == 3
    assert by_id["chart-b"]["reference_name"] == "Graphique #2"


def test_second_chart_can_be_reused_deterministically():
    memory = SessionMemoryStore()
    _remember_chart(memory, "chart-a", "Sales", "bar")
    _remember_chart(memory, "chart-b", "Profit", "line")
    _remember_chart(memory, "chart-c", "Margin", "scatter")
    resolution = _resolve("refais le deuxième graphique avec Sales", memory)
    assert resolution.clarification is None
    assert resolution.intent.name == "visualize"
    assert resolution.intent.entities["artifact_id"]
    assert resolution.intent.entities["chart_type"] == "line"
    assert resolution.intent.entities["x"] == "Sales"


def test_compare_two_models_by_explicit_ids():
    memory = SessionMemoryStore()
    _remember_model(memory, "model-xgb", "xgboost", "Profit")
    _remember_model(memory, "model-cat", "catboost", "Profit")
    resolution = _resolve("compare le modèle model-xgb au modèle model-cat", memory)
    assert resolution.clarification is None
    assert resolution.intent.name == "artifact_context"
    assert resolution.intent.entities["artifact_action"] == "compare"
    ids = resolution.intent.entities["artifact_ids"]
    artifacts = {item["id"]: item for item in recent_artifacts(memory.get_or_create("s1"))}
    assert {artifacts[value]["model_id"] for value in ids} == {"model-xgb", "model-cat"}


def test_generic_model_reference_is_ambiguous_when_multiple_models_exist():
    memory = SessionMemoryStore()
    _remember_model(memory, "model-xgb", "xgboost", "Profit")
    _remember_model(memory, "model-cat", "catboost", "Profit")
    resolution = _resolve("utilise le modèle pour prédire", memory)
    assert resolution.clarification is not None
    assert "plusieurs modèles" in resolution.clarification
    assert "Modèle #1" in resolution.clarification
    assert "Modèle #2" in resolution.clarification


def test_demonstrative_model_reference_keeps_latest_semantics():
    memory = SessionMemoryStore()
    _remember_model(memory, "model-xgb", "xgboost", "Profit")
    _remember_model(memory, "model-cat", "catboost", "Profit")
    resolution = _resolve("utilise ce modèle pour prédire", memory)
    assert resolution.clarification is None
    assert resolution.context.activeModelId == "model-cat"
    assert resolution.intent.entities["model_id"] == "model-cat"


def test_named_analysis_reference_uses_column_match_not_latest_result():
    memory = SessionMemoryStore()
    _remember_test(memory, "Sales", 0.3)
    _remember_test(memory, "Profit", 0.7)
    resolution = _resolve("reprends l'analyse de Sales", memory)
    assert resolution.clarification is None
    artifact_id = resolution.intent.entities["artifact_id"]
    artifacts = {item["id"]: item for item in recent_artifacts(memory.get_or_create("s1"))}
    assert artifacts[artifact_id]["columns"] == ["Sales"]


def test_compact_artifacts_expose_reference_names_for_ui():
    memory = SessionMemoryStore()
    _remember_chart(memory, "chart-a", "Sales")
    _remember_model(memory, "model-xgb", "xgboost", "Profit")
    compact = compact_artifacts(memory.get_or_create("s1"), limit=8)
    assert all(item.get("reference_name") for item in compact)
    assert any(item.get("reference_name") == "Graphique #1" for item in compact)
    assert any(item.get("reference_name") == "Modèle #1" for item in compact)


def test_frontend_exposes_multi_artifact_catalog():
    root = Path(__file__).resolve().parents[3]
    assistant = (root / "frontend/components/assistant/FloatingDataVisionAssistant.tsx").read_text(encoding="utf-8")
    css = (root / "frontend/components/assistant/FloatingDataVisionAssistant.module.css").read_text(encoding="utf-8")
    assert "Résultats mémorisés" in assistant
    assert "reference_name" in assistant
    assert "le deuxième graphique" in assistant
    assert ".artifactList" in css
    assert ".artifactItem" in css
