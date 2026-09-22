from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services.quality_remediation import build_quality_remediation_plan, preview_quality_remediation


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


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A", "A", "B", "B", "B", "B", "B", "B", "B", "B"],
            "amount": [10.0, 10.0, 11.0, None, 12.0, 13.0, 14.0, 15.0, 16.0, 999.0],
            "constant": ["x"] * 10,
        }
    )


def _upload(frame: pd.DataFrame) -> str:
    res = client.post(
        "/api/v1/datasets",
        files={"file": ("quality.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")},
    )
    assert res.status_code == 200, res.text
    return res.json()["dataset"]["id"]


def test_quality_remediation_plan_is_deterministic_and_non_mutating():
    frame = _frame()
    original = frame.copy(deep=True)
    plan1 = build_quality_remediation_plan(frame, dataset_id="ds", version=1)
    plan2 = build_quality_remediation_plan(frame, dataset_id="ds", version=1)
    assert plan1["plan_id"] == plan2["plan_id"]
    assert frame.equals(original)
    assert plan1["action_count"] >= 3
    assert any(a["issue_code"] == "missing_values" and a["operation"]["type"] == "fill_missing" for a in plan1["actions"])
    assert any(a["issue_code"] == "constant_column" and a["review_required"] for a in plan1["actions"])
    assert any(a["issue_code"] == "iqr_outliers" and a["review_required"] for a in plan1["actions"])
    preview = preview_quality_remediation(frame, plan=plan1, action_ids=plan1["default_action_ids"])
    assert preview["after"]["score"] >= preview["before"]["score"]
    assert frame.equals(original)


def test_quality_remediation_api_preview_then_versioned_apply(tmp_path, monkeypatch):
    _use_isolated_runtime(tmp_path, monkeypatch)
    dataset_id = _upload(_frame())

    plan_res = client.get(f"/api/v1/datasets/{dataset_id}/quality/remediation")
    assert plan_res.status_code == 200, plan_res.text
    plan = plan_res.json()
    assert plan["dataset_version"] == 1
    assert plan["default_preview"]["after"]["score"] >= plan["default_preview"]["before"]["score"]

    versions_before = client.get(f"/api/v1/datasets/{dataset_id}/versions").json()["versions"]
    assert len(versions_before) == 1

    selected = list(plan["default_action_ids"])
    assert selected
    preview_res = client.post(
        f"/api/v1/datasets/{dataset_id}/quality/remediation/preview",
        json={"action_ids": selected},
    )
    assert preview_res.status_code == 200, preview_res.text
    assert preview_res.json()["selected_action_ids"] == selected
    assert len(client.get(f"/api/v1/datasets/{dataset_id}/versions").json()["versions"]) == 1

    apply_res = client.post(
        f"/api/v1/datasets/{dataset_id}/quality/remediation/apply",
        json={"action_ids": selected, "expected_plan_id": plan["plan_id"]},
    )
    assert apply_res.status_code == 200, apply_res.text
    body = apply_res.json()
    assert body["dataset"]["version"] == 2
    assert body["dataset"]["parent_id"] == dataset_id
    assert body["dataset"]["operation"]["type"] == "quality_remediation"
    assert body["quality"]["score"] >= plan["quality"]["score"]
    assert body["remediation"]["operation"]["params"]["plan_id"] == plan["plan_id"]


def test_quality_remediation_rejects_stale_plan(tmp_path, monkeypatch):
    _use_isolated_runtime(tmp_path, monkeypatch)
    dataset_id = _upload(_frame())
    plan = client.get(f"/api/v1/datasets/{dataset_id}/quality/remediation").json()
    res = client.post(
        f"/api/v1/datasets/{dataset_id}/quality/remediation/apply",
        json={"action_ids": plan["default_action_ids"], "expected_plan_id": "stale"},
    )
    assert res.status_code == 400
    assert "plan de remédiation a changé" in res.text


def test_v271_assistant_and_frontend_contracts_present():
    tools = (ROOT / "backend/app/assistant/tools.py").read_text(encoding="utf-8")
    planner = (ROOT / "backend/app/assistant/planner_runtime.py").read_text(encoding="utf-8")
    host = (ROOT / "backend/app/assistant/host_v212.py").read_text(encoding="utf-8")
    api = (ROOT / "frontend/lib/api.ts").read_text(encoding="utf-8")
    page = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    assert 'name="plan_quality_remediation"' in tools
    assert 'tool="plan_quality_remediation"' in planner
    assert '"plan_quality_remediation": data.plan_quality_remediation' in host
    assert "getQualityRemediation" in api and "applyQualityRemediation" in api
    assert "Remédiation guidée" in page and "Appliquer dans une nouvelle version" in page
