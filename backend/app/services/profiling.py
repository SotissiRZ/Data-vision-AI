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
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def profile_dataframe(df: pd.DataFrame) -> dict:
    columns = []
    for name in df.columns:
        s = df[name]
        missing = int(s.isna().sum())
        item = {
            "name": str(name),
            "dtype": str(s.dtype),
            "count": int(s.notna().sum()),
            "missing": missing,
            "missing_pct": round(100 * missing / max(len(df), 1), 4),
            "unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            clean = s.dropna()
            if not clean.empty:
                q = clean.quantile([0.25, 0.5, 0.75])
                item.update({
                    "min": _jsonable(clean.min()),
                    "max": _jsonable(clean.max()),
                    "mean": _jsonable(clean.mean()),
                    "median": _jsonable(clean.median()),
                    "variance": _jsonable(clean.var(ddof=1)) if len(clean) > 1 else None,
                    "std": _jsonable(clean.std(ddof=1)) if len(clean) > 1 else None,
                    "q1": _jsonable(q.loc[0.25]),
                    "q3": _jsonable(q.loc[0.75]),
                })
        else:
            top = s.astype("string").value_counts(dropna=True).head(5)
            item["top_values"] = [{"value": _jsonable(k), "count": int(v)} for k, v in top.items()]
        columns.append(item)

    return {
        "rows": int(len(df)),
        "columns_count": int(len(df.columns)),
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
        "duplicates": int(df.duplicated().sum()),
        "columns": columns,
    }
