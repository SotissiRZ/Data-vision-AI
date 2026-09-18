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


def preview_dashboard(df: pd.DataFrame, *, filters: list[dict[str, Any]] | None, widgets: list[dict[str, Any]]) -> dict[str, Any]:
    filtered, applied = apply_filters(df, filters)
    rendered: list[dict[str, Any]] = []
    for raw in _normalize_layout(widgets):
        item = {"id": raw["id"], "title": raw.get("title"), "type": raw.get("type"), "size": raw.get("size"), "order": raw.get("order")}
        try:
            if raw.get("type") == "kpi":
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
    return {
        "rows_before": int(len(df)), "rows_after": int(len(filtered)), "filter_count": len(applied),
        "filters_applied": applied, "widgets": rendered, "calculation_policy": "deterministic_engines_only",
    }
