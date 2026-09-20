from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.modeling import get_model_card, train_model
from app.services.xai import (
    generate_counterfactuals,
    model_diagnostics,
    xai_audit,
)


def _use_tmp_models(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)


def _classification_frame(rows: int = 160) -> pd.DataFrame:
    x = np.linspace(-4.0, 4.0, rows)
    z = np.cos(x)
    segment = np.where(x > 0, "east", "west")
    target = np.where(x + 0.35 * z > 0.2, "yes", "no")
    return pd.DataFrame({"x": x, "z": z, "segment": segment, "target": target})


def _regression_frame(rows: int = 160) -> pd.DataFrame:
    x = np.linspace(0.0, 12.0, rows)
    z = np.sin(x)
    segment = np.where(x > 6, "B", "A")
    target = 4.0 * x + 1.5 * z + 2.0
    return pd.DataFrame({"x": x, "z": z, "segment": segment, "target": target})


def test_classification_diagnostics_are_auditable_and_per_class(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = _classification_frame()
    trained = train_model(
        frame,
        "target",
        task="classification",
        algorithm="logistic_regression",
        dataset_context={"id": "cls-v252", "version": 3, "name": "classification.csv"},
    )
    result = model_diagnostics(trained.model_id, frame)
    assert result["provenance"]["model_sha256"]
    assert result["provenance"]["reference_data_sha256"]
    assert len(result["per_class_metrics"]) == 2
    assert len(result["calibration_by_class"]) == 2
    assert 0 <= result["balanced_accuracy"] <= 1
    assert result["permutation_importance"]
    assert all("stability" in row and "sign_consistency" in row and "rank" in row for row in result["permutation_importance"])


def test_xai_audit_persists_stable_summary_in_model_card(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = _regression_frame()
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="random_forest",
        dataset_context={"id": "reg-v252", "version": 7, "name": "regression.csv"},
    )
    row = {"x": 2.0, "z": float(np.sin(2.0)), "segment": "A"}
    first = xai_audit(
        trained.model_id,
        frame,
        row=row,
        pdp_features=["x"],
        include_shap=False,
        persist=True,
    )
    second = xai_audit(
        trained.model_id,
        frame,
        row=row,
        pdp_features=["x"],
        include_shap=False,
        persist=False,
    )
    assert first["status"] == "ok"
    assert first["coverage"]["permutation_importance"] is True
    assert first["coverage"]["local_explanation"] is True
    assert first["coverage"]["partial_dependence"] is True
    assert first["provenance"]["explanation_id"] == second["provenance"]["explanation_id"]
    card = get_model_card(trained.model_id)
    assert card["xai_summary"]["explanation_id"] == first["provenance"]["explanation_id"]
    assert card["explainability"]["xai_audit"] is True


def test_counterfactuals_respect_actionability_constraints(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = _regression_frame()
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={"id": "cf-v252", "version": 1, "name": "counterfactual.csv"},
    )
    row = {"x": 1.0, "z": float(np.sin(1.0)), "segment": "A"}
    result = generate_counterfactuals(
        trained.model_id,
        frame,
        row,
        direction="increase",
        max_changes=2,
        max_results=8,
        immutable_features=["segment"],
        actionable_features=["x", "segment"],
        feature_constraints={"x": {"min": 2.0, "max": 7.0}},
    )
    assert result["constraints_applied"]["immutable_features"] == ["segment"]
    assert result["constraints_applied"]["features_searched"] == ["x"]
    assert result["provenance"]["explanation_id"]
    assert result["counterfactuals"]
    for candidate in result["counterfactuals"]:
        assert "segment" not in candidate["changes"]
        if "x" in candidate["changes"]:
            value = float(candidate["changes"]["x"]["to"])
            assert 2.0 <= value <= 7.0


def test_counterfactual_can_explicitly_produce_no_candidates(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = _regression_frame()
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={"id": "cf-none-v252", "version": 1},
    )
    row = {"x": 1.0, "z": float(np.sin(1.0)), "segment": "A"}
    result = generate_counterfactuals(
        trained.model_id,
        frame,
        row,
        direction="increase",
        immutable_features=["x", "z", "segment"],
    )
    assert result["status"] == "no_candidates"
    assert result["searched_candidates"] == 0
    assert result["counterfactuals"] == []


def test_frontend_and_assistant_expose_xai_v252_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    contracts = (root / "backend/app/assistant/contracts.py").read_text(encoding="utf-8")
    host = (root / "backend/app/assistant/host_v212.py").read_text(encoding="utf-8")
    reports = (root / "backend/app/services/report_builder.py").read_text(encoding="utf-8")
    assert "Audit XAI complet" in page
    assert "Variables immuables" in page
    assert "runModelXAIAudit" in api
    assert '"xai_audit"' in contracts
    assert "xai_audit(" in host
    assert '"xai_summary": card.get("xai_summary")' in reports
