from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def _frequency(series: pd.Series, requested: str) -> tuple[str, str]:
    if requested and requested != "auto":
        mapping = {"daily": "D", "weekly": "W", "monthly": "MS", "quarterly": "QS", "yearly": "YS"}
        if requested not in mapping:
            raise ValueError("Fréquence non supportée")
        return requested, mapping[requested]
    values = pd.DatetimeIndex(series.dropna().sort_values().unique())
    if len(values) >= 3:
        inferred = pd.infer_freq(values)
        if inferred:
            upper = inferred.upper()
            if upper.startswith(("MS", "M")):
                return "monthly", "MS"
            if upper.startswith(("QS", "Q")):
                return "quarterly", "QS"
            if upper.startswith(("YS", "AS", "Y", "A")):
                return "yearly", "YS"
            if upper.startswith("W"):
                return "weekly", "W"
            if upper.startswith("D"):
                return "daily", "D"
    if len(values) >= 2:
        median_days = float(np.median(np.diff(values.values).astype("timedelta64[s]").astype(float))) / 86400.0
        if median_days <= 2:
            return "daily", "D"
        if median_days <= 10:
            return "weekly", "W"
        if median_days <= 45:
            return "monthly", "MS"
        if median_days <= 120:
            return "quarterly", "QS"
    return "yearly", "YS"


def _season_length(freq: str) -> int | None:
    return {"daily": 7, "weekly": 52, "monthly": 12, "quarterly": 4, "yearly": None}.get(freq)


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | None]:
    if len(y_true) == 0:
        return {"mae": None, "rmse": None, "mape": None, "smape": None, "bias": None}
    rmse = math.sqrt(float(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    nz = np.abs(y_true) > 1e-12
    mape = float(np.mean(np.abs((y_true[nz] - y_pred[nz]) / y_true[nz])) * 100) if np.any(nz) else None
    denom = np.abs(y_true) + np.abs(y_pred)
    valid = denom > 1e-12
    smape = float(np.mean(2.0 * np.abs(y_pred[valid] - y_true[valid]) / denom[valid]) * 100) if np.any(valid) else None
    bias = float(np.mean(y_pred - y_true))
    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "mape": round(mape, 6) if mape is not None else None,
        "smape": round(smape, 6) if smape is not None else None,
        "bias": round(bias, 6),
    }


def _predict_method(values: np.ndarray, steps: int, method: str, season_length: int | None) -> np.ndarray:
    if method == "naive":
        return np.repeat(values[-1], steps).astype(float)
    if method == "seasonal_naive":
        if not season_length or len(values) < season_length:
            raise ValueError("Historique insuffisant pour la méthode saisonnière")
        pattern = values[-season_length:]
        return np.asarray([pattern[i % season_length] for i in range(steps)], dtype=float)
    if method == "linear_trend":
        x = np.arange(len(values), dtype=float)
        slope, intercept = np.polyfit(x, values.astype(float), 1)
        return intercept + slope * np.arange(len(values), len(values) + steps, dtype=float)
    if method == "exponential_smoothing":
        seasonal = None
        seasonal_periods = None
        if season_length and len(values) >= max(2 * season_length, 12):
            seasonal = "add"
            seasonal_periods = season_length
        model = ExponentialSmoothing(
            values.astype(float),
            trend="add" if len(values) >= 5 else None,
            seasonal=seasonal,
            seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
        return np.asarray(model.forecast(steps), dtype=float)
    raise ValueError(f"Méthode de forecasting inconnue: {method}")


def _regularize_series(
    work: pd.DataFrame,
    freq_code: str,
    missing_strategy: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    grouped = work.groupby("date", as_index=False)["value"].mean().sort_values("date").reset_index(drop=True)
    duplicates = int(len(work) - len(grouped))
    expected = pd.date_range(grouped["date"].iloc[0], grouped["date"].iloc[-1], freq=freq_code)
    observed_dates = pd.DatetimeIndex(grouped["date"])
    missing_dates = expected.difference(observed_dates)
    missing_count = int(len(missing_dates))
    if missing_strategy not in {"none", "interpolate", "ffill", "zero"}:
        raise ValueError("Stratégie de valeurs temporelles manquantes non supportée")
    if missing_count and missing_strategy == "none":
        raise ValueError(
            f"La série contient {missing_count} période(s) manquante(s). Choisissez missing_strategy=interpolate, ffill ou zero pour une régularisation explicite."
        )
    if missing_count:
        regular = grouped.set_index("date").reindex(expected)
        if missing_strategy == "interpolate":
            regular["value"] = regular["value"].interpolate(method="linear", limit_direction="both")
        elif missing_strategy == "ffill":
            regular["value"] = regular["value"].ffill().bfill()
        elif missing_strategy == "zero":
            regular["value"] = regular["value"].fillna(0.0)
        grouped = regular.rename_axis("date").reset_index()
    diagnostics = {
        "observations_input": int(len(work)),
        "periods_observed": int(len(observed_dates)),
        "periods_regularized": int(len(grouped)),
        "duplicates_aggregated": duplicates,
        "missing_periods": missing_count,
        "missing_rate_pct": round(float(missing_count / max(1, len(expected)) * 100.0), 4),
        "missing_strategy": missing_strategy,
        "start": pd.Timestamp(grouped["date"].iloc[0]).isoformat(),
        "end": pd.Timestamp(grouped["date"].iloc[-1]).isoformat(),
    }
    return grouped, diagnostics


def _time_series_diagnostics(values: np.ndarray, season_length: int | None) -> dict[str, Any]:
    x = np.arange(len(values), dtype=float)
    if len(values) >= 2:
        slope, intercept = np.polyfit(x, values, 1)
        fitted = intercept + slope * x
        ss_res = float(np.sum((values - fitted) ** 2))
        ss_tot = float(np.sum((values - np.mean(values)) ** 2))
        trend_r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    else:
        slope, trend_r2 = 0.0, 0.0
    lag1 = float(pd.Series(values).autocorr(lag=1)) if len(values) >= 3 else None
    seasonal_corr = None
    if season_length and len(values) >= 2 * season_length:
        seasonal_corr = float(pd.Series(values).autocorr(lag=season_length))
    return {
        "trend_slope_per_period": round(float(slope), 6),
        "trend_r2": round(float(max(0.0, min(1.0, trend_r2))), 6),
        "lag1_autocorrelation": round(lag1, 6) if lag1 is not None and np.isfinite(lag1) else None,
        "seasonal_lag": season_length,
        "seasonal_autocorrelation": round(seasonal_corr, 6) if seasonal_corr is not None and np.isfinite(seasonal_corr) else None,
    }


def _rolling_windows(n: int, requested: int, validation_size: int) -> list[tuple[int, int]]:
    requested = max(1, min(int(requested), 8))
    validation_size = max(2, int(validation_size))
    windows: list[tuple[int, int]] = []
    for offset in range(requested - 1, -1, -1):
        valid_end = n - offset * validation_size
        valid_start = valid_end - validation_size
        if valid_start < 8 or valid_end > n:
            continue
        windows.append((valid_start, valid_end))
    if not windows:
        valid_start = max(8, n - validation_size)
        if valid_start < n:
            windows.append((valid_start, n))
    return windows


def _benchmark_candidate(
    values: np.ndarray,
    candidate: str,
    season_length: int | None,
    windows: list[tuple[int, int]],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    y_true_parts: list[np.ndarray] = []
    y_pred_parts: list[np.ndarray] = []
    fold_metrics: list[dict[str, Any]] = []
    for fold, (valid_start, valid_end) in enumerate(windows, start=1):
        train = values[:valid_start]
        valid = values[valid_start:valid_end]
        pred = _predict_method(train, len(valid), candidate, season_length)
        y_true_parts.append(valid)
        y_pred_parts.append(pred)
        fold_metrics.append({
            "fold": fold,
            "train_periods": int(len(train)),
            "validation_periods": int(len(valid)),
            **_metrics(valid, pred),
        })
    y_true = np.concatenate(y_true_parts) if y_true_parts else np.asarray([], dtype=float)
    y_pred = np.concatenate(y_pred_parts) if y_pred_parts else np.asarray([], dtype=float)
    summary = {
        "method": candidate,
        **_metrics(y_true, y_pred),
        "backtest_windows": len(fold_metrics),
        "fold_metrics": fold_metrics,
        "status": "ok",
    }
    return summary, y_true, y_pred


def forecast_series(
    df: pd.DataFrame,
    date_column: str,
    target: str,
    horizon: int = 12,
    frequency: str = "auto",
    method: str = "auto",
    backtest_windows: int = 3,
    interval_level: float = 0.95,
    missing_strategy: str = "none",
    selection_metric: str = "rmse",
) -> dict[str, Any]:
    if date_column not in df.columns or target not in df.columns:
        raise ValueError("Colonne de date ou cible inconnue")
    if horizon < 1 or horizon > 365:
        raise ValueError("L'horizon doit être compris entre 1 et 365 périodes")
    if not 1 <= int(backtest_windows) <= 8:
        raise ValueError("backtest_windows doit être compris entre 1 et 8")
    if not 0.5 <= float(interval_level) <= 0.99:
        raise ValueError("interval_level doit être compris entre 0.5 et 0.99")
    if selection_metric not in {"rmse", "mae", "smape"}:
        raise ValueError("Métrique de sélection non supportée")

    raw = pd.DataFrame({
        "date": pd.to_datetime(df[date_column], errors="coerce"),
        "value": pd.to_numeric(df[target], errors="coerce"),
    }).dropna()
    if len(raw) < 12:
        raise ValueError("Le forecasting requiert au moins 12 observations datées et numériques.")

    grouped_for_frequency = raw.groupby("date", as_index=False)["value"].mean().sort_values("date").reset_index(drop=True)
    if len(grouped_for_frequency) < 12:
        raise ValueError("Le forecasting requiert au moins 12 périodes temporelles distinctes.")
    freq_name, freq_code = _frequency(grouped_for_frequency["date"], frequency)
    work, regularity = _regularize_series(raw, freq_code, missing_strategy)
    if len(work) < 12:
        raise ValueError("Historique insuffisant après régularisation temporelle.")

    season = _season_length(freq_name)
    values = work["value"].to_numpy(dtype=float)
    diagnostics = _time_series_diagnostics(values, season)
    validation_size = min(max(3, min(horizon, int(math.ceil(len(work) * 0.15)))), max(3, len(work) // 4))
    windows = _rolling_windows(len(work), int(backtest_windows), validation_size)

    candidates = ["naive", "linear_trend", "exponential_smoothing"]
    if season and len(values) >= season:
        candidates.insert(1, "seasonal_naive")
    if method != "auto":
        if method not in {"naive", "seasonal_naive", "linear_trend", "exponential_smoothing"}:
            raise ValueError("Méthode de forecasting non supportée")
        candidates = [method]

    benchmark: list[dict[str, Any]] = []
    backtest_predictions: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for candidate in candidates:
        try:
            summary, y_true, y_pred = _benchmark_candidate(values, candidate, season, windows)
            benchmark.append(summary)
            backtest_predictions[candidate] = (y_true, y_pred)
        except Exception as exc:
            benchmark.append({"method": candidate, "status": "failed", "error": str(exc), "backtest_windows": 0})
    ok = [x for x in benchmark if x.get("status") == "ok" and x.get(selection_metric) is not None]
    if not ok:
        raise ValueError("Aucune méthode de forecasting n'a pu être ajustée aux données.")
    ok.sort(key=lambda x: float(x[selection_metric]))
    for rank, item in enumerate(ok, start=1):
        item["rank"] = rank
    failed = [x for x in benchmark if x.get("status") != "ok"]
    benchmark = ok + failed
    chosen = str(ok[0]["method"])

    future = _predict_method(values, horizon, chosen, season)
    y_true, y_pred = backtest_predictions[chosen]
    residuals = y_true - y_pred
    alpha = 1.0 - float(interval_level)
    lower_resid = float(np.quantile(residuals, alpha / 2.0)) if len(residuals) else 0.0
    upper_resid = float(np.quantile(residuals, 1.0 - alpha / 2.0)) if len(residuals) else 0.0
    lower = future + lower_resid
    upper = future + upper_resid

    residual_lag1 = float(pd.Series(residuals).autocorr(lag=1)) if len(residuals) >= 3 else None
    residual_diag = {
        "count": int(len(residuals)),
        "mean_error": round(float(np.mean(residuals)), 6) if len(residuals) else None,
        "std_error": round(float(np.std(residuals, ddof=1)), 6) if len(residuals) > 1 else 0.0,
        "lag1_autocorrelation": round(residual_lag1, 6) if residual_lag1 is not None and np.isfinite(residual_lag1) else None,
        "absolute_error_p95": round(float(np.quantile(np.abs(residuals), 0.95)), 6) if len(residuals) else None,
    }

    last_date = pd.Timestamp(work["date"].iloc[-1])
    future_dates = pd.date_range(start=last_date, periods=horizon + 1, freq=freq_code)[1:]
    interval_label = int(round(float(interval_level) * 100))
    forecast = [
        {
            "date": d.isoformat(),
            "prediction": round(float(p), 6),
            "lower": round(float(lo), 6),
            "upper": round(float(hi), 6),
            "lower_95": round(float(lo), 6) if interval_label == 95 else None,
            "upper_95": round(float(hi), 6) if interval_label == 95 else None,
        }
        for d, p, lo, hi in zip(future_dates, future, lower, upper)
    ]
    history = [
        {"date": pd.Timestamp(d).isoformat(), "value": round(float(v), 6)}
        for d, v in work.tail(240).itertuples(index=False, name=None)
    ]

    warnings: list[str] = []
    if regularity["missing_periods"]:
        warnings.append(
            f"{regularity['missing_periods']} période(s) manquante(s) ont été régularisées par la stratégie '{missing_strategy}'."
        )
    if residual_diag["lag1_autocorrelation"] is not None and abs(float(residual_diag["lag1_autocorrelation"])) >= 0.3:
        warnings.append("Les résidus de backtest restent autocorrélés; la structure temporelle n'est probablement pas entièrement capturée.")
    if len(residuals) < 20:
        warnings.append("Peu d'erreurs hors-échantillon sont disponibles; l'intervalle empirique doit être interprété avec prudence.")
    warnings.append("Les intervalles sont empiriques et fondés uniquement sur les erreurs de backtesting hors-échantillon.")
    warnings.append("Le moteur suppose que la structure historique reste informative sur l'horizon de prévision.")

    return {
        "engine": "forecasting_v253",
        "date_column": date_column,
        "target": target,
        "frequency": freq_name,
        "frequency_code": freq_code,
        "horizon": horizon,
        "method": chosen,
        "selection_metric": selection_metric,
        "selection_rationale": f"{chosen} minimise {selection_metric.upper()} sur {len(windows)} fenêtre(s) rolling-origin hors-échantillon.",
        "benchmark": benchmark,
        "backtest": {
            "strategy": "rolling_origin",
            "windows": len(windows),
            "validation_periods_per_window": validation_size,
            "window_boundaries": [{"train_end": int(a), "validation_end": int(b)} for a, b in windows],
        },
        "validation_periods": int(sum(b - a for a, b in windows)),
        "prediction_interval": {
            "level": round(float(interval_level), 4),
            "method": "rolling-origin empirical residual quantiles",
            "lower_residual_quantile": round(lower_resid, 6),
            "upper_residual_quantile": round(upper_resid, 6),
            "residuals_count": int(len(residuals)),
        },
        "series_diagnostics": {**regularity, **diagnostics},
        "residual_diagnostics": residual_diag,
        "history": history,
        "forecast": forecast,
        "warnings": warnings,
    }
