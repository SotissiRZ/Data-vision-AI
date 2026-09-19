from __future__ import annotations

from pathlib import Path

from app.assistant.intent import resolve_intent
from app.assistant.models import AssistantContext
from app.assistant.project_memory import (
    forget_entry,
    get_policy,
    list_entries,
    pin_entry,
    save_artifacts,
    save_policy,
    search_entries,
    should_recall,
    scope_for_context,
    to_session_artifact,
)
from app.core.config import get_settings
from app.services import metadata_store


def _configure(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _ctx(workspace="ws-project", dataset="ds-sales"):
    return AssistantContext(
        workspaceId=workspace,
        activeDatasetId=dataset,
        activeDatasetVersionId="3",
        screen="visual",
        uiState={"datasetName": "sales.csv"},
    )


def _model_artifact(identifier="turn-old:0", model_id="model-xgb"):
    return {
        "id": identifier,
        "kind": "model",
        "reference_name": "Modèle #1",
        "label": "Modèle xgboost",
        "tool": "run_automl",
        "dataset_id": "ds-sales",
        "model_id": model_id,
        "columns": ["Profit"],
        "summary": f"modèle xgboost · variables Profit · model_id={model_id}",
        "metrics": {"r2": 0.84},
        "aliases": ["Modèle #1", "xgboost", model_id, "Profit"],
        "created_at": "2026-09-18T10:00:00+00:00",
        "turn_run_id": "turn-old",
        "params": {"algorithm": "xgboost", "target": "Profit"},
        "raw_rows": [{"Profit": 1}],  # must never be persisted
    }


def test_metadata_schema_contains_governed_project_memory_tables():
    ddl = "\n".join(metadata_store.SCHEMA_SQL)
    assert "assistant_project_memory" in ddl
    assert "assistant_project_memory_policy" in ddl
    assert "UNIQUE(scope_id, artifact_id)" in ddl


def test_project_memory_persists_compact_artifact_and_searches_it(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx()
    scope, workspace, user = scope_for_context(context)
    assert scope == "workspace:ws-project"
    assert workspace == "ws-project"
    assert user is None

    assert save_artifacts(context, "session-old", [_model_artifact()]) == 1
    entries = list_entries(scope)
    assert len(entries) == 1
    assert entries[0]["payload"]["model_id"] == "model-xgb"
    assert "raw_rows" not in entries[0]["payload"]

    results = search_entries(scope, "retrouve le modèle xgboost Profit")
    assert results
    assert results[0]["artifact_id"] == "turn-old:0"


def test_project_memory_can_be_pinned_and_forgotten(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx()
    scope, _, _ = scope_for_context(context)
    save_artifacts(context, "session-old", [_model_artifact()])
    entry = list_entries(scope)[0]

    pinned = pin_entry(scope, entry["id"], True)
    assert pinned is not None and pinned["pinned"] is True
    assert forget_entry(scope, entry["id"]) is True
    assert list_entries(scope) == []


def test_project_memory_policy_can_disable_persistence(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx()
    scope, _, _ = scope_for_context(context)
    policy = save_policy(scope, {"enabled": False, "retention_days": 30, "max_entries": 25})
    assert policy["enabled"] is False
    assert policy["retention_days"] == 30
    assert policy["max_entries"] == 25
    assert save_artifacts(context, "session-old", [_model_artifact()]) == 0
    assert list_entries(scope) == []


def test_project_memory_recall_is_explicit_and_conservative():
    assert should_recall("retrouve l'analyse d'avant", has_session_artifacts=True) is True
    assert should_recall("utilise le modèle", has_session_artifacts=False) is True
    assert should_recall("bonjour", has_session_artifacts=False) is False
    assert should_recall("fais un graphique de Sales", has_session_artifacts=True) is False


def test_project_memory_intent_is_deterministic():
    intent = resolve_intent("quelles sont mes analyses précédentes ?", _ctx())
    assert intent.name == "project_memory"
    assert intent.confidence >= 0.99


def test_project_entry_can_be_hydrated_as_session_artifact(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    context = _ctx()
    scope, _, _ = scope_for_context(context)
    save_artifacts(context, "session-old", [_model_artifact()])
    entry = list_entries(scope)[0]
    artifact = to_session_artifact(entry)
    assert artifact["memory_source"] == "project"
    assert artifact["project_memory_id"] == entry["id"]
    assert artifact["model_id"] == "model-xgb"


def test_frontend_exposes_project_memory_controls():
    root = Path(__file__).resolve().parents[3]
    assistant = (root / "frontend/components/assistant/FloatingDataVisionAssistant.tsx").read_text(encoding="utf-8")
    adapter = (root / "frontend/lib/assistant/orchestrator-adapter.ts").read_text(encoding="utf-8")
    css = (root / "frontend/components/assistant/FloatingDataVisionAssistant.module.css").read_text(encoding="utf-8")
    assert "Mémoire projet" in assistant
    assert "Rappel auto" in assistant
    assert "forgetProjectMemory" in assistant
    assert "/ai/assistant/memory" in adapter
    assert ".projectMemoryItem" in css


def test_enterprise_authenticated_workspace_is_authoritative(monkeypatch):
    import app.assistant.project_memory as project_memory

    class Access:
        workspace_id = "ws-auth"
        user_id = "user-1"

    monkeypatch.setattr(project_memory, "current_access_context", lambda: Access())
    scope, workspace, user = project_memory.scope_for_context(_ctx(workspace="ws-auth"))
    assert scope == "workspace:ws-auth"
    assert workspace == "ws-auth"
    assert user == "user-1"

    import pytest
    with pytest.raises(PermissionError):
        project_memory.scope_for_context(_ctx(workspace="ws-spoofed"))
