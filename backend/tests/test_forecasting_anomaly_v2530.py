from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.forecasting import forecast_series
from app.services.anomaly_detection import detect_anomalies


def _series(n: int = 72) -> pd.DataFrame:
    rng = np.random.default_rng(253)
    dates = pd.date_range("2020-01-01", periods=n, freq="MS")
    x = np.arange(n, dtype=float)
    values = 100 + 0.8 * x + 8 * np.sin(2 * np.pi * x / 12) + rng.normal(0, 1.5, n)
    return pd.DataFrame({"date": dates, "sales": values})


def test_v253_forecast_uses_rolling_origin_and_empirical_intervals():
    out = forecast_series(
        _series(), "date", "sales", horizon=6, frequency="monthly", method="auto",
        backtest_windows=4, interval_level=0.9, missing_strategy="none", selection_metric="rmse",
    )
    assert out["engine"] == "forecasting_v253"
    assert out["backtest"]["strategy"] == "rolling_origin"
    assert out["backtest"]["windows"] >= 2
    assert out["prediction_interval"]["method"] == "rolling-origin empirical residual quantiles"
    assert out["prediction_interval"]["residuals_count"] >= 6
    assert len(out["forecast"]) == 6
    assert all(row["lower"] <= row["prediction"] <= row["upper"] for row in out["forecast"])
    ranked = [row for row in out["benchmark"] if row.get("status") == "ok"]
    assert ranked and ranked[0].get("rank") == 1
    assert all("smape" in row for row in ranked)


def test_v253_irregular_series_requires_explicit_missing_strategy():
    df = _series(36).drop(index=[5, 14]).reset_index(drop=True)
    with pytest.raises(ValueError, match="période\\(s\\) manquante"):
        forecast_series(df, "date", "sales", frequency="monthly", missing_strategy="none")
    out = forecast_series(df, "date", "sales", frequency="monthly", missing_strategy="interpolate", backtest_windows=2)
    assert out["series_diagnostics"]["missing_periods"] == 2
    assert out["series_diagnostics"]["missing_strategy"] == "interpolate"
    assert any("régularisées" in warning for warning in out["warnings"])


def test_v253_consensus_anomaly_requires_two_votes():
    rng = np.random.default_rng(254)
    df = pd.DataFrame({"x": rng.normal(0, 1, 120), "y": rng.normal(0, 1, 120)})
    df.loc[119, ["x", "y"]] = [14.0, 16.0]
    out = detect_anomalies(df, ["x", "y"], method="consensus", contamination=0.03, threshold=3.5)
    assert out["engine"] == "anomaly_detection_v253"
    assert out["method"] == "consensus"
    assert out["agreement"]["required_votes"] == 2
    assert {row["method"] for row in out["method_summary"]} == {"iqr", "robust_z", "isolation_forest", "consensus"}
    hit = next(row for row in out["anomalies"] if row["index"] == 119)
    assert hit["votes"] >= 2 and hit["consensus"] is True


def test_v253_api_and_frontend_expose_new_controls():
    from app.api.routes.datasets import ForecastRequest, AnomalyRequest
    forecast = ForecastRequest.model_json_schema()["properties"]
    anomaly = AnomalyRequest.model_json_schema()["properties"]
    for key in ("backtest_windows", "interval_level", "missing_strategy", "selection_metric"):
        assert key in forecast
    assert "consensus" in str(anomaly["method"])
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    assert "Backtests" in page and "Consensus multi-méthodes" in page
    assert "missing_strategy" in api and "consensus" in api


def test_v253_assistant_tools_are_executable_and_owned_by_specialists():
    from app.assistant.tools import build_default_registry
    from app.assistant.host_v212 import bind_v212_host
    from app.assistant.agents import MultiAgentCoordinator
    registry = build_default_registry()
    bind_v212_host(registry)
    assert registry.is_executable("forecast_dataset")
    assert registry.is_executable("detect_dataset_anomalies")
    coordinator = MultiAgentCoordinator(registry)
    assert coordinator.role_for_tool("forecast_dataset") == "ml_agent"
    assert coordinator.role_for_tool("detect_dataset_anomalies") == "statistics_agent"
