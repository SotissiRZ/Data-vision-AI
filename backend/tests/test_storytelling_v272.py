from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.core.config import get_settings
from app.services.report_builder import (
    build_report,
    export_report,
    get_report_publication,
    publish_report,
    validate_report,
)
from app.services.storage import save_dataframe_source
from app.services.storytelling import build_story_blueprint


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=24, freq="MS"),
        "segment": ["A", "B", "C"] * 8,
        "sales": [10,12,14,13,16,20,18,21,26,24,28,31,30,34,38,37,41,45,44,48,52,50,55,60],
        "margin": [2,3,4,3,5,7,6,8,10,9,11,12,11,13,15,14,16,18,17,19,21,20,22,24],
    })


def test_v272_story_blueprint_is_multi_page_and_fully_evidenced(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "story.csv")

    story = build_story_blueprint(
        meta["id"],
        audience="executive",
        objective="Préparer un comité mensuel",
        tone="balanced",
        max_pages=6,
    )

    assert story["engine"] == "datavision_storytelling_v272"
    assert 3 <= story["page_count"] <= 6
    assert story["proof_coverage"] == 1.0
    assert story["claim_count"] >= 4
    assert story["evidence_count"] >= 2
    evidence_ids = {item["id"] for item in story["evidence"]}
    assert evidence_ids
    for page in story["pages"]:
        assert page["headline"]
        assert page["proof_coverage"] == 1.0
        for claim in page["claims"]:
            assert claim["causal_claim"] is False
            assert claim["evidence_ids"]
            assert set(claim["evidence_ids"]) <= evidence_ids
    assert story["governance"]["numeric_calculation_by_llm"] is False
    assert story["governance"]["human_decision_required"] is True


def test_v272_report_auto_story_becomes_story_pages_with_exports(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "story-report.csv")

    report = build_report(
        meta["id"],
        "Story pack",
        ["executive_summary", "analytical_story", "limitations", "methodology", "provenance"],
        auto_story=True,
        story_audience="operations",
        story_objective="Identifier les signaux et actions prioritaires",
        story_tone="concise",
        story_max_pages=5,
    )

    pages = [block for block in report["blocks"] if block["type"] == "story_page"]
    assert len(pages) == report["story_blueprint"]["page_count"]
    assert len(pages) >= 3
    compat = [block for block in report["blocks"] if block["type"] == "analytical_story"]
    assert len(compat) == 1
    assert compat[0].get("render") is False
    assert compat[0].get("compatibility", {}).get("legacy_contract") == "v1.20"
    assert report["story_blueprint"]["proof_coverage"] == 1.0
    assert report["intelligence"]["story_audience"] == "operations"
    assert validate_report(report["id"])["status"] == "pass"

    md = export_report(report["id"], "md").read_text(encoding="utf-8")
    html = export_report(report["id"], "html").read_text(encoding="utf-8")
    assert "Claims et preuves" in md
    assert "Preuves" in md
    assert "story-claim" in html
    assert export_report(report["id"], "docx").stat().st_size > 500
    assert export_report(report["id"], "pdf").read_bytes()[:4] == b"%PDF"


def test_v272_manual_story_mode_preserves_legacy_analytical_story(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "legacy-story.csv")
    report = build_report(meta["id"], "Manual", ["analytical_story"], auto_story=False)
    assert any(block["type"] == "analytical_story" for block in report["blocks"])
    assert report["story_blueprint"] is None


def test_v272_publication_receipt_is_immutable_and_idempotent(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "publish.csv")
    report = build_report(meta["id"], "Governed story", ["analytical_story", "provenance"], auto_story=True)

    gate = {"allowed": True, "policy": "test", "blockers": [], "warnings": []}
    first = publish_report(report["id"], visibility="workspace", actor_id="user-1", workspace_id="ws-1", governance_gate=gate)
    second = publish_report(report["id"], visibility="external", actor_id="user-2", workspace_id="ws-1", governance_gate=gate)
    assert first == second
    assert first["status"] == "published"
    assert first["immutable_report"] is True
    assert first["report_content_hash"] == report["content_hash"]
    assert len(first["receipt_hash"]) == 64
    assert get_report_publication(report["id"])["publication_id"] == first["publication_id"]


def test_v272_publication_refuses_blocking_gate(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "blocked.csv")
    report = build_report(meta["id"], "Blocked", ["provenance"])
    with pytest.raises(PermissionError):
        publish_report(
            report["id"],
            governance_gate={"allowed": False, "blockers": [{"name": "Critical contract"}]},
        )


def test_v272_api_exposes_story_preview_and_governed_publish_routes():
    route = (Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "datasets.py").read_text(encoding="utf-8")
    assert '/{dataset_id}/storytelling/preview' in route
    assert '/{dataset_id}/reports/{report_id}/publish' in route
    assert 'publication_gate(ctx.workspace_id, dataset_id)' in route
    assert 'story_audience=request.story_audience' in route


def test_v272_assistant_report_contract_supports_story_controls():
    from app.assistant.contracts import GenerateReportArgs

    schema = GenerateReportArgs.model_json_schema()["properties"]
    assert set(schema["story_audience"].get("enum", [])) == {"executive", "operations", "analyst", "general"}
    assert set(schema["story_tone"].get("enum", [])) == {"concise", "balanced", "detailed"}
    assert schema["story_max_pages"]["minimum"] == 3
    assert schema["story_max_pages"]["maximum"] == 8


def test_v272_frontend_exposes_storytelling_and_publication_controls():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "Data Storytelling avancé" in page
    assert "Prévisualiser la trame" in page
    assert "PUBLICATION GOUVERNÉE" in page
    assert "story_audience:storyAudience" in page
    assert "previewStorytelling" in api
    assert "publishReport" in api
    assert "/storytelling/preview" in api
    assert "/publish" in api
