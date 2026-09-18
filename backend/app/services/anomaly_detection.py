from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def _numeric_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Variables inconnues: {missing}")
    if not columns:
        columns = list(df.select_dtypes(include=np.number).columns)
    if not columns:
        raise ValueError("Aucune variable numérique disponible")
    frame = df[columns].apply(pd.to_numeric, errors="coerce")
    usable = [c for c in columns if frame[c].notna().sum() >= 5 and frame[c].nunique(dropna=True) > 1]
    if not usable:
        raise ValueError("Aucune variable numérique exploitable pour la détection d'anomalies")
    return frame[usable]


def detect_anomalies(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "auto",
    contamination: float = 0.05,
    threshold: float = 3.5,
) -> dict[str, Any]:
    if not 0.001 <= contamination <= 0.4:
        raise ValueError("contamination doit être comprise entre 0.001 et 0.4")
    frame = _numeric_frame(df, columns)
    cols = list(frame.columns)
    chosen = method
    if chosen == "auto":
        chosen = "robust_z" if len(cols) == 1 else "isolation_forest"
    if chosen not in {"iqr", "robust_z", "isolation_forest"}:
        raise ValueError("Méthode d'anomalie non supportée")

    mask = pd.Series(False, index=frame.index)
    score = pd.Series(0.0, index=frame.index)
    reasons: dict[Any, list[str]] = {idx: [] for idx in frame.index}
    bounds: dict[str, Any] = {}

    if chosen == "iqr":
        for col in cols:
            s = frame[col]
            q1, q3 = s.quantile([0.25, 0.75])
            iqr = float(q3 - q1)
            low, high = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
            col_mask = (s < low) | (s > high)
            denom = max(iqr, 1e-12)
            col_score = pd.concat([(low - s) / denom, (s - high) / denom], axis=1).max(axis=1).clip(lower=0)
            score = np.maximum(score, col_score.fillna(0.0))
            mask |= col_mask.fillna(False)
            bounds[col] = {"low": round(low, 6), "high": round(high, 6)}
            for idx in frame.index[col_mask.fillna(False)]:
                reasons[idx].append(f"{col}: hors bornes IQR")

    elif chosen == "robust_z":
        for col in cols:
            s = frame[col]
            median = float(s.median())
            mad = float(np.median(np.abs(s.dropna().to_numpy(dtype=float) - median)))
            if mad <= 1e-12:
                z = pd.Series(0.0, index=s.index)
            else:
                z = 0.67448975 * (s - median).abs() / mad
            col_mask = z > threshold
            score = np.maximum(score, z.fillna(0.0))
            mask |= col_mask.fillna(False)
            bounds[col] = {"median": round(median, 6), "mad": round(mad, 6), "threshold": threshold}
            for idx in frame.index[col_mask.fillna(False)]:
                reasons[idx].append(f"{col}: z-score robuste > {threshold:g}")

    else:
        clean = frame.copy()
        for col in cols:
            clean[col] = clean[col].fillna(clean[col].median())
        scaled = StandardScaler().fit_transform(clean)
        model = IsolationForest(n_estimators=250, contamination=contamination, random_state=42, n_jobs=1)
        labels = model.fit_predict(scaled)
        anomaly_strength = -model.score_samples(scaled)
        mask = pd.Series(labels == -1, index=frame.index)
        score = pd.Series(anomaly_strength, index=frame.index)
        for idx in frame.index[mask]:
            reasons[idx].append("profil multivarié atypique (Isolation Forest)")

    anomaly_indices = list(frame.index[mask])
    rows: list[dict[str, Any]] = []
    ordered = sorted(anomaly_indices, key=lambda idx: float(score.loc[idx]), reverse=True)
    for idx in ordered[:500]:
        values = {c: (None if pd.isna(frame.loc[idx, c]) else float(frame.loc[idx, c])) for c in cols}
        rows.append({
            "index": int(idx) if isinstance(idx, (int, np.integer)) else str(idx),
            "score": round(float(score.loc[idx]), 6),
            "reasons": reasons.get(idx, []),
            "values": values,
        })

    by_column = []
    for col in cols:
        s = frame[col]
        by_column.append({
            "column": col,
            "missing": int(s.isna().sum()),
            "min": round(float(s.min()), 6) if s.notna().any() else None,
            "max": round(float(s.max()), 6) if s.notna().any() else None,
        })
    return {
        "method": chosen,
        "columns": cols,
        "rows": int(len(df)),
        "anomalies_count": int(mask.sum()),
        "anomaly_rate_pct": round(float(mask.mean() * 100), 4),
        "contamination": contamination if chosen == "isolation_forest" else None,
        "bounds": bounds,
        "column_summary": by_column,
        "anomalies": rows,
    }
