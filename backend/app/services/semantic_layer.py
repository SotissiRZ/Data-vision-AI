from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.storage import get_meta

_ALLOWED_AGGS = {"sum", "mean", "median", "min", "max", "count", "nunique"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root_dir() -> Path:
    path = get_settings().data_root / "semantic"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _root_id(dataset_id: str) -> str:
    meta = get_meta(dataset_id)
    return str(meta.get("root_id") or meta["id"])


def _path(dataset_id: str) -> Path:
    return _root_dir() / f"{_root_id(dataset_id)}.json"


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
    return text or f"metric_{uuid.uuid4().hex[:8]}"


def _is_identifier(name: str, series: pd.Series) -> bool:
    n = name.lower()
    by_name = n in {"id", "index", "row", "record", "patient_id", "customer_id", "user_id"} or n.endswith("_id")
    id_token = any(t in n for t in ("uuid", "identifier", "identifiant", "record_no", "record_number", "primary_key"))
    high_unique = len(series) > 20 and series.nunique(dropna=True) / max(len(series), 1) > .98
    return by_name or (id_token and high_unique)


def _suggest(df: pd.DataFrame) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    for col in df.columns:
        name = str(col)
        s = df[col]
        if _is_identifier(name, s):
            continue
        if pd.api.types.is_numeric_dtype(s):
            lower = name.lower()
            agg = "sum" if any(t in lower for t in ("revenue", "sales", "amount", "cost", "profit", "quantity", "qty", "volume", "ca", "chiffre")) else "mean"
            metrics.append({
                "id": _slug(name), "name": name, "label": name.replace("_", " "), "column": name,
                "aggregation": agg, "unit": "", "description": "", "synonyms": [], "certified": False,
                "source": "suggested",
            })
        else:
            dimensions.append({
                "column": name, "label": name.replace("_", " "), "description": "", "synonyms": [],
                "hidden": False, "source": "suggested",
            })
    return {"metrics": metrics[:24], "dimensions": dimensions[:32]}


def get_semantic_model(dataset_id: str, df: pd.DataFrame) -> dict[str, Any]:
    path = _path(dataset_id)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["dataset_id"] = dataset_id
        payload["root_id"] = _root_id(dataset_id)
        return payload
    suggested = _suggest(df)
    return {
        "dataset_id": dataset_id,
        "root_id": _root_id(dataset_id),
        "version": 1,
        "status": "draft",
        "metrics": suggested["metrics"],
        "dimensions": suggested["dimensions"],
        "business_glossary": [],
        "updated_at": None,
        "source": "auto_suggested",
    }


def save_semantic_model(dataset_id: str, df: pd.DataFrame, payload: dict[str, Any]) -> dict[str, Any]:
    columns = {str(c) for c in df.columns}
    metrics: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in payload.get("metrics", []):
        column = str(raw.get("column") or "")
        if column not in columns:
            raise ValueError(f"Colonne métrique inconnue: {column}")
        agg = str(raw.get("aggregation") or "mean").lower()
        if agg not in _ALLOWED_AGGS:
            raise ValueError(f"Agrégation non supportée: {agg}")
        metric_id = _slug(str(raw.get("id") or raw.get("name") or column))
        if metric_id in seen:
            raise ValueError(f"Identifiant de métrique dupliqué: {metric_id}")
        seen.add(metric_id)
        metrics.append({
            "id": metric_id,
            "name": str(raw.get("name") or raw.get("label") or column),
            "label": str(raw.get("label") or raw.get("name") or column),
            "column": column,
            "aggregation": agg,
            "unit": str(raw.get("unit") or "")[:32],
            "description": str(raw.get("description") or "")[:500],
            "synonyms": [str(x)[:80] for x in raw.get("synonyms", []) if str(x).strip()][:20],
            "certified": bool(raw.get("certified", False)),
            "source": "user",
        })
    dimensions: list[dict[str, Any]] = []
    for raw in payload.get("dimensions", []):
        column = str(raw.get("column") or "")
        if column not in columns:
            raise ValueError(f"Dimension inconnue: {column}")
        dimensions.append({
            "column": column,
            "label": str(raw.get("label") or column),
            "description": str(raw.get("description") or "")[:500],
            "synonyms": [str(x)[:80] for x in raw.get("synonyms", []) if str(x).strip()][:20],
            "hidden": bool(raw.get("hidden", False)),
            "source": "user",
        })
    glossary = []
    for raw in payload.get("business_glossary", []):
        term = str(raw.get("term") or "").strip()
        if term:
            glossary.append({"term": term[:120], "definition": str(raw.get("definition") or "")[:1000]})
    previous = get_semantic_model(dataset_id, df)
    out = {
        "dataset_id": dataset_id,
        "root_id": _root_id(dataset_id),
        "version": int(previous.get("version") or 0) + 1,
        "status": "governed",
        "metrics": metrics,
        "dimensions": dimensions,
        "business_glossary": glossary,
        "updated_at": _now(),
        "source": "saved",
    }
    _path(dataset_id).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _apply_filters(df: pd.DataFrame, filters: list[dict[str, Any]]) -> pd.DataFrame:
    out = df.copy()
    for f in filters or []:
        col = str(f.get("column") or "")
        if col not in out.columns:
            continue
        op = str(f.get("operator") or "eq")
        value = f.get("value")
        s = out[col]
        if op == "eq": out = out[s.astype(str) == str(value)]
        elif op == "ne": out = out[s.astype(str) != str(value)]
        elif op == "contains": out = out[s.astype(str).str.contains(str(value), case=False, na=False)]
        elif op in {"gt", "gte", "lt", "lte"}:
            numeric = pd.to_numeric(s, errors="coerce")
            val = float(value)
            mask = {"gt": numeric > val, "gte": numeric >= val, "lt": numeric < val, "lte": numeric <= val}[op]
            out = out[mask]
        elif op == "is_null": out = out[s.isna()]
        elif op == "not_null": out = out[s.notna()]
    return out


def _metric_value(series: pd.Series, aggregation: str) -> float | int | None:
    if aggregation == "count": return int(series.notna().sum())
    if aggregation == "nunique": return int(series.nunique(dropna=True))
    num = pd.to_numeric(series, errors="coerce").dropna()
    if num.empty: return None
    value = {
        "sum": num.sum, "mean": num.mean, "median": num.median, "min": num.min, "max": num.max,
    }[aggregation]()
    if isinstance(value, (np.integer, np.floating)): return value.item()
    return float(value)


def evaluate_metric(dataset_id: str, df: pd.DataFrame, metric_id: str, dimensions: list[str] | None = None, filters: list[dict[str, Any]] | None = None, limit: int = 200) -> dict[str, Any]:
    semantic = get_semantic_model(dataset_id, df)
    metric = next((m for m in semantic.get("metrics", []) if m.get("id") == metric_id), None)
    if not metric:
        raise ValueError(f"Métrique inconnue: {metric_id}")
    column = metric["column"]
    aggregation = metric["aggregation"]
    work = _apply_filters(df, filters or [])
    dims = [d for d in (dimensions or []) if d in work.columns][:3]
    if not dims:
        return {
            "metric": metric, "value": _metric_value(work[column], aggregation), "rows": int(len(work)),
            "dimensions": [], "result": [], "filters": filters or [], "calculation_policy": "deterministic",
        }
    grouped = work.groupby(dims, dropna=False)[column]
    if aggregation == "count": values = grouped.count()
    elif aggregation == "nunique": values = grouped.nunique()
    else:
        numeric = pd.to_numeric(work[column], errors="coerce")
        temp = work.assign(__metric__=numeric).groupby(dims, dropna=False)["__metric__"]
        values = getattr(temp, aggregation)()
    result = values.reset_index(name="value").sort_values("value", ascending=False).head(max(1, min(limit, 500))).to_dict(orient="records")
    return {
        "metric": metric, "value": _metric_value(work[column], aggregation), "rows": int(len(work)),
        "dimensions": dims, "result": result, "filters": filters or [], "calculation_policy": "deterministic",
    }


def metric_pulse(dataset_id: str, df: pd.DataFrame, metric_id: str, date_column: str | None = None, periods: int = 12) -> dict[str, Any]:
    semantic = get_semantic_model(dataset_id, df)
    metric = next((m for m in semantic.get("metrics", []) if m.get("id") == metric_id), None)
    if not metric:
        raise ValueError(f"Métrique inconnue: {metric_id}")
    current = _metric_value(df[metric["column"]], metric["aggregation"])
    result: dict[str, Any] = {"metric": metric, "current": current, "trend": [], "delta_pct": None, "status": "stable", "calculation_policy": "deterministic"}
    if not date_column or date_column not in df.columns:
        return result
    dates = pd.to_datetime(df[date_column], errors="coerce")
    work = df.assign(__date__=dates).dropna(subset=["__date__"]).copy()
    if work.empty:
        return result
    work["__period__"] = work["__date__"].dt.to_period("M").dt.to_timestamp()
    grouped = []
    for period, g in work.groupby("__period__"):
        grouped.append({"period": period.isoformat(), "value": _metric_value(g[metric["column"]], metric["aggregation"])})
    grouped = [x for x in grouped if x["value"] is not None][-max(2, min(periods, 36)):]
    result["trend"] = grouped
    if len(grouped) >= 2:
        prev = float(grouped[-2]["value"])
        last = float(grouped[-1]["value"])
        if abs(prev) > 1e-12:
            delta = (last - prev) / abs(prev) * 100
            result["delta_pct"] = delta
            result["status"] = "up" if delta > 1 else "down" if delta < -1 else "stable"
        values = np.array([float(x["value"]) for x in grouped[:-1]], dtype=float)
        if len(values) >= 4 and float(np.std(values)) > 0:
            z = (last - float(np.mean(values))) / float(np.std(values))
            result["anomaly_z"] = z
            result["anomaly"] = abs(z) >= 2.5
    return result
