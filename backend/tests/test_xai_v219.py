import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.modeling import (
    algorithm_availability,
    benchmark_models,
    train_model,
)
from app.services.xai import (
    generate_counterfactuals,
    model_diagnostics,
    partial_dependence,
    shap_explanation,
    xai_capabilities,
)


def _use_tmp_models(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)


def regression_frame(rows=120):
    x = np.linspace(0, 10, rows)
    z = np.sin(x)
    y = 3.0 * x + 2.0 * z + 5.0
    return pd.DataFrame(
        {
            "x": x,
            "z": z,
            "segment": np.where(x > 5, "B", "A"),
            "target": y,
        }
    )


def classification_frame(rows=120):
    x = np.linspace(-3, 3, rows)
    z = np.cos(x)
    label = np.where(x + 0.4 * z > 0, "yes", "no")
    return pd.DataFrame(
        {
            "x": x,
            "z": z,
            "segment": np.where(x > 0, "east", "west"),
            "target": label,
        }
    )


def test_algorithm_catalog_exposes_advanced_engines():
    engines = algorithm_availability()
    assert engines["svm"]["available"] is True
    assert engines["svm"]["engine"] == "scikit-learn"
    for name in ("xgboost", "lightgbm", "catboost"):
        assert name in engines
        assert isinstance(engines[name]["available"], bool)


def test_benchmark_models_returns_ranked_successes():
    result = benchmark_models(
        regression_frame(),
        target="target",
        task="regression",
        primary_metric="rmse",
        cv_folds=3,
        max_candidates=4,
    )
    assert result["task"] == "regression"
    assert result["best"] is not None
    assert result["best"]["status"] == "ok"
    assert len(result["benchmark"]) == 4
    assert all("engine" in row for row in result["benchmark"])


def test_partial_dependence_uses_saved_model(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = regression_frame()
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="random_forest",
        dataset_context={"id": "ds1", "version": 1, "name": "regression.csv"},
    )

    result = partial_dependence(
        trained.model_id,
        frame,
        ["x", "segment"],
        grid_points=8,
    )
    assert result["model_id"] == trained.model_id
    assert len(result["curves"]) == 2
    numeric = next(x for x in result["curves"] if x["feature"] == "x")
    assert numeric["kind"] == "numeric"
    assert len(numeric["points"]) >= 3
    assert all("response" in point for point in numeric["points"])


def test_binary_diagnostics_include_calibration_error(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = classification_frame()
    trained = train_model(
        frame,
        "target",
        task="classification",
        algorithm="logistic_regression",
        dataset_context={"id": "ds2", "version": 1, "name": "class.csv"},
    )
    result = model_diagnostics(trained.model_id, frame)

    assert result["task"] == "classification"
    assert "roc_auc" in result
    assert "brier_score" in result
    assert "expected_calibration_error" in result
    assert 0 <= result["expected_calibration_error"] <= 1


def test_counterfactual_search_improves_regression_direction(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = regression_frame()
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={"id": "ds3", "version": 1, "name": "cf.csv"},
    )
    row = {
        "x": 1.0,
        "z": float(np.sin(1.0)),
        "segment": "A",
    }
    result = generate_counterfactuals(
        trained.model_id,
        frame,
        row,
        direction="increase",
        max_changes=2,
        max_results=5,
    )

    assert result["task"] == "regression"
    assert result["searched_candidates"] > 0
    assert result["counterfactuals"]
    assert result["counterfactuals"][0]["objective_improvement"] > 0


def test_shap_is_explicitly_ok_or_unavailable(tmp_path, monkeypatch):
    _use_tmp_models(tmp_path, monkeypatch)
    frame = regression_frame(80)
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="random_forest",
        dataset_context={"id": "ds4", "version": 1, "name": "shap.csv"},
    )
    caps = xai_capabilities(trained.model_id)
    assert "shap" in caps

    result = shap_explanation(
        trained.model_id,
        frame,
        row={
            "x": 2.0,
            "z": float(np.sin(2.0)),
            "segment": "A",
        },
        max_rows=20,
    )
    assert result["status"] in {"ok", "unavailable"}
    if result["status"] == "ok":
        assert result["global_importance"]
        assert result["method"] in {
            "TreeExplainer",
            "PermutationExplainer",
        }
    else:
        assert result.get("reason")
