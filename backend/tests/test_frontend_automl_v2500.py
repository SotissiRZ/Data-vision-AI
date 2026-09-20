from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")


def test_v250_model_studio_exposes_three_automl_tasks_and_experiments():
    for value in ("classification", "regression", "clustering"):
        assert f'<option value="{value}">' in PAGE
    assert "Variables de clustering" in PAGE
    assert "Historique des expériences AutoML" in PAGE
    assert "getAutoMLExperiments" in PAGE
    assert "/models/experiments" in API


def test_v250_sidebar_is_compact_and_expands_on_hover_without_reflow():
    assert "--dv-sidebar-collapsed:82px" in CSS
    assert "--dv-sidebar-expanded:248px" in CSS
    assert ".pro-sidebar:hover,.pro-sidebar:focus-within" in CSS
    assert "grid-template-columns:var(--dv-sidebar-collapsed) minmax(0,1fr)" in CSS
    assert "title={area.label}" in PAGE
    assert "aria-label={area.label}" in PAGE


def test_v250_frontend_api_accepts_clustering_without_target():
    assert "target?: string | null" in API
    assert "'clustering'" in API
    assert "features?: string[] | null" in API
