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
    rmse = math.sqrt(float(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    nz = np.abs(y_true) > 1e-12
    mape = float(np.mean(np.abs((y_true[nz] - y_pred[nz]) / y_true[nz])) * 100) if np.any(nz) else None
    return {"mae": round(mae, 6), "rmse": round(rmse, 6), "mape": round(mape, 6) if mape is not None else None}


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
            values.astype(float), trend="add" if len(values) >= 5 else None,
            seasonal=seasonal, seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
        return np.asarray(model.forecast(steps), dtype=float)
    raise ValueError(f"Méthode de forecasting inconnue: {method}")


def forecast_series(
    df: pd.DataFrame,
    date_column: str,
    target: str,
    horizon: int = 12,
    frequency: str = "auto",
    method: str = "auto",
) -> dict[str, Any]:
    if date_column not in df.columns or target not in df.columns:
        raise ValueError("Colonne de date ou cible inconnue")
    if horizon < 1 or horizon > 365:
        raise ValueError("L'horizon doit être compris entre 1 et 365 périodes")

    work = pd.DataFrame({"date": pd.to_datetime(df[date_column], errors="coerce"), "value": pd.to_numeric(df[target], errors="coerce")}).dropna()
    if len(work) < 12:
        raise ValueError("Le forecasting requiert au moins 12 observations datées et numériques.")
    work = work.groupby("date", as_index=False)["value"].mean().sort_values("date").reset_index(drop=True)
    if len(work) < 12:
        raise ValueError("Le forecasting requiert au moins 12 périodes temporelles distinctes.")

    freq_name, freq_code = _frequency(work["date"], frequency)
    season = _season_length(freq_name)
    holdout = min(max(3, int(math.ceil(len(work) * 0.2))), max(3, len(work) // 3))
    train = work.iloc[:-holdout]
    valid = work.iloc[-holdout:]
    if len(train) < 8:
        raise ValueError("Historique insuffisant après création de la fenêtre de validation.")

    candidates = ["naive", "linear_trend", "exponential_smoothing"]
    if season and len(train) >= season:
        candidates.insert(1, "seasonal_naive")
    if method != "auto":
        if method not in {"naive", "seasonal_naive", "linear_trend", "exponential_smoothing"}:
            raise ValueError("Méthode de forecasting non supportée")
        candidates = [method]

    benchmark: list[dict[str, Any]] = []
    y_train = train["value"].to_numpy(dtype=float)
    y_valid = valid["value"].to_numpy(dtype=float)
    for candidate in candidates:
        try:
            pred = _predict_method(y_train, len(valid), candidate, season)
            benchmark.append({"method": candidate, **_metrics(y_valid, pred), "status": "ok"})
        except Exception as exc:
            benchmark.append({"method": candidate, "status": "failed", "error": str(exc)})
    ok = [x for x in benchmark if x.get("status") == "ok"]
    if not ok:
        raise ValueError("Aucune méthode de forecasting n'a pu être ajustée aux données.")
    ok.sort(key=lambda x: float(x["rmse"]))
    chosen = ok[0]["method"]

    full_values = work["value"].to_numpy(dtype=float)
    future = _predict_method(full_values, horizon, chosen, season)

    # Prediction intervals are empirical and clearly labeled as approximations.
    valid_pred = _predict_method(y_train, len(valid), chosen, season)
    residuals = y_valid - valid_pred
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
    z = 1.96
    lower = future - z * sigma
    upper = future + z * sigma

    last_date = pd.Timestamp(work["date"].iloc[-1])
    future_dates = pd.date_range(start=last_date, periods=horizon + 1, freq=freq_code)[1:]
    forecast = [
        {
            "date": d.isoformat(), "prediction": round(float(p), 6),
            "lower_95": round(float(lo), 6), "upper_95": round(float(hi), 6),
        }
        for d, p, lo, hi in zip(future_dates, future, lower, upper)
    ]
    history = [
        {"date": pd.Timestamp(d).isoformat(), "value": round(float(v), 6)}
        for d, v in work.tail(240).itertuples(index=False, name=None)
    ]
    return {
        "date_column": date_column,
        "target": target,
        "frequency": freq_name,
        "frequency_code": freq_code,
        "horizon": horizon,
        "method": chosen,
        "benchmark": benchmark,
        "validation_periods": len(valid),
        "prediction_interval": {"level": 0.95, "method": "empirical residual standard deviation", "sigma": round(sigma, 6)},
        "history": history,
        "forecast": forecast,
        "warnings": [
            "Les intervalles sont des approximations empiriques et ne remplacent pas un intervalle probabiliste propre au modèle.",
            "Le moteur suppose que la structure historique reste informative sur l'horizon de prévision.",
        ],
    }
