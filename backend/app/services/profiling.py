from __future__ import annotations

import math
import re
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



def _temporal_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Detect temporal columns without treating arbitrary numeric/text columns as dates."""
    candidates: list[dict[str, Any]] = []
    name_hint = re.compile(r"(?:^|[_\s-])(date|datetime|timestamp|time|year|annee|année|month|mois|period|periode|période)(?:$|[_\s-])", re.I)
    date_shape = re.compile(r"(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}-\d{2}|\d{4})")

    for name in df.columns:
        series = df[name]
        non_null = series.dropna()
        if non_null.empty:
            continue
        column_name = str(name)
        hinted = bool(name_hint.search(column_name))

        # Native datetime columns are authoritative.
        if pd.api.types.is_datetime64_any_dtype(series):
            parsed = pd.to_datetime(non_null, errors="coerce", utc=True)
            valid = parsed.dropna()
            if valid.empty:
                continue
            candidates.append({
                "column": column_name,
                "kind": "datetime",
                "valid_count": int(len(valid)),
                "valid_ratio": round(float(len(valid)) / max(len(non_null), 1), 4),
                "start": valid.min().isoformat(),
                "end": valid.max().isoformat(),
                "confidence": 1.0,
            })
            continue

        # Numeric years are accepted only with a temporal column-name hint.
        if hinted and pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(non_null, errors="coerce").dropna()
            if not numeric.empty:
                plausible = numeric[(numeric >= 1000) & (numeric <= 3000)]
                integer_like = plausible[(plausible % 1).abs() < 1e-9]
                ratio = float(len(integer_like)) / max(len(numeric), 1)
                if ratio >= 0.8 and not integer_like.empty:
                    start_year = int(integer_like.min())
                    end_year = int(integer_like.max())
                    candidates.append({
                        "column": column_name,
                        "kind": "year",
                        "valid_count": int(len(integer_like)),
                        "valid_ratio": round(ratio, 4),
                        "start": f"{start_year:04d}-01-01T00:00:00+00:00",
                        "end": f"{end_year:04d}-12-31T23:59:59+00:00",
                        "confidence": round(min(0.99, 0.85 + 0.14 * ratio), 4),
                    })
                    continue

        # String/object parsing is intentionally conservative.
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series) or str(series.dtype).startswith("category")):
            continue
        sample = non_null.astype("string").head(250)
        shape_ratio = float(sample.str.contains(date_shape, regex=True, na=False).mean()) if len(sample) else 0.0
        if not hinted and shape_ratio < 0.65:
            continue
        try:
            parsed = pd.to_datetime(non_null.astype("string"), errors="coerce", utc=True, format="mixed")
        except TypeError:
            parsed = pd.to_datetime(non_null.astype("string"), errors="coerce", utc=True)
        valid = parsed.dropna()
        ratio = float(len(valid)) / max(len(non_null), 1)
        if ratio < (0.65 if hinted else 0.8) or valid.empty:
            continue
        confidence = 0.7 + min(0.25, 0.25 * ratio) + (0.04 if hinted else 0.0)
        candidates.append({
            "column": column_name,
            "kind": "datetime_text",
            "valid_count": int(len(valid)),
            "valid_ratio": round(ratio, 4),
            "start": valid.min().isoformat(),
            "end": valid.max().isoformat(),
            "confidence": round(min(confidence, 0.99), 4),
        })

    candidates.sort(key=lambda item: (item.get("confidence", 0), item.get("valid_count", 0)), reverse=True)
    primary = candidates[0] if candidates else None
    return {
        "detected": bool(candidates),
        "primary": primary,
        "columns": candidates,
    }


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
        "temporal": _temporal_profile(df),
    }
