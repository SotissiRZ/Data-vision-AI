import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.modeling import train_model
from app.services.responsible_ai import (
    fairness_report,
    model_risk_assessment,
    population_drift,
    responsible_ai_gate,
    persist_responsible_ai_summary,
)


def _tmp_models(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)


def classification_frame(rows=200, include_group_feature=False):
    half = rows // 2
    group = np.array(["A"] * half + ["B"] * (rows - half))
    x = np.concatenate([
        np.linspace(-3.0, 0.2, half),
        np.linspace(-0.2, 3.0, rows - half),
    ])
    target = np.where(x > 0, "yes", "no")
    frame = pd.DataFrame({"x": x, "group": group, "target": target})
    if not include_group_feature:
        # The audit column can be absent from the model features by training on a copy
        # where the model sees only x + target, while the returned audit frame keeps group.
        return frame
    return frame


def regression_frame(rows=180):
    half = rows // 2
    group = np.array(["A"] * half + ["B"] * (rows - half))
    x = np.linspace(0, 10, rows)
    noise = np.concatenate([
        np.zeros(half),
        np.linspace(-4, 4, rows - half),
    ])
    target = 3.0 * x + 2.0 + noise
    return pd.DataFrame({"x": x, "group": group, "target": target})


def _train_without_group(frame, *, task, algorithm, dataset_id):
    return train_model(
        frame[["x", "target"]],
        "target",
        task=task,
        algorithm=algorithm,
        dataset_context={"id": dataset_id, "version": 1, "name": f"{dataset_id}.csv"},
    )


def test_classification_fairness_reports_group_metrics(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    frame = classification_frame()
    trained = _train_without_group(
        frame,
        task="classification",
        algorithm="logistic_regression",
        dataset_id="fair-class",
    )

    report = fairness_report(
        trained.model_id,
        frame,
        protected_columns=["group"],
        positive_label="yes",
        mode="separate",
        min_group_size=10,
    )

    assert report["task"] == "classification"
    assert report["evaluation_source"] == "final_test_holdout"
    assert report["positive_label"] == "yes"
    assert len(report["reports"]) == 1
    groups = report["reports"][0]["groups"]
    assert {row["group"] for row in groups} == {"A", "B"}
    assert all("selection_rate" in row for row in groups)
    parity = report["reports"][0]["parity_metrics"]
    assert parity["demographic_parity_difference"] is not None
    assert parity["selection_rate_ratio"] is not None
    assert report["protected_feature_usage"] == []


def test_gate_uses_only_organization_thresholds(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    frame = classification_frame()
    trained = _train_without_group(
        frame,
        task="classification",
        algorithm="logistic_regression",
        dataset_id="gate-class",
    )

    advisory = responsible_ai_gate(
        trained.model_id,
        frame,
        protected_columns=["group"],
        positive_label="yes",
        min_group_size=10,
        policy={},
    )
    assert advisory["allowed"] is True
    assert advisory["checks"] == []

    blocking = responsible_ai_gate(
        trained.model_id,
        frame,
        protected_columns=["group"],
        positive_label="yes",
        min_group_size=10,
        policy={"max_demographic_parity_difference": 0.0},
    )
    assert blocking["allowed"] is False
    assert any(
        item["code"] == "threshold_failed:demographic_parity_difference"
        for item in blocking["blockers"]
    )
    assert blocking["policy_source"] == "organization_defined_thresholds"


def test_protected_attribute_usage_is_flagged(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    frame = classification_frame(include_group_feature=True)
    trained = train_model(
        frame,
        "target",
        task="classification",
        algorithm="logistic_regression",
        dataset_context={"id": "protected-feature", "version": 1, "name": "pf.csv"},
    )
    report = fairness_report(
        trained.model_id,
        frame,
        protected_columns=["group"],
        positive_label="yes",
        min_group_size=10,
    )
    assert report["protected_feature_usage"] == ["group"]
    assert any(
        warning["code"] == "protected_attribute_used_as_feature"
        for warning in report["warnings"]
    )


def test_regression_group_error_metrics_and_risk(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    frame = regression_frame()
    trained = _train_without_group(
        frame,
        task="regression",
        algorithm="linear_regression",
        dataset_id="fair-reg",
    )
    report = fairness_report(
        trained.model_id,
        frame,
        protected_columns=["group"],
        mode="separate",
        min_group_size=10,
    )
    parity = report["reports"][0]["parity_metrics"]
    assert parity["mae_difference"] is not None
    assert parity["rmse_difference"] is not None

    risk = model_risk_assessment(trained.model_id, fairness=report)
    assert risk["risk_level"] in {"low", "medium", "high", "critical"}
    assert "interpretation" in risk


def test_population_drift_tracks_representation_shift(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    reference = classification_frame(200)
    trained = _train_without_group(
        reference,
        task="classification",
        algorithm="logistic_regression",
        dataset_id="drift-ref",
    )
    current = reference.copy()
    current.loc[:149, "group"] = "B"
    current.loc[150:, "group"] = "A"

    drift = population_drift(
        trained.model_id,
        reference,
        current,
        protected_columns=["group"],
        positive_label="yes",
        mode="separate",
        min_group_size=10,
    )
    view = drift["representation_drift"][0]
    assert view["max_absolute_share_shift"] > 0
    assert drift["labels_available_in_current"] is True
    assert drift["current_performance"] is not None


def test_persist_summary_updates_model_card(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    frame = classification_frame()
    trained = _train_without_group(
        frame,
        task="classification",
        algorithm="logistic_regression",
        dataset_id="persist-fair",
    )
    report = fairness_report(
        trained.model_id,
        frame,
        protected_columns=["group"],
        positive_label="yes",
        min_group_size=10,
    )
    risk = model_risk_assessment(trained.model_id, fairness=report)
    card = persist_responsible_ai_summary(
        trained.model_id,
        fairness=report,
        risk=risk,
    )
    assert card["fairness"]["status"] == "evaluated"
    assert card["responsible_ai"]["risk"]["risk_level"] == risk["risk_level"]


def test_fairness_requires_explicit_group_selection(tmp_path, monkeypatch):
    _tmp_models(tmp_path, monkeypatch)
    frame = classification_frame()
    trained = _train_without_group(
        frame,
        task="classification",
        algorithm="logistic_regression",
        dataset_id="explicit-only",
    )
    try:
        fairness_report(
            trained.model_id,
            frame,
            protected_columns=[],
        )
    except ValueError as exc:
        assert "ne devine pas automatiquement" in str(exc)
    else:
        raise AssertionError("Empty protected columns must fail closed.")
