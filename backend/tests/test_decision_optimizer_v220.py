import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.decision_lab import optimize_scenarios
from app.services.modeling import train_model


def _configure_tmp(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)


def regression_frame(rows=120):
    x = np.linspace(0, 10, rows)
    z = np.linspace(2, 5, rows)
    y = 4.0 * x + 2.0 * z + 1.0
    return pd.DataFrame({"x": x, "z": z, "target": y})


def test_optimizer_finds_high_value_regression_scenario(
    tmp_path,
    monkeypatch,
):
    _configure_tmp(tmp_path, monkeypatch)
    df = regression_frame()
    trained = train_model(
        df,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={
            "id": "ds-opt",
            "version": 1,
            "name": "optimizer.csv",
        },
    )

    result = optimize_scenarios(
        trained.model_id,
        {"x": 1.0, "z": 2.0},
        {
            "x": {"min": 0.0, "max": 10.0, "steps": 6},
            "z": {"values": [2.0, 5.0]},
        },
        objective="maximize",
        max_candidates=100,
        max_results=5,
    )

    assert result["task"] == "regression"
    assert result["searched_candidates"] == 12
    assert result["recommended_scenarios"]
    best = result["recommended_scenarios"][0]
    assert best["overrides"]["x"] == 10.0
    assert best["overrides"]["z"] == 5.0
    assert best["prediction"] > result["baseline"]["prediction"]


def test_target_objective_prefers_closest_prediction(
    tmp_path,
    monkeypatch,
):
    _configure_tmp(tmp_path, monkeypatch)
    df = regression_frame()
    trained = train_model(
        df,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={
            "id": "ds-target",
            "version": 1,
            "name": "target.csv",
        },
    )

    result = optimize_scenarios(
        trained.model_id,
        {"x": 1.0, "z": 2.0},
        {
            "x": {"values": [1.0, 3.0, 5.0, 7.0]},
            "z": {"values": [2.0]},
        },
        objective="target",
        target_value=25.0,
        max_candidates=50,
        max_results=4,
    )

    rows = result["recommended_scenarios"]
    distances = [row["objective_distance"] for row in rows]
    assert distances == sorted(distances)


def test_optimizer_rejects_more_than_five_controls(
    tmp_path,
    monkeypatch,
):
    _configure_tmp(tmp_path, monkeypatch)
    df = regression_frame()
    trained = train_model(
        df,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={
            "id": "ds-limit",
            "version": 1,
            "name": "limit.csv",
        },
    )

    controls = {
        f"x{i}": {"values": [1, 2]}
        for i in range(6)
    }
    # None of these are model features, so this must fail closed.
    try:
        optimize_scenarios(
            trained.model_id,
            {"x": 1.0, "z": 2.0},
            controls,
        )
    except ValueError as exc:
        assert "Aucune variable de contrôle valide" in str(exc)
    else:
        raise AssertionError("Invalid controls should fail.")
