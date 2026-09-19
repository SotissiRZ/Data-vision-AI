from __future__ import annotations

from pathlib import Path

from app.assistant.models import AssistantContext
from app.assistant.project_memory import save_artifacts, scope_for_context, search_entries
from app.core.config import get_settings
from app.services import metadata_store


def _configure(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _ctx():
    return AssistantContext(
        workspaceId="ws-semantic",
        activeDatasetId="ds-finance",
        activeDatasetVersionId="1",
        screen="visual",
        uiState={"datasetName": "Financial Sample.xlsx"},
    )


def _artifact(identifier, kind, label, summary, columns, created_at, **extra):
    return {
        "id": identifier,
        "kind": kind,
        "reference_name": label,
        "label": label,
        "tool": extra.pop("tool", "deterministic_tool"),
        "dataset_id": "ds-finance",
        "columns": columns,
        "summary": summary,
        "aliases": extra.pop("aliases", []),
        "created_at": created_at,
        **extra,
    }


def test_semantic_recall_maps_french_business_wording_to_sales(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    ctx = _ctx()
    scope, _, _ = scope_for_context(ctx)
    save_artifacts(ctx, "s1", [_artifact(
        "chart-sales", "chart", "Graphique ventes", "bar chart · Sales par Segment", ["Sales", "Segment"],
        "2025-04-01T10:00:00+00:00", aliases=["Sales", "revenue"]
    )])
    results = search_entries(scope, "retrouve le graphique du chiffre d'affaires", dataset_id="ds-finance")
    assert results and results[0]["artifact_id"] == "chart-sales"
    assert results[0]["search_mode"] == "semantic_local"
    assert results[0]["search_score"] > 0.2
    assert results[0]["match_reasons"]


def test_semantic_recall_understands_profit_model_without_exact_sentence(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    ctx = _ctx(); scope, _, _ = scope_for_context(ctx)
    save_artifacts(ctx, "s1", [_artifact(
        "model-profit", "model", "Modèle XGBoost", "prédiction de Profit avec XGBoost", ["Profit"],
        "2026-02-01T10:00:00+00:00", model_id="model-xgb", aliases=["XGBoost", "Profit"],
        params={"target": "Profit", "algorithm": "xgboost"}
    )])
    results = search_entries(scope, "reprends le modèle qui prédisait les bénéfices")
    assert results and results[0]["artifact_id"] == "model-profit"


def test_semantic_recall_maps_regions_to_geography(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    ctx = _ctx(); scope, _, _ = scope_for_context(ctx)
    save_artifacts(ctx, "s1", [_artifact(
        "chart-geo", "chart", "Carte Geography", "visualisation des ventes par Geography", ["Geography", "Sales"],
        "2026-03-01T10:00:00+00:00", aliases=["Geography", "Sales"]
    )])
    results = search_entries(scope, "retrouve le graphique sur les régions")
    assert results and results[0]["artifact_id"] == "chart-geo"


def test_semantic_recall_prefers_requested_artifact_kind(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    ctx = _ctx(); scope, _, _ = scope_for_context(ctx)
    save_artifacts(ctx, "s1", [
        _artifact("chart-sales", "chart", "Graphique Sales", "Sales par Segment", ["Sales"], "2026-03-01T10:00:00+00:00"),
        _artifact("model-sales", "model", "Modèle Sales", "modèle prédictif Sales", ["Sales"], "2026-03-02T10:00:00+00:00", model_id="m-sales"),
    ])
    results = search_entries(scope, "retrouve le modèle sur les ventes")
    assert results and results[0]["artifact_id"] == "model-sales"


def test_semantic_search_keeps_workspace_scope(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    ctx = _ctx(); scope, _, _ = scope_for_context(ctx)
    save_artifacts(ctx, "s1", [_artifact("a1", "chart", "Graphique Sales", "Sales", ["Sales"], "2026-01-01T10:00:00+00:00")])
    assert search_entries(scope, "ventes")
    assert search_entries("workspace:other", "ventes") == []


def test_frontend_exposes_semantic_memory_search():
    root = Path(__file__).resolve().parents[3]
    component = (root / "frontend/components/assistant/FloatingDataVisionAssistant.tsx").read_text(encoding="utf-8")
    adapter = (root / "frontend/lib/assistant/adapter.ts").read_text(encoding="utf-8")
    css = (root / "frontend/components/assistant/FloatingDataVisionAssistant.module.css").read_text(encoding="utf-8")
    assert "Rechercher dans la mémoire projet" in component
    assert "Recherche sémantique locale" in component
    assert "search_score?: number" in adapter
    assert ".projectMemorySearch" in css


def test_semantic_ranker_does_not_call_external_embedding_provider():
    source = Path(__file__).resolve().parents[2] / "app/assistant/project_memory.py"
    text = source.read_text(encoding="utf-8")
    assert "semantic_local" in text
    assert "openai" not in text.casefold()
    assert "embedding" in text.casefold()  # documented as explicitly not used
