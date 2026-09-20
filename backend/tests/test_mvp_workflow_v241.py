from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def _use_isolated_runtime(tmp_path, monkeypatch):
    from app.core.config import get_settings
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "ai_provider", "disabled")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A", "A", "B", "B", "A", "B"],
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
            "missing": [1.0, None, 3.0, None, 5.0, 6.0],
        }
    )


def _upload(name: str, content: bytes, mime: str) -> str:
    response = client.post(
        "/api/v1/datasets",
        files={"file": (name, io.BytesIO(content), mime)},
    )
    assert response.status_code == 200, response.text
    return response.json()["dataset"]["id"]


def test_mvp_core_workflow_api_end_to_end(tmp_path, monkeypatch):
    """Exercise the priority MVP path through the public API, not private helpers."""
    _use_isolated_runtime(tmp_path, monkeypatch)
    frame = _sample_frame()
    dataset_id = _upload(
        "mvp.csv",
        frame.to_csv(index=False).encode("utf-8"),
        "text/csv",
    )

    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert profile.status_code == 200, profile.text
    assert profile.json()["rows"] == len(frame)
    assert profile.json()["columns_count"] == len(frame.columns)

    quality = client.get(f"/api/v1/datasets/{dataset_id}/quality")
    assert quality.status_code == 200, quality.text
    assert quality.json()["score"] <= 100
    assert quality.json()["issues_count"] >= 1

    transformed = client.post(
        f"/api/v1/datasets/{dataset_id}/transform",
        json={
            "operation": {
                "type": "fill_missing",
                "column": "missing",
                "strategy": "median",
            }
        },
    )
    assert transformed.status_code == 200, transformed.text
    transformed_id = transformed.json()["dataset"]["id"]
    assert transformed.json()["dataset"]["version"] == 2
    assert transformed.json()["quality"]["score"] >= quality.json()["score"]

    versions = client.get(f"/api/v1/datasets/{transformed_id}/versions")
    assert versions.status_code == 200, versions.text
    assert len(versions.json()["versions"]) == 2

    correlations = client.post(
        f"/api/v1/datasets/{transformed_id}/analysis/correlations",
        json={"columns": ["x", "y"], "method": "pearson"},
    )
    assert correlations.status_code == 200, correlations.text
    assert correlations.json()["pairs"][0]["coefficient"] == pytest.approx(1.0)

    visualization = client.post(
        f"/api/v1/datasets/{transformed_id}/visualizations/build",
        json={
            "chart_type": "scatter",
            "x": "x",
            "y": "y",
            "aggregation": "none",
            "bins": 20,
        },
    )
    assert visualization.status_code == 200, visualization.text
    assert visualization.json()["type"] == "scatter"
    assert visualization.json()["n"] == len(frame)

    sql = client.post(
        f"/api/v1/datasets/{transformed_id}/workspace/sql",
        json={
            "sql": 'SELECT "group", AVG(x) AS avg_x FROM dataset GROUP BY "group" ORDER BY "group"',
            "limit": 100,
        },
    )
    assert sql.status_code == 200, sql.text
    assert sql.json()["columns"] == ["group", "avg_x"]
    assert sql.json()["returned_rows"] == 2

    analysis = client.post(
        f"/api/v1/datasets/{transformed_id}/ai/analyze",
        json={
            "question": "Analyse les corrélations entre x et y",
            "variables": ["x", "y"],
            "mode": "fast",
        },
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["intent"] == "correlation"
    assert analysis.json()["critic"]["status"] == "passed"
    assert analysis.json()["provenance"]["llm_used_for_numeric_calculation"] is False

    history = client.get(f"/api/v1/datasets/{transformed_id}/ai/history")
    assert history.status_code == 200, history.text
    assert history.json()["count"] == 1
    assert history.json()["analyses"][0]["session_id"] == analysis.json()["session_id"]

    report = client.post(
        f"/api/v1/datasets/{transformed_id}/reports",
        json={
            "title": "MVP Acceptance",
            "sections": [
                "overview",
                "quality",
                "descriptive",
                "methodology",
                "provenance",
            ],
            "analysis_session_id": analysis.json()["session_id"],
        },
    )
    assert report.status_code == 200, report.text
    report_id = report.json()["id"]

    html_export = client.get(
        f"/api/v1/datasets/{transformed_id}/reports/{report_id}/export/html"
    )
    assert html_export.status_code == 200, html_export.text
    assert "text/html" in html_export.headers["content-type"]
    assert len(html_export.content) > 1000

    pdf_export = client.get(
        f"/api/v1/datasets/{transformed_id}/reports/{report_id}/export/pdf"
    )
    assert pdf_export.status_code == 200, pdf_export.text
    assert pdf_export.headers["content-type"] == "application/pdf"
    assert pdf_export.content.startswith(b"%PDF")


def test_mvp_upload_csv_xlsx_json_runtime(tmp_path, monkeypatch):
    _use_isolated_runtime(tmp_path, monkeypatch)
    frame = _sample_frame().head(3)

    xlsx = io.BytesIO()
    frame.to_excel(xlsx, index=False)
    formats = [
        ("mvp.csv", frame.to_csv(index=False).encode("utf-8"), "text/csv"),
        (
            "mvp.xlsx",
            xlsx.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "mvp.json",
            frame.to_json(orient="records").encode("utf-8"),
            "application/json",
        ),
    ]

    for name, content, mime in formats:
        dataset_id = _upload(name, content, mime)
        response = client.get(f"/api/v1/datasets/{dataset_id}/profile")
        assert response.status_code == 200, (name, response.text)
        assert response.json()["rows"] == len(frame)


def test_mvp_parquet_runtime_or_dependency_contract(tmp_path, monkeypatch):
    """Run Parquet end-to-end when pyarrow exists; otherwise verify the packaged runtime contract."""
    _use_isolated_runtime(tmp_path, monkeypatch)
    frame = _sample_frame().head(3)
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
        storage = (ROOT / "backend/app/services/storage.py").read_text(encoding="utf-8")
        assert "pyarrow==" in requirements
        assert '".parquet"' in storage
        assert "pd.read_parquet" in storage
        pytest.skip("Local validation runtime has no pyarrow; Docker/CI requirements pin it.")

    parquet = io.BytesIO()
    frame.to_parquet(parquet, index=False)
    dataset_id = _upload("mvp.parquet", parquet.getvalue(), "application/octet-stream")
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert profile.status_code == 200, profile.text
    assert profile.json()["rows"] == len(frame)
