from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.automl_engine import audit_automl_safety, run_automl_experiment
from app.services.ml_guardrails import assess_overfitting


def _imbalanced_frame(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(51)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = np.array(["minor"] * 24 + ["major"] * (n - 24), dtype=object)
    rng.shuffle(target)
    return pd.DataFrame({"record_id": [f"R-{i:04d}" for i in range(n)], "x1": x1, "x2": x2, "target": target})


def _temporal_frame(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(52)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = np.where(x1 + x2 > 0, "yes", "no")
    return pd.DataFrame({"event_date": dates, "x1": x1, "x2": x2, "target": target})


def test_v251_target_copy_is_blocking():
    df = _imbalanced_frame()
    df["target_copy"] = df["target"]
    audit = audit_automl_safety(df, target="target", task="classification", features=["x1", "x2", "target_copy"])
    assert audit["status"] == "blocked"
    assert any(x["code"] == "target_copy_leakage" and x["severity"] == "blocking" for x in audit["findings"])
    try:
        run_automl_experiment(df, target="target", task="classification", features=["x1", "x2", "target_copy"], tune=False, max_candidates=2)
    except ValueError as exc:
        assert "ML Safety bloque" in str(exc)
    else:
        raise AssertionError("Une copie directe de la cible doit bloquer AutoML")


def test_v251_identifier_exclusion_and_metric_governance():
    df = _imbalanced_frame()
    audit = audit_automl_safety(df, target="target", task="classification", primary_metric="accuracy")
    assert audit["metric_policy"]["effective"] == "balanced_accuracy"
    assert audit["metric_policy"]["overridden"] is True
    excluded = {x["column"]: x["reason"] for x in audit["excluded_features"]}
    assert excluded["record_id"] == "identifier_or_quasi_unique"
    assert any(x["code"] == "class_imbalance" for x in audit["findings"])


def test_v251_temporal_split_is_enforced_and_test_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = _temporal_frame()
    out = run_automl_experiment(
        df, target="target", task="classification", primary_metric="balanced_accuracy",
        split_strategy="auto", time_column="event_date", tune=False, max_candidates=2,
        dataset_context={"id": "temporal-ds", "version": 1},
    )
    split = out["split_audit"]
    assert split["strategy"] == "temporal"
    assert split["time_column"] == "event_date"
    assert split["disjoint"] is True
    assert split["final_test_isolated"] is True
    assert split["test_used_for_selection"] is False
    assert split["test_used_for_tuning"] is False
    excluded = {x["column"]: x["reason"] for x in out["safety_audit"]["excluded_features"]}
    assert excluded["event_date"] == "split_only_time_column"
    assert out["model_card"]["validation_strategy"]["strategy"] == "temporal"
    assert out["model_card"]["validation_strategy"]["split_audit"]["index_hashes"]["test"]


def test_v251_explicit_random_split_keeps_warning_for_temporal_signal():
    df = _temporal_frame()
    audit = audit_automl_safety(df, target="target", task="classification", split_strategy="random", time_column="event_date")
    assert audit["split_policy"]["strategy"] == "random"
    assert any(x["code"] == "temporal_signal_present" for x in audit["findings"])


def test_v251_small_samples_are_blocked_before_training():
    df = _temporal_frame(30)
    audit = audit_automl_safety(df, target="target", task="classification")
    assert audit["status"] == "blocked"
    assert any(x["code"] == "sample_too_small" for x in audit["findings"])


def test_v251_overfitting_assessment_is_train_validation_only():
    risk = assess_overfitting({"balanced_accuracy": 0.99}, {"balanced_accuracy": 0.71}, "balanced_accuracy")
    assert risk["status"] == "risk"
    assert risk["severity"] == "high"
    assert risk["gap"] > 0.15
    stable = assess_overfitting({"rmse": 10.0}, {"rmse": 11.0}, "rmse")
    assert stable["status"] == "ok"


def test_v251_api_and_assistant_contract_expose_safety_controls():
    from app.api.routes.datasets import AutoMLRequest, BenchmarkRequest, MLSafetyAuditRequest
    a = AutoMLRequest.model_json_schema()["properties"]
    b = BenchmarkRequest.model_json_schema()["properties"]
    c = MLSafetyAuditRequest.model_json_schema()["properties"]
    assert "split_strategy" in a and "time_column" in a
    assert "split_strategy" in b and "time_column" in b
    assert "split_strategy" in c and "time_column" in c
    root = Path(__file__).resolve().parents[2]
    routes = (root / "backend/app/api/routes/datasets.py").read_text(encoding="utf-8")
    bridge = (root / "backend/app/assistant/host_v212.py").read_text(encoding="utf-8")
    contracts = (root / "backend/app/assistant/contracts.py").read_text(encoding="utf-8")
    assert '/models/safety-audit' in routes
    assert 'split_strategy="temporal" if validation == "time_split"' in bridge
    assert 'time_column: str | None = None' in contracts


def test_v251_frontend_exposes_preflight_safety_audit_and_split_controls():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    assert "Auditer ML Safety" in page
    assert "splitStrategy" in page
    assert "Colonne temporelle" in page
    assert "overfitting_assessment" in page
    assert "runMLSafetyAudit" in api

def test_v251_temporal_split_blocks_single_class_periods():
    n = 100
    df = pd.DataFrame({
        "event_date": pd.date_range("2025-01-01", periods=n, freq="D"),
        "x": np.linspace(0, 1, n),
        "target": ["old"] * 70 + ["new"] * 30,
    })
    audit = audit_automl_safety(
        df, target="target", task="classification", split_strategy="temporal", time_column="event_date",
    )
    assert audit["status"] == "blocked"
    assert any(x["code"] == "temporal_class_coverage" for x in audit["findings"])
