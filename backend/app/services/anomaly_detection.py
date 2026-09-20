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


def _empty_reasons(index: pd.Index) -> dict[Any, list[str]]:
    return {idx: [] for idx in index}


def _iqr(frame: pd.DataFrame) -> dict[str, Any]:
    mask = pd.Series(False, index=frame.index)
    score = pd.Series(0.0, index=frame.index)
    reasons = _empty_reasons(frame.index)
    bounds: dict[str, Any] = {}
    for col in frame.columns:
        s = frame[col]
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = float(q3 - q1)
        low, high = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
        col_mask = (s < low) | (s > high)
        denom = max(iqr, 1e-12)
        col_score = pd.concat([(low - s) / denom, (s - high) / denom], axis=1).max(axis=1).clip(lower=0)
        score = pd.Series(np.maximum(score.to_numpy(dtype=float), col_score.fillna(0.0).to_numpy(dtype=float)), index=frame.index)
        mask |= col_mask.fillna(False)
        bounds[col] = {"low": round(low, 6), "high": round(high, 6)}
        for idx in frame.index[col_mask.fillna(False)]:
            reasons[idx].append(f"{col}: hors bornes IQR")
    return {"method": "iqr", "mask": mask, "score": score, "reasons": reasons, "bounds": bounds}


def _robust_z(frame: pd.DataFrame, threshold: float) -> dict[str, Any]:
    mask = pd.Series(False, index=frame.index)
    score = pd.Series(0.0, index=frame.index)
    reasons = _empty_reasons(frame.index)
    bounds: dict[str, Any] = {}
    for col in frame.columns:
        s = frame[col]
        median = float(s.median())
        mad = float(np.median(np.abs(s.dropna().to_numpy(dtype=float) - median)))
        if mad <= 1e-12:
            z = pd.Series(0.0, index=s.index)
        else:
            z = 0.67448975 * (s - median).abs() / mad
        col_mask = z > threshold
        score = pd.Series(np.maximum(score.to_numpy(dtype=float), z.fillna(0.0).to_numpy(dtype=float)), index=frame.index)
        mask |= col_mask.fillna(False)
        bounds[col] = {"median": round(median, 6), "mad": round(mad, 6), "threshold": threshold}
        for idx in frame.index[col_mask.fillna(False)]:
            reasons[idx].append(f"{col}: z-score robuste > {threshold:g}")
    return {"method": "robust_z", "mask": mask, "score": score, "reasons": reasons, "bounds": bounds}


def _isolation_forest(frame: pd.DataFrame, contamination: float) -> dict[str, Any]:
    clean = frame.copy()
    for col in frame.columns:
        clean[col] = clean[col].fillna(clean[col].median())
    scaled = StandardScaler().fit_transform(clean)
    model = IsolationForest(n_estimators=300, contamination=contamination, random_state=42, n_jobs=1)
    labels = model.fit_predict(scaled)
    anomaly_strength = -model.score_samples(scaled)
    mask = pd.Series(labels == -1, index=frame.index)
    score = pd.Series(anomaly_strength, index=frame.index)
    reasons = _empty_reasons(frame.index)
    for idx in frame.index[mask]:
        reasons[idx].append("profil multivarié atypique (Isolation Forest)")
    return {"method": "isolation_forest", "mask": mask, "score": score, "reasons": reasons, "bounds": {}}


def _percentile_score(score: pd.Series) -> pd.Series:
    if len(score) == 0:
        return score.astype(float)
    return score.rank(method="average", pct=True).fillna(0.0).astype(float)


def _consensus(frame: pd.DataFrame, contamination: float, threshold: float) -> dict[str, Any]:
    parts = [_iqr(frame), _robust_z(frame, threshold), _isolation_forest(frame, contamination)]
    votes = pd.Series(0, index=frame.index, dtype=int)
    severity = pd.Series(0.0, index=frame.index)
    reasons = _empty_reasons(frame.index)
    for part in parts:
        votes += part["mask"].astype(int)
        severity += _percentile_score(part["score"])
        for idx in frame.index:
            if bool(part["mask"].loc[idx]):
                reasons[idx].append(f"{part['method']}: " + "; ".join(part["reasons"].get(idx, []) or ["signal atypique"]))
    severity = severity / float(len(parts))
    mask = votes >= 2
    return {
        "method": "consensus",
        "mask": mask,
        "score": severity,
        "reasons": reasons,
        "bounds": {part["method"]: part["bounds"] for part in parts if part["bounds"]},
        "votes": votes,
        "components": parts,
    }


def _summary(method: str, mask: pd.Series, score: pd.Series) -> dict[str, Any]:
    return {
        "method": method,
        "anomalies_count": int(mask.sum()),
        "anomaly_rate_pct": round(float(mask.mean() * 100), 4),
        "max_score": round(float(score.max()), 6) if len(score) else 0.0,
    }


def detect_anomalies(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "auto",
    contamination: float = 0.05,
    threshold: float = 3.5,
) -> dict[str, Any]:
    if not 0.001 <= contamination <= 0.4:
        raise ValueError("contamination doit être comprise entre 0.001 et 0.4")
    if not 1.0 <= threshold <= 10.0:
        raise ValueError("threshold doit être compris entre 1 et 10")
    frame = _numeric_frame(df, columns)
    cols = list(frame.columns)
    chosen = method
    if chosen == "auto":
        chosen = "robust_z" if len(cols) == 1 else "isolation_forest"
    if chosen not in {"iqr", "robust_z", "isolation_forest", "consensus"}:
        raise ValueError("Méthode d'anomalie non supportée")

    if chosen == "iqr":
        result = _iqr(frame)
    elif chosen == "robust_z":
        result = _robust_z(frame, threshold)
    elif chosen == "isolation_forest":
        result = _isolation_forest(frame, contamination)
    else:
        result = _consensus(frame, contamination, threshold)

    mask: pd.Series = result["mask"]
    score: pd.Series = result["score"]
    reasons: dict[Any, list[str]] = result["reasons"]
    votes: pd.Series | None = result.get("votes")

    anomaly_indices = list(frame.index[mask])
    rows: list[dict[str, Any]] = []
    ordered = sorted(anomaly_indices, key=lambda idx: float(score.loc[idx]), reverse=True)
    for idx in ordered[:500]:
        values = {c: (None if pd.isna(frame.loc[idx, c]) else float(frame.loc[idx, c])) for c in cols}
        row = {
            "index": int(idx) if isinstance(idx, (int, np.integer)) else str(idx),
            "score": round(float(score.loc[idx]), 6),
            "reasons": reasons.get(idx, []),
            "values": values,
        }
        if votes is not None:
            row["votes"] = int(votes.loc[idx])
            row["consensus"] = int(votes.loc[idx]) >= 2
        rows.append(row)

    by_column = []
    for col in cols:
        s = frame[col]
        by_column.append({
            "column": col,
            "missing": int(s.isna().sum()),
            "min": round(float(s.min()), 6) if s.notna().any() else None,
            "max": round(float(s.max()), 6) if s.notna().any() else None,
            "median": round(float(s.median()), 6) if s.notna().any() else None,
        })

    method_summary: list[dict[str, Any]] = []
    if chosen == "consensus":
        method_summary = [_summary(part["method"], part["mask"], part["score"]) for part in result["components"]]
        method_summary.append(_summary("consensus", mask, score))
    else:
        method_summary = [_summary(chosen, mask, score)]

    agreement = None
    if votes is not None:
        agreement = {
            "methods": 3,
            "required_votes": 2,
            "rows_with_1_vote": int((votes == 1).sum()),
            "rows_with_2_votes": int((votes == 2).sum()),
            "rows_with_3_votes": int((votes == 3).sum()),
        }

    return {
        "engine": "anomaly_detection_v253",
        "method": chosen,
        "columns": cols,
        "rows": int(len(df)),
        "anomalies_count": int(mask.sum()),
        "anomaly_rate_pct": round(float(mask.mean() * 100), 4),
        "contamination": contamination if chosen in {"isolation_forest", "consensus"} else None,
        "threshold": threshold if chosen in {"robust_z", "consensus"} else None,
        "bounds": result.get("bounds", {}),
        "column_summary": by_column,
        "method_summary": method_summary,
        "agreement": agreement,
        "score_semantics": "percentile consensus severity" if chosen == "consensus" else "method-specific anomaly severity",
        "anomalies": rows,
        "warnings": (["Le consensus requiert au moins 2 votes sur IQR, z-score robuste et Isolation Forest."] if chosen == "consensus" else []),
    }
