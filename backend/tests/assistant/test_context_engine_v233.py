from __future__ import annotations

from app.assistant.artifact_memory import extract_run_artifacts, remember_run_artifacts, recent_artifacts, project_artifacts_for_model
from app.assistant.conversation import ConversationalResponder
from app.assistant.memory import SessionMemoryStore
from app.assistant.persistent_memory import PersistentSessionMemoryStore
from app.services import metadata_store
from app.assistant.models import AgentIntent, AgentTurnRun, AgentTurnStep, AssistantContext
from app.assistant.reference_resolver import resolve_references
from app.assistant.turn_runs import AgentTurnRunStore


def _context(model_id: str | None = None):
    return AssistantContext(
        workspaceId="ws1",
        activeDatasetId="ds1",
        activeDatasetVersionId="3",
        activeModelId=model_id,
        screen="visual",
        uiState={
            "datasetName": "sales.csv",
            "datasetSchema": [
                {"name": "Date", "dtype": "object"},
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
            ],
        },
    )


def _run(*steps: AgentTurnStep, intent: str = "visualize"):
    return AgentTurnRun(
        session_id="s1",
        request_message="test",
        context=_context(),
        intent=AgentIntent(name=intent, confidence=0.99),
        steps=list(steps),
        current_step_index=len(steps),
        status="completed",
    )


def test_extracts_compact_chart_and_model_artifacts():
    run = _run(
        AgentTurnStep(
            tool="create_visualization",
            label="Créer graphique",
            args={"x": "Sales", "chart_type": "line"},
            status="succeeded",
            result={"chart_type": "line", "visualization_id": "chart-1"},
        ),
        AgentTurnStep(
            tool="run_automl",
            label="AutoML",
            args={"target": "Profit"},
            status="succeeded",
            result={"model_id": "model-1", "algorithm": "xgboost", "r2": 0.91},
        ),
    )
    artifacts = extract_run_artifacts(run)
    assert len(artifacts) == 2
    assert artifacts[0]["kind"] == "chart"
    assert artifacts[0]["chart_id"] == "chart-1"
    assert artifacts[0]["columns"] == ["Sales"]
    assert artifacts[1]["kind"] == "model"
    assert artifacts[1]["model_id"] == "model-1"
    assert artifacts[1]["metrics"]["r2"] == 0.91


def test_refais_ce_graphique_reuses_chart_type_and_new_column():
    memory = SessionMemoryStore()
    run = _run(
        AgentTurnStep(
            tool="create_visualization",
            label="Créer graphique",
            args={"x": "Sales", "chart_type": "line"},
            status="succeeded",
            result={"chart_type": "line", "visualization_id": "chart-1"},
        )
    )
    remember_run_artifacts(memory, "s1", run)
    resolution = resolve_references(
        message="refais ce graphique avec Profit",
        intent=AgentIntent(name="artifact_context", confidence=0.997),
        context=_context(),
        memory=memory.get_or_create("s1"),
    )
    assert resolution.intent.name == "visualize"
    assert resolution.intent.entities["chart_type"] == "line"
    assert resolution.intent.entities["x"] == "Profit"
    assert resolution.inherited is True


def test_utilise_ce_modele_pour_predire_restores_model_context():
    memory = SessionMemoryStore()
    run = _run(
        AgentTurnStep(
            tool="run_automl",
            label="AutoML",
            args={"target": "Profit"},
            status="succeeded",
            result={"model_id": "model-42", "algorithm": "catboost", "r2": 0.88},
        ),
        intent="predict_target",
    )
    remember_run_artifacts(memory, "s1", run)
    resolution = resolve_references(
        message="utilise ce modèle pour prédire",
        intent=AgentIntent(name="artifact_context", confidence=0.997),
        context=_context(),
        memory=memory.get_or_create("s1"),
    )
    assert resolution.intent.name == "artifact_context"
    assert resolution.intent.entities["artifact_action"] == "reuse_model"
    assert resolution.context.activeModelId == "model-42"
    assert resolution.intent.entities["model_id"] == "model-42"

    response = ConversationalResponder(AgentTurnRunStore(), memory).respond(
        session_id="s1",
        message="utilise ce modèle pour prédire",
        intent=resolution.intent,
        context=resolution.context,
    )
    assert response is not None
    assert "model-42" in response.message
    assert "ne vais pas inventer" in response.message


def test_compare_result_with_previous_uses_common_metrics():
    memory = SessionMemoryStore()
    run1 = _run(
        AgentTurnStep(
            tool="run_statistical_test",
            label="Test A",
            args={"x": "Sales"},
            status="succeeded",
            result={"test": "pearson", "statistic": 0.4, "p_value": 0.03},
        ),
        intent="compare_groups",
    )
    remember_run_artifacts(memory, "s1", run1)
    run2 = _run(
        AgentTurnStep(
            tool="run_statistical_test",
            label="Test B",
            args={"x": "Profit"},
            status="succeeded",
            result={"test": "pearson", "statistic": 0.7, "p_value": 0.01},
        ),
        intent="compare_groups",
    )
    remember_run_artifacts(memory, "s1", run2)
    resolution = resolve_references(
        message="compare ce résultat au précédent",
        intent=AgentIntent(name="artifact_context", confidence=0.997),
        context=_context(),
        memory=memory.get_or_create("s1"),
    )
    assert resolution.intent.name == "artifact_context"
    assert len(resolution.intent.entities["artifact_ids"]) == 2

    response = ConversationalResponder(AgentTurnRunStore(), memory).respond(
        session_id="s1",
        message="compare ce résultat au précédent",
        intent=resolution.intent,
        context=resolution.context,
    )
    assert response is not None
    assert "Comparaison déterministe" in response.message
    assert "p_value" in response.message


def test_artifacts_are_kept_in_compact_memory():
    memory = SessionMemoryStore()
    run = _run(
        AgentTurnStep(
            tool="create_visualization",
            label="Créer graphique",
            args={"x": "Sales"},
            status="succeeded",
            result={"chart_type": "bar", "visualization_id": "chart-1"},
        )
    )
    remember_run_artifacts(memory, "s1", run)
    artifacts = recent_artifacts(memory.get_or_create("s1"))
    assert len(artifacts) == 1
    assert artifacts[0]["dataset_id"] == "ds1"


def test_external_projection_redacts_column_names():
    memory = SessionMemoryStore()
    run = _run(
        AgentTurnStep(
            tool="run_statistical_test",
            label="Test",
            args={"x": "Sales"},
            status="succeeded",
            result={"test": "pearson", "statistic": 0.5, "p_value": 0.02},
        ),
        intent="compare_groups",
    )
    remember_run_artifacts(memory, "s1", run)
    projected = project_artifacts_for_model(
        memory.get_or_create("s1"),
        external=True,
        include_column_names_external=False,
    )
    assert projected
    assert "columns" not in projected[0]
    assert "Sales" not in projected[0]["summary"]



def test_explique_ce_modele_routes_to_xai_intent():
    memory = SessionMemoryStore()
    run = _run(
        AgentTurnStep(
            tool="run_automl",
            label="AutoML",
            args={"target": "Profit"},
            status="succeeded",
            result={"model_id": "model-xai", "algorithm": "xgboost", "r2": 0.9},
        ),
        intent="predict_target",
    )
    remember_run_artifacts(memory, "s1", run)
    resolution = resolve_references(
        message="explique ce modèle",
        intent=AgentIntent(name="artifact_context", confidence=0.997),
        context=_context(),
        memory=memory.get_or_create("s1"),
    )
    assert resolution.intent.name == "explain_model"
    assert resolution.context.activeModelId == "model-xai"



def test_persistent_dataset_switch_invalidates_artifact_memory(monkeypatch):
    rows: dict[str, dict] = {}

    def fake_fetch_one(_sql, params=None):
        row = rows.get((params or {}).get("session_id"))
        if row is None:
            return None
        return {
            "session_id": row.get("session_id"),
            "workspace_id": row.get("workspace_id"),
            "active_entities_json": row.get("active_entities_json", "{}"),
            "facts_json": row.get("facts_json", "{}"),
            "decisions_json": row.get("decisions_json", "[]"),
            "last_intent": row.get("last_intent"),
            "last_entities_json": row.get("last_entities_json", "{}"),
            "recent_columns_json": row.get("recent_columns_json", "[]"),
            "recent_intents_json": row.get("recent_intents_json", "[]"),
            "last_result_summary": row.get("last_result_summary"),
            "updated_at": row.get("updated_at"),
        }

    def fake_execute(_sql, params=None):
        payload = dict(params or {})
        sid = payload.get("session_id")
        if sid:
            rows[sid] = payload

    monkeypatch.setattr(metadata_store, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(metadata_store, "execute", fake_execute)

    store = PersistentSessionMemoryStore()
    store.sync_context("switch-artifacts", _context())
    run = _run(
        AgentTurnStep(
            tool="create_visualization",
            label="Créer graphique",
            args={"x": "Sales"},
            status="succeeded",
            result={"chart_type": "bar", "visualization_id": "chart-1"},
        )
    )
    remember_run_artifacts(store, "switch-artifacts", run)
    assert recent_artifacts(store.get_or_create("switch-artifacts"))

    changed = _context()
    changed.activeDatasetId = "ds2"
    store.sync_context("switch-artifacts", changed)
    assert recent_artifacts(store.get_or_create("switch-artifacts")) == []

