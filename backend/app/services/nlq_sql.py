from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from app.services.data_workspace import run_sql


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).replace("_", " ").replace("-", " ")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _mentioned(question: str, df: pd.DataFrame) -> list[str]:
    q = _norm(question)
    found: list[tuple[int, str]] = []
    for col in df.columns:
        name = str(col)
        candidates = {_norm(name), _norm(name.replace("_", " "))}
        positions = [q.find(c) for c in candidates if c and q.find(c) >= 0]
        if positions:
            found.append((min(positions), name))
    found.sort(key=lambda x: x[0])
    return [name for _, name in found]


def _numeric(df: pd.DataFrame, column: str) -> bool:
    return column in df.columns and pd.api.types.is_numeric_dtype(df[column])


def translate_nlq(df: pd.DataFrame, question: str, limit: int = 200, semantic: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (question or "").strip()
    if not raw:
        raise ValueError("La question est vide")
    q = _norm(raw)
    semantic = semantic or {}
    semantic_metric = None
    semantic_dimension = None
    for metric in semantic.get("metrics", []):
        terms = [metric.get("id"), metric.get("name"), metric.get("label"), *(metric.get("synonyms") or [])]
        if any(_norm(str(t)) in q for t in terms if t and len(_norm(str(t))) >= 2):
            semantic_metric = metric
            break
    for dim in semantic.get("dimensions", []):
        if dim.get("hidden"):
            continue
        terms = [dim.get("column"), dim.get("label"), *(dim.get("synonyms") or [])]
        if any(_norm(str(t)) in q for t in terms if t and len(_norm(str(t))) >= 2):
            semantic_dimension = dim.get("column")
            break
    if semantic_metric:
        explicit_agg_map = [
            (("moyenne", "moyen", "average", "avg"), "AVG", "mean"),
            (("somme", "total", "sum"), "SUM", "sum"),
            (("minimum", "min ", "plus petit"), "MIN", "min"),
            (("maximum", "max ", "plus grand"), "MAX", "max"),
            (("mediane", "median"), "MEDIAN", "median"),
        ]
        explicit = next(((sql, key) for words, sql, key in explicit_agg_map if any(w in q for w in words)), None)
        semantic_agg = str(semantic_metric.get("aggregation", "mean")).lower()
        if explicit:
            agg_sql, semantic_agg = explicit
        else:
            agg_sql = {"sum":"SUM","mean":"AVG","min":"MIN","max":"MAX","count":"COUNT","nunique":"COUNT(DISTINCT","median":"MEDIAN"}.get(semantic_agg,"AVG")
        column = str(semantic_metric.get("column"))
        metric_name = str(semantic_metric.get("label") or semantic_metric.get("name") or semantic_metric.get("id"))
        assumptions=[]
        if semantic_agg == "median":
            # DuckDB supports MEDIAN, but the SQLite fallback used in some local test environments does not.
            agg_sql = "AVG"
            assumptions.append("La médiane est approximée par AVG dans le traducteur SQL portable; utilisez l'évaluation sémantique dédiée pour une médiane exacte.")
        if agg_sql == "COUNT(DISTINCT":
            expr=f"COUNT(DISTINCT {_q(column)})"
        elif agg_sql == "COUNT":
            expr=f"COUNT({_q(column)})"
        else:
            expr=f"{agg_sql}({_q(column)})"
        alias=_q(str(semantic_metric.get("id") or "metric"))
        if semantic_dimension:
            sql=f"SELECT {_q(str(semantic_dimension))}, {expr} AS {alias} FROM dataset GROUP BY {_q(str(semantic_dimension))} ORDER BY {alias} DESC LIMIT {max(1,min(int(limit),5000))}"
            reasoning=f"Métrique gouvernée {metric_name} ventilée par {semantic_dimension}."
        else:
            sql=f"SELECT {expr} AS {alias} FROM dataset"
            reasoning=f"Métrique gouvernée {metric_name}."
        return {"sql":sql,"reasoning":reasoning,"assumptions":assumptions,"confidence":"high","mentioned_columns":[column]+([semantic_dimension] if semantic_dimension else []),"semantic_grounding":{"metric_id":semantic_metric.get("id"),"dimension":semantic_dimension,"certified":bool(semantic_metric.get("certified"))}}
    augmented = raw
    for dim in semantic.get("dimensions", []):
        column=str(dim.get("column") or "")
        if not column: continue
        for term in [dim.get("label"), *(dim.get("synonyms") or [])]:
            if term and _norm(str(term)) in q:
                augmented += f" {column}"
                break
    mentioned = _mentioned(augmented, df)
    numeric = [c for c in mentioned if _numeric(df, c)]
    non_numeric = [c for c in mentioned if not _numeric(df, c)]
    limit = max(1, min(int(limit), 5000))

    agg_map = [
        (("moyenne", "moyen", "average", "avg"), "AVG", "moyenne"),
        (("somme", "total", "sum"), "SUM", "somme"),
        (("minimum", "min ", "plus petit"), "MIN", "minimum"),
        (("maximum", "max ", "plus grand"), "MAX", "maximum"),
        (("mediane", "median"), "MEDIAN", "médiane"),
    ]
    agg = next(((sql, label) for words, sql, label in agg_map if any(w in q for w in words)), None)
    count_requested = any(w in q for w in ("combien", "nombre de", "count", "how many"))
    top_match = re.search(r"\btop\s+(\d+)\b", q)
    top_n = max(1, min(100, int(top_match.group(1)))) if top_match else None
    by_requested = bool(re.search(r"\b(par|selon|by|pour chaque)\b", q))

    assumptions: list[str] = []
    confidence = "high"

    if count_requested and not numeric:
        if non_numeric and by_requested:
            group = non_numeric[0]
            sql = f"SELECT {_q(group)}, COUNT(*) AS count_rows FROM dataset GROUP BY {_q(group)} ORDER BY count_rows DESC LIMIT {top_n or limit}"
            reasoning = f"Comptage des lignes regroupé par {group}."
        else:
            sql = "SELECT COUNT(*) AS count_rows FROM dataset"
            reasoning = "Comptage du nombre total de lignes."
        return {"sql": sql, "reasoning": reasoning, "assumptions": assumptions, "confidence": confidence, "mentioned_columns": mentioned}

    if agg and numeric:
        agg_sql, agg_label = agg
        metric = numeric[0]
        group_candidates = [c for c in mentioned if c != metric]
        group = group_candidates[0] if by_requested and group_candidates else (non_numeric[0] if by_requested and non_numeric else None)
        if agg_sql == "MEDIAN":
            # DuckDB supports median; SQLite fallback does not. Quantile support is not portable, so use AVG fallback in NLQ.
            agg_sql = "AVG"
            assumptions.append("La médiane demandée est approximée par AVG dans le traducteur portable NLQ; utilisez le moteur statistique pour une médiane exacte.")
            confidence = "medium"
        alias = f"{agg_label.replace('é','e').replace('è','e')}_{metric}"
        if group:
            sql = f"SELECT {_q(group)}, {agg_sql}({_q(metric)}) AS {_q(alias)} FROM dataset GROUP BY {_q(group)} ORDER BY {_q(alias)} DESC LIMIT {top_n or limit}"
            reasoning = f"Agrégation {agg_label} de {metric} par {group}."
        else:
            sql = f"SELECT {agg_sql}({_q(metric)}) AS {_q(alias)} FROM dataset"
            reasoning = f"Agrégation {agg_label} de {metric}."
        return {"sql": sql, "reasoning": reasoning, "assumptions": assumptions, "confidence": confidence, "mentioned_columns": mentioned}

    if top_n and len(mentioned) >= 2:
        metric = next((c for c in mentioned if _numeric(df, c)), None)
        group = next((c for c in mentioned if c != metric), None) if metric else None
        if metric and group:
            sql = f"SELECT {_q(group)}, SUM({_q(metric)}) AS total_metric FROM dataset GROUP BY {_q(group)} ORDER BY total_metric DESC LIMIT {top_n}"
            assumptions.append(f"'Top' est interprété comme la somme de {metric} par {group}.")
            return {"sql": sql, "reasoning": f"Classement des {top_n} premières valeurs de {group} selon la somme de {metric}.", "assumptions": assumptions, "confidence": "medium", "mentioned_columns": mentioned}

    if mentioned:
        cols = ", ".join(_q(c) for c in mentioned[:12])
        sql = f"SELECT {cols} FROM dataset LIMIT {limit}"
        assumptions.append("Aucune agrégation explicite n'a été détectée; la requête retourne les colonnes mentionnées.")
        return {"sql": sql, "reasoning": "Projection des colonnes explicitement citées.", "assumptions": assumptions, "confidence": "medium", "mentioned_columns": mentioned}

    return {
        "sql": f"SELECT * FROM dataset LIMIT {min(limit, 100)}",
        "reasoning": "Aucune colonne ou agrégation n'a été identifiée avec suffisamment de confiance.",
        "assumptions": ["La requête retourne un aperçu du dataset; reformulez la question pour une agrégation précise."],
        "confidence": "low",
        "mentioned_columns": [],
    }


def run_nlq(df: pd.DataFrame, question: str, limit: int = 200, semantic: dict[str, Any] | None = None) -> dict[str, Any]:
    translation = translate_nlq(df, question, limit, semantic)
    result = run_sql(df, translation["sql"], limit)
    return {"question": question, **translation, "result": result}
