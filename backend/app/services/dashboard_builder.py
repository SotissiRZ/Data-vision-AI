from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.services.storage import get_meta
from app.services.visualization import build_visualization
from app.services.quality import quality_report
from app.services.semantic_layer import get_semantic_model, query_semantic_metric, semantic_filtered_base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir() -> Path:
    path = get_settings().data_root / "dashboards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(dashboard_id: str) -> Path:
    return _dir() / f"{dashboard_id}.json"


def _normalize_layout(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(widgets[:40]):
        item = dict(raw)
        item.setdefault("id", str(uuid.uuid4()))
        item.setdefault("title", f"Widget {index + 1}")
        item.setdefault("type", "chart")
        size = str(item.get("size", "medium"))
        if size not in {"small", "medium", "large", "full"}:
            size = "medium"
        item["size"] = size
        item["order"] = index
        out.append(item)
    return out


def save_dashboard(dataset_id: str, *, name: str, description: str = "", dashboard_id: str | None = None,
                   filters: list[dict[str, Any]] | None = None, widgets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    meta = get_meta(dataset_id)
    now = _now()
    existing: dict[str, Any] | None = None
    if dashboard_id and _path(dashboard_id).exists():
        existing = json.loads(_path(dashboard_id).read_text(encoding="utf-8"))
        if existing.get("root_id") != (meta.get("root_id") or meta["id"]):
            raise ValueError("Ce dashboard appartient à un autre dataset")
    did = dashboard_id or str(uuid.uuid4())
    row = {
        "id": did,
        "dataset_id": dataset_id,
        "root_id": meta.get("root_id") or meta["id"],
        "dataset_version": int(meta.get("version", 1)),
        "name": (name or "Dashboard DataVision").strip()[:180],
        "description": (description or "").strip()[:500],
        "filters": filters or [],
        "widgets": _normalize_layout(widgets or []),
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
        "schema_version": 1,
    }
    _path(did).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def get_dashboard_definition(dashboard_id: str) -> dict[str, Any]:
    path = _path(dashboard_id)
    if not path.exists():
        raise FileNotFoundError(dashboard_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_dashboards(dataset_id: str) -> list[dict[str, Any]]:
    meta = get_meta(dataset_id)
    root_id = meta.get("root_id") or meta["id"]
    rows: list[dict[str, Any]] = []
    for path in _dir().glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if item.get("root_id") == root_id:
            rows.append({
                "id": item.get("id"), "name": item.get("name"), "description": item.get("description", ""),
                "dataset_id": item.get("dataset_id"), "dataset_version": item.get("dataset_version", 1),
                "widget_count": len(item.get("widgets", [])), "filter_count": len(item.get("filters", [])),
                "created_at": item.get("created_at"), "updated_at": item.get("updated_at"),
            })
    rows.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return rows


def delete_dashboard(dataset_id: str, dashboard_id: str) -> None:
    meta = get_meta(dataset_id)
    item = get_dashboard_definition(dashboard_id)
    if item.get("root_id") != (meta.get("root_id") or meta["id"]):
        raise FileNotFoundError(dashboard_id)
    _path(dashboard_id).unlink(missing_ok=True)


def _coerce_for_series(series: pd.Series, value: Any) -> Any:
    if value is None:
        return None
    if pd.api.types.is_numeric_dtype(series):
        try:
            return float(value)
        except Exception:
            return value
    dt = pd.to_datetime(series, errors="coerce", format="mixed")
    if dt.notna().mean() > 0.8:
        try:
            return pd.to_datetime(value)
        except Exception:
            return value
    return str(value)


def apply_filters(df: pd.DataFrame, filters: list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    out = df.copy()
    applied: list[dict[str, Any]] = []
    for raw in filters or []:
        column = str(raw.get("column") or "")
        operator = str(raw.get("operator") or "eq")
        if column not in out.columns:
            continue
        s = out[column]
        value = raw.get("value")
        value2 = raw.get("value2")
        try:
            if operator == "is_null":
                mask = s.isna()
            elif operator == "not_null":
                mask = s.notna()
            elif operator == "contains":
                mask = s.astype(str).str.contains(str(value or ""), case=False, na=False, regex=False)
            elif operator in {"gt", "gte", "lt", "lte", "between"}:
                if pd.api.types.is_numeric_dtype(s):
                    cmp = pd.to_numeric(s, errors="coerce")
                    a = float(value)
                    b = float(value2) if value2 is not None else None
                else:
                    parsed = pd.to_datetime(s, errors="coerce", format="mixed")
                    if parsed.notna().mean() > 0.8:
                        cmp = parsed
                        a = pd.to_datetime(value)
                        b = pd.to_datetime(value2) if value2 is not None else None
                    else:
                        cmp = s.astype(str)
                        a = str(value)
                        b = str(value2) if value2 is not None else None
                if operator == "gt": mask = cmp > a
                elif operator == "gte": mask = cmp >= a
                elif operator == "lt": mask = cmp < a
                elif operator == "lte": mask = cmp <= a
                else: mask = (cmp >= a) & (cmp <= b)
            elif operator == "neq":
                target = _coerce_for_series(s, value)
                if pd.api.types.is_numeric_dtype(s): mask = pd.to_numeric(s, errors="coerce") != target
                else: mask = s.astype(str) != str(target)
            else:
                target = _coerce_for_series(s, value)
                if pd.api.types.is_numeric_dtype(s): mask = pd.to_numeric(s, errors="coerce") == target
                else: mask = s.astype(str) == str(target)
            out = out.loc[mask.fillna(False) if hasattr(mask, "fillna") else mask]
            applied.append({"column": column, "operator": operator, "value": value, "value2": value2})
        except Exception:
            continue
    return out, applied


def _kpi(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    metric = str(config.get("metric") or "rows")
    column = config.get("column")
    value: Any
    detail = ""
    if metric == "rows":
        value = int(len(df)); detail = "observations après filtres"
    elif metric == "columns":
        value = int(df.shape[1]); detail = "variables"
    elif metric == "missing_cells":
        value = int(df.isna().sum().sum()); detail = "cellules manquantes"
    elif metric == "duplicates":
        value = int(df.duplicated().sum()); detail = "lignes dupliquées"
    elif metric == "quality_score":
        value = int(quality_report(df).get("score", 0)); detail = "score qualité / 100"
    else:
        if not column or column not in df.columns:
            raise ValueError("Ce KPI nécessite une colonne valide")
        s = df[column]
        if metric == "nunique": value = int(s.nunique(dropna=True))
        elif metric == "missing_pct": value = round(float(s.isna().mean() * 100), 3)
        else:
            num = pd.to_numeric(s, errors="coerce").dropna()
            if num.empty: raise ValueError("KPI numérique impossible sur cette colonne")
            funcs = {"mean": num.mean, "sum": num.sum, "median": num.median, "min": num.min, "max": num.max}
            if metric not in funcs: raise ValueError("Métrique KPI non supportée")
            raw = float(funcs[metric]())
            value = raw if math.isfinite(raw) else None
        detail = str(column)
    return {"type": "kpi", "metric": metric, "column": column, "value": value, "detail": detail}


def _semantic_filters(filters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in filters or []:
        ref = str(raw.get("dimension") or raw.get("column") or "")
        if not ref:
            continue
        op = str(raw.get("operator") or "eq")
        # Semantic engine uses ne while legacy dashboard builder uses neq.
        if op == "neq": op = "ne"
        value = raw.get("value")
        if op == "between":
            value = [raw.get("value"), raw.get("value2")]
        out.append({"dimension": ref, "operator": op, "value": value, "min": raw.get("value"), "max": raw.get("value2")})
    return out


def _semantic_widget(dataset_id: str, df: pd.DataFrame, raw: dict[str, Any], filters: list[dict[str, Any]] | None) -> dict[str, Any]:
    cfg = dict(raw.get("config") or {})
    metric_id = str(cfg.get("metric_id") or "")
    if not metric_id:
        raise ValueError("Le widget sémantique nécessite une métrique métier.")
    model = get_semantic_model(dataset_id, df)
    widget_type = str(raw.get("type") or "semantic_chart")
    if widget_type == "semantic_kpi":
        query = query_semantic_metric(dataset_id, df, metric_id, [], _semantic_filters(filters), 1)
        metric = query.get("metric") or {}
        return {
            "type": "kpi", "semantic": True, "metric_id": metric_id, "value": query.get("value"),
            "detail": metric.get("label") or metric.get("name") or metric_id,
            "unit": metric.get("unit") or "", "semantic_model_version": query.get("semantic_model_version"),
        }

    hierarchy_id = str(cfg.get("hierarchy_id") or "")
    hierarchy = next((h for h in model.get("hierarchies", []) if h.get("id") == hierarchy_id), None) if hierarchy_id else None
    level = max(0, int(cfg.get("hierarchy_level") or 0))
    dimension = str(cfg.get("dimension") or "")
    drill = None
    if hierarchy and hierarchy.get("levels"):
        levels = list(hierarchy.get("levels") or [])
        level = min(level, len(levels)-1)
        dimension = str(levels[level])
        drill = {
            "hierarchy_id": hierarchy_id, "level": level, "dimension": dimension,
            "next_dimension": levels[level+1] if level+1 < len(levels) else None,
            "next_level": level+1 if level+1 < len(levels) else None,
            "levels": levels,
        }
    date_dimension = str(cfg.get("date_dimension") or "") or None
    time_grain = str(cfg.get("time_grain") or "") or None
    if date_dimension and not time_grain:
        time_grain = "month"
    dimensions = [dimension] if dimension else []
    query = query_semantic_metric(
        dataset_id, df, metric_id, dimensions, _semantic_filters(filters), int(cfg.get("limit") or 100),
        date_dimension, time_grain, str(cfg.get("comparison") or "none"),
        str(cfg.get("time_calculation") or "none"), int(cfg.get("rolling_window") or 3),
    )
    metric = query.get("metric") or {}
    chart_type = str(cfg.get("chart_type") or ("line" if date_dimension else "bar"))
    rows = query.get("result") or []
    x_key = date_dimension if date_dimension else dimension
    value_key = "time_value" if str(cfg.get("display_value") or "value") == "time_value" else "value"
    data = []
    for row in rows:
        label = row.get(x_key) if x_key else metric.get("label") or metric_id
        data.append({"label": label, "value": row.get(value_key), **row})
    return {
        "type": chart_type, "semantic": True, "metric_id": metric_id, "metric_label": metric.get("label") or metric_id,
        "unit": metric.get("unit") or "", "x": x_key, "value_label": metric.get("label") or metric_id,
        "data": data, "query": {k: query.get(k) for k in ("dimensions","comparison","time_calculation","time_grain","semantic_model_version")},
        "drill": drill,
    }


def preview_dashboard(dataset_id: str, df: pd.DataFrame, *, filters: list[dict[str, Any]] | None, widgets: list[dict[str, Any]]) -> dict[str, Any]:
    # Semantic filtering is applied first so a cross-filter on a linked dimension constrains legacy
    # KPI/charts too. Safe N:1/1:1 relationships preserve fact-row cardinality.
    try:
        filtered = semantic_filtered_base(dataset_id, df, filters or []) if filters else df.copy()
        applied = list(filters or [])
    except Exception:
        # Fail closed for an explicitly semantic filter; keep backward compatibility for purely
        # physical dashboards only when no dimension marker is present.
        if any(f.get("dimension") or f.get("source") in {"semantic", "drill"} for f in filters or []):
            raise
        filtered, applied = apply_filters(df, filters)
    rendered: list[dict[str, Any]] = []
    for raw in _normalize_layout(widgets):
        item = {"id": raw["id"], "title": raw.get("title"), "type": raw.get("type"), "size": raw.get("size"), "order": raw.get("order")}
        try:
            if raw.get("type") in {"semantic_kpi", "semantic_chart"}:
                item["result"] = _semantic_widget(dataset_id, df, raw, filters)
            elif raw.get("type") == "kpi":
                item["result"] = _kpi(filtered, raw.get("config") or {})
            elif raw.get("type") == "text":
                item["result"] = {"type": "text", "text": str((raw.get("config") or {}).get("text") or "")}
            else:
                cfg = dict(raw.get("config") or {})
                item["result"] = build_visualization(
                    filtered,
                    chart_type=str(cfg.get("chart_type") or "auto"),
                    x=cfg.get("x"), y=cfg.get("y"), color=cfg.get("color"),
                    aggregation=str(cfg.get("aggregation") or "none"), bins=int(cfg.get("bins") or 20),
                )
            item["status"] = "ok"
        except Exception as exc:
            item["status"] = "error"; item["error"] = str(exc); item["result"] = None
        rendered.append(item)
    semantic_count = sum(1 for w in widgets if w.get("type") in {"semantic_kpi", "semantic_chart"})
    return {
        "rows_before": int(len(df)), "rows_after": int(len(filtered)), "filter_count": len(applied),
        "filters_applied": applied, "widgets": rendered, "semantic_widgets": semantic_count,
        "calculation_policy": "deterministic_engines_only",
    }

