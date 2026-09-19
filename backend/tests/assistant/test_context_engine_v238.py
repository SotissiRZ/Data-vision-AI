from __future__ import annotations

from pathlib import Path

from app.assistant.intent import resolve_intent
from app.assistant.memory import SessionMemoryStore
from app.assistant.models import AssistantContext
from app.assistant.planner_runtime import DeterministicPlanner
from app.assistant.project_memory import (
    duplicate_entry,
    get_entry,
    list_entries,
    save_artifacts,
    scope_for_context,
    to_session_artifact,
)
from app.assistant.reference_resolver import resolve_references
from app.core.config import get_settings
from app.services import metadata_store


def _configure(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _ctx(dataset="ds-sales"):
    return AssistantContext(
        workspaceId="ws-replay",
        activeDatasetId=dataset,
        activeDatasetVersionId="4",
        screen="visual",
        uiState={
            "datasetName": "sales.csv",
            "datasetSchema": [
                {"name": "Date", "dtype": "date"},
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
            ],
        },
    )


def _chart_artifact(dataset="ds-sales", column="Sales"):
    return {
        "id": "turn-old:chart",
        "kind": "chart",
        "reference_name": "Graphique #1",
        "label": "Graphique Sales",
        "tool": "create_visualization",
        "dataset_id": dataset,
        "chart_id": "chart-sales",
        "columns": [column],
        "summary": f"visualisation line · variables {column}",
        "aliases": ["Graphique #1", "chart-sales", column],
        "params": {"chart_type": "line", "x": column, "title": "Sales trend"},
        "created_at": "2026-09-18T10:00:00+00:00",
    }


def _memory_with_entry(entry):
    store = SessionMemoryStore()
    artifact = to_session_artifact(entry)
    store.remember_fact("session-new", "recent_artifacts", [artifact])
    return store


def _resolve(message: str, context: AssistantContext, memory: SessionMemoryStore):
    intent = resolve_intent(message, context)
    return resolve_references(
        message=message,
        intent=intent,
        context=context,
        memory=memory.get_or_create("session-new"),
    )


def test_project_memory_recipe_can_be_duplicated_without_touching_source(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx()
    scope, _, _ = scope_for_context(context)
    assert save_artifacts(context, "old-session", [_chart_artifact()]) == 1
    source = list_entries(scope)[0]

    clone = duplicate_entry(scope, source["id"])
    assert clone is not None
    assert clone["id"] != source["id"]
    assert clone["artifact_id"] != source["artifact_id"]
    assert clone["title"].startswith("Copie —")
    assert clone["payload"]["copied_from_project_memory_id"] == source["id"]
    assert get_entry(scope, source["id"])["title"] == source["title"]
    assert len(list_entries(scope)) == 2


def test_project_memory_hydration_exposes_exact_action_alias(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx(); scope, _, _ = scope_for_context(context)
    save_artifacts(context, "old-session", [_chart_artifact()])
    entry = list_entries(scope)[0]
    artifact = to_session_artifact(entry)
    assert f"project-memory:{entry['id']}" in artifact["aliases"]
    assert artifact["project_memory_id"] == entry["id"]


def test_replay_exact_project_memory_recipe_uses_governed_replay_intent(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx(); scope, _, _ = scope_for_context(context)
    save_artifacts(context, "old-session", [_chart_artifact()])
    entry = list_entries(scope)[0]
    memory = _memory_with_entry(entry)

    resolution = _resolve(
        f"Relance cet artefact project-memory:{entry['id']} sur le dataset actif.",
        context,
        memory,
    )
    assert resolution.clarification is None
    assert resolution.intent.name == "replay_artifact"
    assert resolution.intent.entities["replay_tool"] == "create_visualization"
    assert resolution.intent.entities["replay_args"]["chart_type"] == "line"
    assert resolution.intent.entities["replay_args"]["x"] == "Sales"
    assert resolution.intent.entities["replay_mode"] == "active_dataset"

    plan = DeterministicPlanner().plan(
        message="replay",
        intent=resolution.intent,
        context=resolution.context,
        attachment_ids=[],
    )
    assert len(plan) == 1
    assert plan[0].tool == "create_visualization"
    assert plan[0].args["x"] == "Sales"


def test_replay_on_wrong_source_dataset_requires_explicit_active_dataset_choice(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    source_context = _ctx(dataset="ds-old")
    scope, _, _ = scope_for_context(source_context)
    save_artifacts(source_context, "old-session", [_chart_artifact(dataset="ds-old")])
    entry = list_entries(scope)[0]
    memory = _memory_with_entry(entry)
    current = _ctx(dataset="ds-current")

    resolution = _resolve(
        f"Relance cet artefact project-memory:{entry['id']}.",
        current,
        memory,
    )
    assert resolution.clarification is not None
    assert "autre dataset" in resolution.clarification
    assert "dataset actif" in resolution.clarification


def test_replay_on_active_dataset_refuses_missing_columns(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    source_context = _ctx(dataset="ds-old")
    scope, _, _ = scope_for_context(source_context)
    save_artifacts(source_context, "old-session", [_chart_artifact(dataset="ds-old", column="LegacyRevenue")])
    entry = list_entries(scope)[0]
    memory = _memory_with_entry(entry)
    current = _ctx(dataset="ds-current")

    resolution = _resolve(
        f"Relance cet artefact project-memory:{entry['id']} sur le dataset actif.",
        current,
        memory,
    )
    assert resolution.clarification is not None
    assert "colonnes absentes" in resolution.clarification
    assert "LegacyRevenue" in resolution.clarification


def test_planner_refuses_non_allowlisted_replay_tool():
    context = _ctx()
    from app.assistant.models import AgentIntent
    intent = AgentIntent(
        name="replay_artifact",
        confidence=0.999,
        entities={"replay_tool": "delete_column", "replay_args": {"column": "Sales"}},
    )
    assert DeterministicPlanner().plan(
        message="replay",
        intent=intent,
        context=context,
        attachment_ids=[],
    ) == []


def test_frontend_exposes_open_replay_active_and_duplicate_memory_actions():
    root = Path(__file__).resolve().parents[3]
    assistant = (root / "frontend/components/assistant/FloatingDataVisionAssistant.tsx").read_text(encoding="utf-8")
    adapter = (root / "frontend/lib/assistant/orchestrator-adapter.ts").read_text(encoding="utf-8")
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    assert "Ouvrir" in assistant
    assert "Relancer" in assistant
    assert "project-memory:${entry.id}" in assistant
    assert "duplicateProjectMemory" in assistant
    assert "/duplicate" in adapter
    assert "datavision:assistant-navigate" in page


def test_router_duplicate_is_governed_and_audited():
    root = Path(__file__).resolve().parents[2]
    router = (root / "app/assistant/router.py").read_text(encoding="utf-8")
    assert '@router.post("/memory/{entry_id}/duplicate")' in router
    assert "_project_memory_scope_id(manage=True)" in router
    assert "assistant.project_memory.duplicated" in router
