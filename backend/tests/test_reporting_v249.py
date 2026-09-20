from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.services.insight_engine import generate_insights
from app.services.report_builder import build_report, export_report, list_reports, validate_report
from app.services.storage import save_dataframe_source


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=16, freq="MS"),
        "segment": ["A", "A", "B", "B"] * 4,
        "sales": [10,12,15,18,20,22,25,28,30,34,38,42,46,50,55,61],
        "margin": [5,6,7,9,10,11,12,14,15,17,19,21,23,25,27,30],
    })


def test_v249_composable_blocks_are_ordered_and_provenanced(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "sales.csv")
    insights = generate_insights(meta["id"], _frame(), max_insights=20, persist=False)["insights"]
    assert insights
    chosen = insights[0]

    import app.services.report_builder as rb
    monkeypatch.setattr(rb, "get_model_card", lambda model_id: {
        "model_id": model_id,
        "dataset": {"id": meta["id"]},
        "task": "regression",
        "algorithm": "random_forest",
        "target": "sales",
        "metrics": {"r2": 0.91, "mae": 2.3},
        "validation": {"split": "holdout"},
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    viz = {
        "id": "viz-1", "title": "Sales trend", "dataset_version": 1,
        "visualization": {"type": "line", "x": "date", "y": "sales", "data": [{"label": "2024-01", "value": 10}, {"label": "2024-02", "value": 12}]},
    }
    monkeypatch.setattr(rb, "list_visualizations", lambda dataset_id: [viz])

    custom = [
        {"id": "custom:text", "type": "text", "title": "Contexte métier", "text": "Revue mensuelle."},
        {"id": "custom:kpi", "type": "kpi", "title": "KPI", "items": [{"label": "Objectif", "value": 95, "unit": "%"}]},
        {"id": "custom:table", "type": "table", "title": "Table", "columns": ["segment", "value"], "rows": [{"segment": "A", "value": 1}]},
        {"id": "custom:insight", "type": "insight", "title": "Insight", "fingerprint": chosen["fingerprint"]},
        {"id": "custom:model", "type": "model", "title": "Modèle", "model_id": "model-1"},
        {"id": "custom:code", "type": "code", "title": "Code", "language": "python", "code": "print('ok')", "output": "ok"},
        {"id": "custom:method", "type": "methodology", "title": "Méthode", "items": ["Holdout temporel"]},
        {"id": "custom:viz", "type": "visualization", "title": "Figure", "visualization_id": "viz-1"},
    ]
    order = ["section:overview", "custom:kpi", "custom:insight", "custom:model", "custom:text", "custom:table", "custom:code", "custom:method", "custom:viz", "section:provenance"]
    report = build_report(meta["id"], "Board pack", ["overview", "provenance"], custom_blocks=custom, block_order=order)
    assert [b["id"] for b in report["blocks"]] == order
    assert report["block_schema_version"] == 1
    assert report["block_count"] == len(order)
    assert all(block.get("provenance") for block in report["blocks"])
    assert report["reproducibility"]["block_provenance"] is True
    assert len(report["content_hash"]) == 64
    assert validate_report(report["id"])["status"] == "pass"


def test_v249_multi_format_exports_include_custom_blocks(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "sales.csv")
    report = build_report(meta["id"], "Export pack", ["overview", "provenance"], custom_blocks=[
        {"id": "custom:text", "type": "text", "title": "Commentaire", "text": "Texte de gouvernance"},
        {"id": "custom:kpi", "type": "kpi", "title": "KPI", "items": [{"label": "SLA", "value": 99.9, "hint": "%"}]},
        {"id": "custom:code", "type": "code", "title": "Code", "language": "sql", "code": "SELECT 1", "output": "1"},
    ])
    for fmt in ("md", "html", "docx", "pdf"):
        path = export_report(report["id"], fmt)
        assert path.exists() and path.stat().st_size > 200
    assert "Texte de gouvernance" in export_report(report["id"], "md").read_text(encoding="utf-8")
    assert b"%PDF" == export_report(report["id"], "pdf").read_bytes()[:4]


def test_v249_report_hash_detects_tampering(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "sales.csv")
    report = build_report(meta["id"], "Integrity", ["overview", "provenance"])
    path = tmp_path / "reports" / f"{report['id']}.json"
    payload = path.read_text(encoding="utf-8").replace("Integrity", "Tampered", 1)
    path.write_text(payload, encoding="utf-8")
    result = validate_report(report["id"])
    assert result["status"] == "fail"
    assert any("Hash" in msg for msg in result["errors"])


def test_v249_report_list_exposes_block_count_and_hash(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    meta = save_dataframe_source(_frame(), "sales.csv")
    report = build_report(meta["id"], "Listed", ["overview"], custom_blocks=[{"id":"custom:t","type":"text","title":"T","text":"x"}])
    rows = list_reports(meta["id"])
    row = next(x for x in rows if x["id"] == report["id"])
    assert row["block_count"] == 2
    assert row["content_hash"] == report["content_hash"]


def test_v249_report_export_route_uses_publication_gate():
    route = (Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "datasets.py").read_text(encoding="utf-8")
    assert "publication_gate(ctx.workspace_id, dataset_id)" in route
    assert "Export bloqué par le Data Reliability Gate" in route


def test_v249_report_agent_contract_exposes_only_real_formats_and_composable_blocks():
    from app.assistant.contracts import GenerateReportArgs
    schema = GenerateReportArgs.model_json_schema()
    fmt = schema["properties"]["format"]
    assert set(fmt.get("enum", [])) == {"pdf", "docx", "html", "markdown"}
    assert "custom_blocks" in schema["properties"]
    assert "block_order" in schema["properties"]
