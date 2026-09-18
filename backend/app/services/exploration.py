from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _jsonable(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def preview_dataframe(df: pd.DataFrame, limit: int = 25) -> dict:
    limit = max(1, min(limit, 100))
    rows = []
    for record in df.head(limit).to_dict(orient="records"):
        rows.append({str(k): _jsonable(v) for k, v in record.items()})
    return {
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "shown": len(rows),
        "total": int(len(df)),
    }


def analyze_column(df: pd.DataFrame, column: str) -> dict:
    if column not in df.columns:
        raise ValueError("Variable inconnue")

    s = df[column]
    missing = int(s.isna().sum())
    base = {
        "column": column,
        "dtype": str(s.dtype),
        "count": int(s.notna().sum()),
        "missing": missing,
        "missing_pct": round(100 * missing / max(len(df), 1), 4),
        "unique": int(s.nunique(dropna=True)),
    }

    if pd.api.types.is_numeric_dtype(s):
        clean = pd.to_numeric(s, errors="coerce").dropna()
        base["kind"] = "numeric"
        if clean.empty:
            return base
        q1, median, q3 = clean.quantile([0.25, 0.5, 0.75])
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        whisker_low = clean[clean >= lower_fence].min() if (clean >= lower_fence).any() else clean.min()
        whisker_high = clean[clean <= upper_fence].max() if (clean <= upper_fence).any() else clean.max()
        outliers = int(((clean < lower_fence) | (clean > upper_fence)).sum())

        unique_count = int(clean.nunique())
        bins_count = int(max(6, min(24, round(math.sqrt(len(clean))))))
        if unique_count <= 1:
            counts = np.array([len(clean)], dtype=int)
            edges = np.array([float(clean.iloc[0]) - 0.5, float(clean.iloc[0]) + 0.5])
        else:
            counts, edges = np.histogram(clean.to_numpy(dtype=float), bins=bins_count)

        base.update({
            "summary": {
                "min": _jsonable(clean.min()),
                "max": _jsonable(clean.max()),
                "mean": _jsonable(clean.mean()),
                "median": _jsonable(median),
                "std": _jsonable(clean.std(ddof=1)) if len(clean) > 1 else None,
                "variance": _jsonable(clean.var(ddof=1)) if len(clean) > 1 else None,
                "q1": _jsonable(q1),
                "q3": _jsonable(q3),
                "outliers_iqr": outliers,
            },
            "histogram": [
                {
                    "from": round(float(edges[i]), 6),
                    "to": round(float(edges[i + 1]), 6),
                    "count": int(counts[i]),
                }
                for i in range(len(counts))
            ],
            "boxplot": {
                "min": _jsonable(clean.min()),
                "q1": _jsonable(q1),
                "median": _jsonable(median),
                "q3": _jsonable(q3),
                "max": _jsonable(clean.max()),
                "whisker_low": _jsonable(whisker_low),
                "whisker_high": _jsonable(whisker_high),
                "outliers": outliers,
            },
        })
        return base

    clean = s.astype("string").dropna()
    base["kind"] = "categorical"
    counts = clean.value_counts(dropna=True).head(20)
    base["categories"] = [
        {"value": str(value), "count": int(count), "pct": round(100 * int(count) / max(len(clean), 1), 4)}
        for value, count in counts.items()
    ]
    return base
