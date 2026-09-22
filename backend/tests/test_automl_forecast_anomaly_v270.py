from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.automl_engine import get_automl_experiment, run_automl_benchmark, run_automl_experiment
from app.services.modeling import get_model_card


def _series(n: int = 84) -> pd.DataFrame:
    rng = np.random.default_rng(270)
    dates = pd.date_range("2019-01-01", periods=n, freq="MS")
    x = np.arange(n, dtype=float)
    sales = 80 + 0.75 * x + 9 * np.sin(2 * np.pi * x / 12) + rng.normal(0, 1.2, n)
    return pd.DataFrame({"date": dates, "sales": sales, "promo": (x % 4 == 0).astype(int)})


def _anomaly_frame(n: int = 140) -> pd.DataFrame:
    rng = np.random.default_rng(271)
    df = pd.DataFrame({"x": rng.normal(0, 1, n), "y": rng.normal(0, 1, n)})
    df.loc[n - 1, ["x", "y"]] = [12.0, 14.0]
    df.loc[n - 2, ["x", "y"]] = [-10.0, 11.0]
    return df


def test_v270_forecasting_automl_uses_rolling_origin_and_persists_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    out = run_automl_experiment(
        _series(), task="forecasting", target="sales", time_column="date",
        primary_metric="rmse", max_candidates=4, horizon=6, backtest_windows=4,
        dataset_context={"id": "forecast-ds", "version": 2, "name": "sales.csv"},
    )
    assert out["engine"] == "automl_v270"
    assert out["task"] == "forecasting"
    assert out["model_id"]
    assert out["leaderboard"][0]["rank"] == 1
    assert out["metric_direction"] == "minimize"
    assert out["forecast_result"]["backtest"]["strategy"] == "rolling_origin"
    assert out["forecast_result"]["backtest"]["windows"] >= 2
    assert (tmp_path / "models" / f"{out['model_id']}.joblib").exists()
    card = get_model_card(out["model_id"])
    assert card["task"] == "forecasting"
    assert card["validation_strategy"]["strategy"] == "rolling_origin"
    exp = get_automl_experiment(out["experiment_id"])
    assert exp["task"] == "forecasting"
    assert exp["validation_policy"]["selection_uses_future"] is False


def test_v270_forecasting_benchmark_does_not_persist_model(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    out = run_automl_benchmark(
        _series(), task="forecasting", target="sales", time_column="date",
        primary_metric="mae", max_candidates=4, horizon=4, backtest_windows=3,
    )
    assert out["task"] == "forecasting"
    assert out["model_id"] is None
    assert out["experiment_id"] is None
    assert out["leaderboard"][0]["rank"] == 1
    assert not list((tmp_path / "models").glob("*.joblib")) if (tmp_path / "models").exists() else True


def test_v270_anomaly_automl_is_unsupervised_and_selects_by_robustness(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    out = run_automl_experiment(
        _anomaly_frame(), task="anomaly_detection", features=["x", "y"],
        primary_metric="quality_score", max_candidates=4, contamination=0.04, threshold=3.5,
        dataset_context={"id": "anomaly-ds", "version": 1},
    )
    assert out["engine"] == "automl_v270"
    assert out["task"] == "anomaly_detection"
    assert out["target"] is None
    assert out["leaderboard"][0]["rank"] == 1
    assert out["leaderboard"][0]["quality_score"] is not None
    assert out["leaderboard"][0]["stability"] is not None
    assert out["leaderboard"][0]["agreement"] is not None
    assert "vérité terrain" in out["selection_rationale"]
    exp = get_automl_experiment(out["experiment_id"])
    assert exp["validation_policy"]["ground_truth_used"] is False
    card = get_model_card(out["model_id"])
    assert card["task"] == "anomaly_detection"
    assert card["validation_strategy"]["ground_truth_used"] is False


def test_v270_api_contract_exposes_forecasting_and_anomaly_automl():
    from app.api.routes.datasets import AutoMLRequest, BenchmarkRequest
    a = str(AutoMLRequest.model_json_schema())
    b = str(BenchmarkRequest.model_json_schema())
    assert "forecasting" in a and "anomaly_detection" in a
    assert "quality_score" in a and "smape" in a
    assert "horizon" in a and "contamination" in a
    assert "forecasting" in b and "anomaly_detection" in b


def test_v270_assistant_contract_and_bridge_support_specialized_automl():
    from app.assistant.contracts import AutoMLArgs
    assert AutoMLArgs(task="forecasting", target="sales", time_column="date").task == "forecasting"
    assert AutoMLArgs(task="anomaly_detection", target=None, features=["x"]).task == "anomaly_detection"
    try:
        AutoMLArgs(task="forecasting", target="sales")
    except ValueError as exc:
        assert "temporelle" in str(exc)
    else:
        raise AssertionError("Forecasting AutoML doit exiger une colonne temporelle")
    root = Path(__file__).resolve().parents[2]
    host = (root / "backend/app/assistant/host_v212.py").read_text(encoding="utf-8")
    assert '"forecasting", "anomaly_detection"' in host


def test_v270_frontend_exposes_unified_tasks_and_controls():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    assert "Forecasting temporel" in page
    assert "Détection d’anomalies" in page
    assert "Score qualité" in page
    assert "forecastHorizon" in page and "contamination" in page
    assert "anomaly_detection" in api and "backtest_windows" in api


def test_v270_specialized_artifact_registers_in_model_registry(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store
    from app.services.model_registry import LOCAL_ACTOR, LOCAL_WORKSPACE, register_model
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear(); metadata_store.init_metadata_store()
    out = run_automl_experiment(
        _series(), task="forecasting", target="sales", time_column="date",
        primary_metric="rmse", max_candidates=3, horizon=3, backtest_windows=2,
        dataset_context={"id": "forecast-registry", "root_id": "forecast-registry", "version": 1, "name": "series.csv"},
    )
    entry = register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, out["model_id"])
    assert entry["model_id"] == out["model_id"]
    assert entry["card"]["task"] == "forecasting"
    assert entry["integrity"]["status"] == "ok"
