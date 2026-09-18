from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

import pandas as pd

from app.services.semantic_layer import get_semantic_model, query_semantic_metric


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.replace("_", " ").replace("-", " ")).strip()


def _terms(item: dict[str, Any], *, dimension: bool = False) -> list[str]:
    values = [item.get("id"), item.get("label"), item.get("name"), *(item.get("synonyms") or [])]
    if dimension:
        values.extend([item.get("column")])
    out: list[str] = []
    for value in values:
        term = _norm(str(value or ""))
        if len(term) >= 2 and term not in out:
            out.append(term)
    return out


def _best_match(question: str, items: list[dict[str, Any]], *, dimension: bool = False) -> tuple[dict[str, Any] | None, float]:
    q = _norm(question)
    best: dict[str, Any] | None = None
    best_score = 0.0
    for item in items:
        if dimension and item.get("hidden"):
            continue
        score = 0.0
        for term in _terms(item, dimension=dimension):
            if term in q:
                # Longer business phrases are more discriminating than short ids.
                score = max(score, min(20.0, len(term)) + (4.0 if " " in term else 0.0))
        if score:
            if item.get("certified"):
                score += 3.0
            if score > best_score:
                best, best_score = item, score
    return best, best_score


def _mentioned_dimensions(question: str, model: dict[str, Any]) -> list[dict[str, Any]]:
    q = _norm(question)
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for dim in model.get("dimensions", []):
        if dim.get("hidden"):
            continue
        positions: list[int] = []
        best_len = 0
        for term in _terms(dim, dimension=True):
            pos = q.find(term)
            if pos >= 0:
                positions.append(pos)
                best_len = max(best_len, len(term))
        if positions:
            ranked.append((min(positions), -best_len, dim))
    ranked.sort(key=lambda x: (x[0], x[1]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, __, dim in ranked:
        if dim.get("id") not in seen:
            out.append(dim); seen.add(str(dim.get("id")))
    return out


def _aggregation_override(question: str) -> str | None:
    q = _norm(question)
    mapping = [
        ("mean", ("moyenne", "moyen", "average", "avg")),
        ("sum", ("somme", "total", "sum")),
        ("median", ("mediane", "median")),
        ("min", ("minimum", "plus petit")),
        ("max", ("maximum", "plus grand")),
        ("count", ("nombre de", "count")),
    ]
    for agg, words in mapping:
        if any(w in q for w in words):
            return agg
    return None


def _display_sql(plan: dict[str, Any], model: dict[str, Any]) -> str:
    metric = next((m for m in model.get("metrics", []) if m.get("id") == plan.get("metric_id")), {})
    agg = str(plan.get("aggregation_override") or metric.get("aggregation") or "mean").upper()
    if agg == "MEAN": agg = "AVG"
    if agg == "NUNIQUE": agg = "COUNT_DISTINCT"
    column = str(metric.get("column") or metric.get("id") or "metric")
    metric_expr = f'{agg}("{column}")' if metric.get("type") != "calculated" else f'SEMANTIC_METRIC("{metric.get("id")}")'
    dims = []
    for did in plan.get("dimensions") or []:
        dim = next((d for d in model.get("dimensions", []) if d.get("id") == did), {})
        physical = str(dim.get("column") or did)
        dims.append(f'"{physical}"' if dim.get("table", "base") == "base" else f'"{dim.get("table")}.{physical}"')
    if plan.get("date_dimension"):
        dim = next((d for d in model.get("dimensions", []) if d.get("id") == plan.get("date_dimension")), {})
        physical = str(dim.get("column") or plan.get("date_dimension"))
        dims.append(f'DATE_{str(plan.get("time_grain") or "month").upper()}("{physical}")')
    select = ", ".join([*dims, f'{metric_expr} AS "{plan.get("metric_id")}"'])
    group = f" GROUP BY {', '.join(dims)}" if dims else ""
    source = "dataset" if set(plan.get("tables") or ["base"]) <= {"base"} else "SEMANTIC_MODEL /* joins governed by relationships */"
    return f"SELECT {select} FROM {source}{group}"


def _time_options(question: str, dimensions: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    q = _norm(question)
    grain = None
    grain_terms = [
        ("day", ("par jour", "quotidien", "daily", "jour par jour")),
        ("week", ("par semaine", "hebdo", "weekly", "semaine par semaine")),
        ("month", ("par mois", "mensuel", "monthly", "mois par mois")),
        ("quarter", ("par trimestre", "trimestriel", "quarterly", "quarter")),
        ("year", ("par an", "par annee", "annuel", "yearly", "annee par annee")),
    ]
    for key, words in grain_terms:
        if any(w in q for w in words):
            grain = key; break

    comparison = "none"
    if any(w in q for w in ("yoy", "year over year", "annee precedente", "n-1", "vs l an dernier", "versus l an dernier")):
        comparison = "yoy"
    elif any(w in q for w in ("periode precedente", "mois precedent", "trimestre precedent", "previous period", "precedent")):
        comparison = "previous_period"

    time_calculation = "none"
    if any(w in q for w in ("ytd", "depuis le debut de l annee", "cumul annuel")):
        time_calculation = "ytd"
    elif any(w in q for w in ("cumul", "cumulative", "running total")):
        time_calculation = "running_total"
    elif any(w in q for w in ("moyenne mobile", "moving average", "rolling mean")):
        time_calculation = "rolling_mean"
    elif any(w in q for w in ("somme mobile", "rolling sum")):
        time_calculation = "rolling_sum"

    date_dim = next((d for d in dimensions if d.get("kind") == "date"), None)
    if not date_dim and (grain or comparison != "none" or time_calculation != "none"):
        date_dim = next((d for d in model.get("dimensions", []) if not d.get("hidden") and d.get("kind") == "date"), None)
    return {
        "date_dimension": date_dim.get("id") if date_dim else None,
        "time_grain": grain,
        "comparison": comparison,
        "time_calculation": time_calculation,
    }


def plan_semantic_question(dataset_id: str, df: pd.DataFrame, question: str, limit: int = 200, model: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve a business-language question against the governed semantic model.

    The planner never calculates values. It only resolves metric/dimensions/time intent; execution
    is delegated to the deterministic Semantic Query Engine.
    """
    raw = (question or "").strip()
    if not raw:
        return None
    model = model or get_semantic_model(dataset_id, df)
    metric, metric_score = _best_match(raw, model.get("metrics", []), dimension=False)
    if not metric:
        return None

    dimensions = _mentioned_dimensions(raw, model)
    # The metric's own physical column should not accidentally become a grouping dimension just
    # because labels share text (common in auto-suggested single-table models).
    dimensions = [d for d in dimensions if not (metric.get("type") != "calculated" and d.get("table", "base") == metric.get("table", "base") and d.get("column") == metric.get("column"))]
    dim_ids = [str(d.get("id")) for d in dimensions if d.get("id")]
    time = _time_options(raw, dimensions, model)
    if time["date_dimension"] and time["date_dimension"] in dim_ids:
        dim_ids = [d for d in dim_ids if d != time["date_dimension"]]

    top = re.search(r"\btop\s+(\d+)\b", _norm(raw))
    effective_limit = min(max(1, int(top.group(1))) if top else max(1, int(limit)), 5000)
    confidence = "high" if metric_score >= 8 and metric.get("certified") else "medium"
    return {
        "metric_id": str(metric["id"]),
        "metric_label": metric.get("label") or metric.get("name") or metric.get("id"),
        "metric_certified": bool(metric.get("certified")),
        "dimensions": dim_ids,
        "filters": [],
        "limit": effective_limit,
        **time,
        "rolling_window": 3,
        "aggregation_override": _aggregation_override(raw),
        "confidence": confidence,
        "semantic_model_version": model.get("version"),
        "semantic_version": model.get("semantic_version", 2),
        "tables": sorted({str(metric.get("table", "base")), *[str(d.get("table", "base")) for d in dimensions]}),
    }


def execute_semantic_question(dataset_id: str, df: pd.DataFrame, question: str, limit: int = 200, model: dict[str, Any] | None = None) -> dict[str, Any] | None:
    plan = plan_semantic_question(dataset_id, df, question, limit, model)
    if not plan:
        return None
    started = time.perf_counter()
    result = query_semantic_metric(
        dataset_id,
        df,
        plan["metric_id"],
        plan["dimensions"],
        plan["filters"],
        plan["limit"],
        plan["date_dimension"],
        plan["time_grain"],
        plan["comparison"],
        plan["time_calculation"],
        plan["rolling_window"],
        plan.get("aggregation_override"),
    )
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return {"plan": plan, "query": result, "display_sql": _display_sql(plan, model or get_semantic_model(dataset_id, df))}


def semantic_result_as_table(execution: dict[str, Any]) -> dict[str, Any]:
    plan, query = execution["plan"], execution["query"]
    rows = query.get("result") or []
    if not rows:
        rows = [{plan["metric_id"]: query.get("value")}]
        columns = [plan["metric_id"]]
    else:
        columns = list(rows[0].keys())
    return {
        "columns": columns,
        "rows": rows,
        "returned_rows": len(rows),
        "limit": plan.get("limit", 200),
        "truncated": len(rows) >= int(plan.get("limit", 200)),
        "elapsed_ms": query.get("elapsed_ms", 0),
        "engine": "semantic_query_engine_v2",
    }
