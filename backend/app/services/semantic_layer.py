from __future__ import annotations

import ast
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.storage import get_meta, list_dataset_catalog

_ALLOWED_AGGS = {"sum", "mean", "median", "min", "max", "count", "nunique"}
_ALLOWED_CARDINALITIES = {"many_to_one", "one_to_one"}
_ALLOWED_JOINS = {"left", "inner"}
_ALLOWED_TIME_GRAINS = {"day", "week", "month", "quarter", "year"}
_ALLOWED_COMPARISONS = {"none", "previous_period", "yoy"}
_ALLOWED_TIME_CALCS = {"none", "running_total", "ytd", "rolling_mean", "rolling_sum"}


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
    return text or f"item_{uuid.uuid4().hex[:8]}"


def _is_identifier(name: str, series: pd.Series) -> bool:
    n = name.lower()
    by_name = n in {"id", "index", "row", "record", "patient_id", "customer_id", "user_id"} or n.endswith("_id")
    id_token = any(t in n for t in ("uuid", "identifier", "identifiant", "record_no", "record_number", "primary_key"))
    high_unique = len(series) > 20 and series.nunique(dropna=True) / max(len(series), 1) > .98
    return by_name or (id_token and high_unique)


def _dimension_kind(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    return "categorical"


def _suggest(dataset_id: str, df: pd.DataFrame) -> dict[str, Any]:
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
                "id": _slug(name), "name": name, "label": name.replace("_", " "), "type": "base",
                "table": "base", "column": name, "aggregation": agg, "unit": "", "format": "number",
                "description": "", "synonyms": [], "certified": False, "source": "suggested",
            })
        dimensions.append({
            "id": _slug(name), "table": "base", "column": name, "label": name.replace("_", " "),
            "description": "", "synonyms": [], "hidden": False, "certified": False,
            "kind": _dimension_kind(s), "source": "suggested",
        })
    return {
        "tables": [{
            "id": "base", "dataset_id": dataset_id, "label": get_meta(dataset_id).get("original_name", "Dataset principal"),
            "role": "fact", "active": True,
        }],
        "relationships": [],
        "metrics": metrics[:32],
        "dimensions": dimensions[:48],
        "hierarchies": [],
    }


def _normalize_model(dataset_id: str, df: pd.DataFrame, payload: dict[str, Any]) -> dict[str, Any]:
    suggested = _suggest(dataset_id, df)
    tables = payload.get("tables") or suggested["tables"]
    normalized_tables: list[dict[str, Any]] = []
    seen_tables: set[str] = set()
    has_base = False
    for raw in tables:
        table_id = _slug(str(raw.get("id") or raw.get("alias") or raw.get("label") or "table"))
        ds_id = str(raw.get("dataset_id") or dataset_id)
        if ds_id == dataset_id or table_id == "base":
            table_id = "base"
            ds_id = dataset_id
            has_base = True
        if table_id in seen_tables:
            continue
        seen_tables.add(table_id)
        normalized_tables.append({
            "id": table_id,
            "dataset_id": ds_id,
            "label": str(raw.get("label") or table_id)[:160],
            "role": str(raw.get("role") or ("fact" if table_id == "base" else "dimension")),
            "active": bool(raw.get("active", True)),
        })
    if not has_base:
        normalized_tables.insert(0, suggested["tables"][0])
        seen_tables.add("base")

    normalized_metrics: list[dict[str, Any]] = []
    seen_metrics: set[str] = set()
    for raw in payload.get("metrics", suggested["metrics"]):
        metric_type = str(raw.get("type") or ("calculated" if raw.get("formula") else "base")).lower()
        table_id = _slug(str(raw.get("table") or "base"))
        column = str(raw.get("column") or "")
        metric_id = _slug(str(raw.get("id") or raw.get("name") or raw.get("label") or column or "metric"))
        if metric_id in seen_metrics:
            continue
        seen_metrics.add(metric_id)
        agg = str(raw.get("aggregation") or "mean").lower()
        normalized_metrics.append({
            "id": metric_id,
            "name": str(raw.get("name") or raw.get("label") or column or metric_id)[:160],
            "label": str(raw.get("label") or raw.get("name") or column or metric_id)[:160],
            "type": metric_type,
            "table": table_id,
            "column": column,
            "aggregation": agg,
            "formula": str(raw.get("formula") or "")[:500],
            "unit": str(raw.get("unit") or "")[:32],
            "format": str(raw.get("format") or "number")[:32],
            "description": str(raw.get("description") or "")[:800],
            "synonyms": [str(x)[:80] for x in raw.get("synonyms", []) if str(x).strip()][:30],
            "certified": bool(raw.get("certified", False)),
            "source": str(raw.get("source") or "user"),
        })

    normalized_dimensions: list[dict[str, Any]] = []
    seen_dims: set[str] = set()
    for raw in payload.get("dimensions", suggested["dimensions"]):
        table_id = _slug(str(raw.get("table") or "base"))
        column = str(raw.get("column") or "")
        dim_id = _slug(str(raw.get("id") or raw.get("label") or column or "dimension"))
        if dim_id in seen_dims:
            suffix = 2
            while f"{dim_id}_{suffix}" in seen_dims:
                suffix += 1
            dim_id = f"{dim_id}_{suffix}"
        seen_dims.add(dim_id)
        normalized_dimensions.append({
            "id": dim_id,
            "table": table_id,
            "column": column,
            "label": str(raw.get("label") or column or dim_id)[:160],
            "description": str(raw.get("description") or "")[:800],
            "synonyms": [str(x)[:80] for x in raw.get("synonyms", []) if str(x).strip()][:30],
            "hidden": bool(raw.get("hidden", False)),
            "certified": bool(raw.get("certified", False)),
            "kind": str(raw.get("kind") or "categorical"),
            "date_role": str(raw.get("date_role") or "")[:40],
            "source": str(raw.get("source") or "user"),
        })

    relationships: list[dict[str, Any]] = []
    seen_rels: set[str] = set()
    for raw in payload.get("relationships", []):
        rid = _slug(str(raw.get("id") or f"{raw.get('from_table','')}_{raw.get('to_table','')}_{raw.get('from_column','')}"))
        if rid in seen_rels:
            continue
        seen_rels.add(rid)
        relationships.append({
            "id": rid,
            "from_table": _slug(str(raw.get("from_table") or "base")),
            "from_column": str(raw.get("from_column") or ""),
            "to_table": _slug(str(raw.get("to_table") or "")),
            "to_column": str(raw.get("to_column") or ""),
            "cardinality": str(raw.get("cardinality") or "many_to_one"),
            "join_type": str(raw.get("join_type") or "left"),
            "active": bool(raw.get("active", True)),
            "description": str(raw.get("description") or "")[:500],
        })

    hierarchies: list[dict[str, Any]] = []
    for raw in payload.get("hierarchies", []):
        levels = [str(x) for x in raw.get("levels", []) if str(x).strip()]
        hierarchies.append({
            "id": _slug(str(raw.get("id") or raw.get("name") or "hierarchy")),
            "name": str(raw.get("name") or "Hiérarchie")[:160],
            "levels": levels[:12],
            "certified": bool(raw.get("certified", False)),
            "description": str(raw.get("description") or "")[:500],
        })

    glossary = []
    for raw in payload.get("business_glossary", []):
        term = str(raw.get("term") or "").strip()
        if term:
            glossary.append({"term": term[:120], "definition": str(raw.get("definition") or "")[:1200]})

    return {
        "dataset_id": dataset_id,
        "root_id": _root_id(dataset_id),
        "semantic_version": 2,
        "version": int(payload.get("version") or 1),
        "status": str(payload.get("status") or "draft"),
        "tables": normalized_tables,
        "relationships": relationships,
        "metrics": normalized_metrics,
        "dimensions": normalized_dimensions,
        "hierarchies": hierarchies,
        "business_glossary": glossary,
        "updated_at": payload.get("updated_at"),
        "source": str(payload.get("source") or "auto_suggested"),
    }


def get_semantic_model(dataset_id: str, df: pd.DataFrame) -> dict[str, Any]:
    path = _path(dataset_id)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["dataset_id"] = dataset_id
        payload["root_id"] = _root_id(dataset_id)
        return _normalize_model(dataset_id, df, payload)
    suggested = _suggest(dataset_id, df)
    return _normalize_model(dataset_id, df, {
        "version": 1,
        "status": "draft",
        **suggested,
        "business_glossary": [],
        "updated_at": None,
        "source": "auto_suggested",
    })


def _load_table_frames(dataset_id: str, df: pd.DataFrame, model: dict[str, Any]) -> dict[str, pd.DataFrame]:
    from app.services.storage import load_dataframe

    frames: dict[str, pd.DataFrame] = {}
    for table in model.get("tables", []):
        if not table.get("active", True):
            continue
        alias = str(table["id"])
        ds_id = str(table.get("dataset_id") or dataset_id)
        frames[alias] = df.copy() if alias == "base" or ds_id == dataset_id else load_dataframe(ds_id)
    if "base" not in frames:
        frames["base"] = df.copy()
    return frames


def semantic_table_catalog(dataset_id: str) -> dict[str, Any]:
    from app.services.storage import load_dataframe

    rows = list_dataset_catalog()
    current_root = _root_id(dataset_id)
    latest_by_root: dict[str, dict[str, Any]] = {}
    for row in rows:
        root = str(row.get("root_id") or row.get("id"))
        previous = latest_by_root.get(root)
        if previous is None or int(row.get("version", 1)) > int(previous.get("version", 1)):
            latest_by_root[root] = row
    tables: list[dict[str, Any]] = []
    for root, row in list(latest_by_root.items())[:50]:
        ds_id = str(row.get("id"))
        try:
            frame = load_dataframe(ds_id)
            columns = [{"name": str(c), "dtype": str(frame[c].dtype), "unique": int(frame[c].nunique(dropna=True))} for c in frame.columns[:120]]
        except (PermissionError, FileNotFoundError):
            continue
        tables.append({
            "dataset_id": ds_id,
            "root_id": root,
            "name": row.get("source_name") or row.get("name"),
            "version": int(row.get("version", 1)),
            "current": root == current_root,
            "rows": int(len(frame)),
            "columns": columns,
        })
    return {"tables": tables, "count": len(tables)}


def _formula_names(formula: str) -> set[str]:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Formule invalide: {exc.msg}") from exc
    allowed_nodes = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd, ast.Load)
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError("La formule accepte uniquement métriques, nombres, parenthèses et opérateurs + - * / ** %.")
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def _formula_value(formula: str, values: dict[str, Any]) -> float | None:
    tree = ast.parse(formula, mode="eval")

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in values or values[node.id] is None:
                raise ValueError(f"Métrique absente dans la formule: {node.id}")
            return float(values[node.id])
        if isinstance(node, ast.UnaryOp):
            value = ev(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right if abs(right) > 1e-15 else math.nan
            if isinstance(node.op, ast.Pow): return left ** right
            if isinstance(node.op, ast.Mod): return left % right if abs(right) > 1e-15 else math.nan
        raise ValueError("Expression calculée non supportée")

    value = ev(tree)
    return None if not math.isfinite(value) else float(value)


def validate_semantic_model(dataset_id: str, df: pd.DataFrame, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _normalize_model(dataset_id, df, payload or get_semantic_model(dataset_id, df))
    errors: list[str] = []
    warnings: list[str] = []
    frames: dict[str, pd.DataFrame] = {}
    try:
        frames = _load_table_frames(dataset_id, df, model)
    except PermissionError as exc:
        errors.append(str(exc))
    except FileNotFoundError as exc:
        errors.append(f"Dataset lié introuvable: {exc}")

    table_ids = {t["id"] for t in model.get("tables", []) if t.get("active", True)}
    if "base" not in table_ids:
        errors.append("La table principale 'base' est obligatoire.")

    for relation in model.get("relationships", []):
        if not relation.get("active", True):
            continue
        ft, tt = relation.get("from_table"), relation.get("to_table")
        fc, tc = relation.get("from_column"), relation.get("to_column")
        if ft not in table_ids or tt not in table_ids:
            errors.append(f"Relation {relation.get('id')}: table inconnue.")
            continue
        if relation.get("cardinality") not in _ALLOWED_CARDINALITIES:
            errors.append(f"Relation {relation.get('id')}: cardinalité {relation.get('cardinality')} non sûre pour l'agrégation automatique.")
        if relation.get("join_type") not in _ALLOWED_JOINS:
            errors.append(f"Relation {relation.get('id')}: jointure non supportée.")
        if ft in frames and fc not in frames[ft].columns:
            errors.append(f"Relation {relation.get('id')}: colonne {ft}.{fc} inconnue.")
        if tt in frames and tc not in frames[tt].columns:
            errors.append(f"Relation {relation.get('id')}: colonne {tt}.{tc} inconnue.")
        if tt in frames and tc in frames[tt].columns:
            duplicated = int(frames[tt][tc].dropna().duplicated().sum())
            if relation.get("cardinality") == "many_to_one" and duplicated:
                errors.append(f"Relation {relation.get('id')}: {tt}.{tc} n'est pas unique ({duplicated} doublon(s)); risque de fan-out.")
            if relation.get("cardinality") == "one_to_one" and duplicated:
                errors.append(f"Relation {relation.get('id')}: clé droite non unique pour une relation 1:1.")
        if relation.get("cardinality") == "one_to_one" and ft in frames and fc in frames[ft].columns and frames[ft][fc].dropna().duplicated().any():
            errors.append(f"Relation {relation.get('id')}: clé gauche non unique pour une relation 1:1.")

    metric_ids = {m["id"] for m in model.get("metrics", [])}
    deps: dict[str, set[str]] = {}
    for metric in model.get("metrics", []):
        mid = metric["id"]
        if metric.get("type") == "calculated":
            formula = str(metric.get("formula") or "")
            if not formula:
                errors.append(f"Métrique calculée {mid}: formule manquante.")
                continue
            try:
                names = _formula_names(formula)
                deps[mid] = names
                unknown = names - metric_ids
                if unknown:
                    errors.append(f"Métrique {mid}: références inconnues {', '.join(sorted(unknown))}.")
                if mid in names:
                    errors.append(f"Métrique {mid}: auto-référence interdite.")
            except ValueError as exc:
                errors.append(f"Métrique {mid}: {exc}")
        else:
            table = metric.get("table", "base")
            column = metric.get("column")
            if table not in table_ids:
                errors.append(f"Métrique {mid}: table inconnue {table}.")
            elif table in frames and column not in frames[table].columns:
                errors.append(f"Métrique {mid}: colonne inconnue {table}.{column}.")
            if metric.get("aggregation") not in _ALLOWED_AGGS:
                errors.append(f"Métrique {mid}: agrégation non supportée {metric.get('aggregation')}.")

    # Cycle detection for calculated metrics.
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visited: return
        if node in visiting:
            errors.append(f"Cycle détecté dans les métriques calculées autour de {node}.")
            return
        visiting.add(node)
        for dep in deps.get(node, set()):
            if dep in deps: visit(dep)
        visiting.remove(node); visited.add(node)
    for mid in deps: visit(mid)

    dim_ids = {d["id"] for d in model.get("dimensions", [])}
    for dim in model.get("dimensions", []):
        table, column = dim.get("table", "base"), dim.get("column")
        if table not in table_ids:
            errors.append(f"Dimension {dim['id']}: table inconnue {table}.")
        elif table in frames and column not in frames[table].columns:
            errors.append(f"Dimension {dim['id']}: colonne inconnue {table}.{column}.")
        if dim.get("kind") == "date" and table in frames and column in frames[table].columns:
            converted = pd.to_datetime(frames[table][column], errors="coerce")
            if len(converted) and converted.notna().mean() < .7:
                warnings.append(f"Dimension date {dim['id']}: moins de 70 % des valeurs sont convertibles en date.")

    for hierarchy in model.get("hierarchies", []):
        levels = hierarchy.get("levels", [])
        if len(levels) < 2:
            warnings.append(f"Hiérarchie {hierarchy.get('name')}: ajoutez au moins deux niveaux.")
        unknown = [x for x in levels if x not in dim_ids]
        if unknown:
            errors.append(f"Hiérarchie {hierarchy.get('name')}: dimensions inconnues {', '.join(unknown)}.")

    # Connectivity: all active related tables should be reachable from base in the directed safe graph.
    reachable = {"base"}
    changed = True
    while changed:
        changed = False
        for rel in model.get("relationships", []):
            if rel.get("active", True) and rel.get("from_table") in reachable and rel.get("to_table") not in reachable:
                reachable.add(rel["to_table"]); changed = True
    disconnected = sorted(table_ids - reachable)
    if disconnected:
        warnings.append(f"Tables non reliées à la table de faits: {', '.join(disconnected)}.")

    certified_metrics = sum(1 for m in model.get("metrics", []) if m.get("certified"))
    described_metrics = sum(1 for m in model.get("metrics", []) if m.get("description"))
    relation_score = 100 if len(table_ids) == 1 else max(0, 100 - 25 * len(disconnected) - 20 * sum(1 for e in errors if "Relation" in e))
    semantic_score = int(max(0, min(100,
        35 + 25 * certified_metrics / max(1, len(model.get("metrics", [])))
        + 20 * described_metrics / max(1, len(model.get("metrics", [])))
        + 20 * relation_score / 100
        - min(50, 12 * len(errors))
    )))
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "score": semantic_score,
        "tables": len(table_ids),
        "relationships": len([r for r in model.get("relationships", []) if r.get("active", True)]),
        "metrics": len(model.get("metrics", [])),
        "calculated_metrics": len([m for m in model.get("metrics", []) if m.get("type") == "calculated"]),
        "certified_metrics": certified_metrics,
        "dimensions": len(model.get("dimensions", [])),
        "hierarchies": len(model.get("hierarchies", [])),
        "reachable_tables": sorted(reachable),
        "model": model,
    }


def save_semantic_model(dataset_id: str, df: pd.DataFrame, payload: dict[str, Any]) -> dict[str, Any]:
    previous = get_semantic_model(dataset_id, df)
    candidate = _normalize_model(dataset_id, df, {
        **payload,
        "version": int(previous.get("version") or 0) + 1,
        "status": "governed",
        "updated_at": _now(),
        "source": "saved",
    })
    validation = validate_semantic_model(dataset_id, df, candidate)
    if validation["errors"]:
        raise ValueError(" | ".join(validation["errors"][:8]))
    out = validation["model"]
    out.update({
        "version": int(previous.get("version") or 0) + 1,
        "status": "governed",
        "updated_at": _now(),
        "source": "saved",
        "validation": {k: v for k, v in validation.items() if k != "model"},
    })
    _path(dataset_id).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _prefix_frame(alias: str, frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={c: f"{alias}__{c}" for c in frame.columns})


def _required_join_closure(model: dict[str, Any], required_tables: set[str]) -> set[str]:
    """Add safe intermediate tables needed to reach every requested table from base.

    v2.3 could join direct dimensions. v2.4 supports snowflake-style chains such as
    fact -> product -> category while preserving the directed N:1 / 1:1 safety contract.
    """
    active = [r for r in model.get("relationships", []) if r.get("active", True) and r.get("cardinality") in _ALLOWED_CARDINALITIES]
    parent: dict[str, tuple[str, dict[str, Any]]] = {}
    queue = ["base"]
    seen = {"base"}
    while queue:
        current = queue.pop(0)
        for rel in active:
            if rel.get("from_table") != current:
                continue
            nxt = str(rel.get("to_table"))
            if nxt in seen:
                continue
            seen.add(nxt)
            parent[nxt] = (current, rel)
            queue.append(nxt)
    closure = {"base"}
    for target in set(required_tables) | {"base"}:
        if target == "base":
            continue
        if target not in seen:
            raise ValueError(f"Impossible de relier la table {target} depuis la table de faits.")
        node = target
        closure.add(node)
        while node != "base":
            node = parent[node][0]
            closure.add(node)
    return closure


def _joined_frame(dataset_id: str, df: pd.DataFrame, model: dict[str, Any], required_tables: set[str]) -> pd.DataFrame:
    frames = _load_table_frames(dataset_id, df, model)
    work = _prefix_frame("base", frames["base"])
    joined = {"base"}
    target = _required_join_closure(model, required_tables)
    active = [r for r in model.get("relationships", []) if r.get("active", True)]
    while target - joined:
        progressed = False
        for rel in active:
            ft, tt = rel["from_table"], rel["to_table"]
            if ft not in joined or tt in joined or tt not in target:
                continue
            if rel.get("cardinality") not in _ALLOWED_CARDINALITIES:
                continue
            if tt not in frames:
                continue
            right = _prefix_frame(tt, frames[tt])
            left_key, right_key = f"{ft}__{rel['from_column']}", f"{tt}__{rel['to_column']}"
            if left_key not in work.columns or right_key not in right.columns:
                raise ValueError(f"Relation {rel['id']} non exécutable: clé absente.")
            if rel.get("cardinality") == "many_to_one" and right[right_key].dropna().duplicated().any():
                raise ValueError(f"Relation {rel['id']} bloquée: clé droite non unique, risque de fan-out.")
            if rel.get("cardinality") == "one_to_one" and right[right_key].dropna().duplicated().any():
                raise ValueError(f"Relation {rel['id']} bloquée: clé droite non unique pour une relation 1:1.")
            work = work.merge(right, how=rel.get("join_type", "left"), left_on=left_key, right_on=right_key, suffixes=("", ""))
            joined.add(tt); progressed = True
        if not progressed:
            missing = ", ".join(sorted(target - joined))
            raise ValueError(f"Impossible de relier les tables requises depuis la table de faits: {missing}.")
    return work


def _resolve_dimension(model: dict[str, Any], value: str) -> dict[str, Any] | None:
    return next((d for d in model.get("dimensions", []) if d.get("id") == value or (d.get("table", "base") == "base" and d.get("column") == value)), None)


def _metric_by_id(model: dict[str, Any], metric_id: str) -> dict[str, Any] | None:
    return next((m for m in model.get("metrics", []) if m.get("id") == metric_id), None)


def _metric_dependencies(model: dict[str, Any], metric_id: str, seen: set[str] | None = None) -> set[str]:
    seen = seen or set()
    if metric_id in seen:
        return set()
    seen.add(metric_id)
    metric = _metric_by_id(model, metric_id)
    if not metric:
        return set()
    if metric.get("type") != "calculated":
        return {metric_id}
    deps: set[str] = set()
    for name in _formula_names(str(metric.get("formula") or "")):
        deps |= _metric_dependencies(model, name, seen)
    return deps


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


def _metric_on_group(group: pd.DataFrame, model: dict[str, Any], metric_id: str, cache: dict[str, Any] | None = None) -> Any:
    cache = cache if cache is not None else {}
    if metric_id in cache:
        return cache[metric_id]
    metric = _metric_by_id(model, metric_id)
    if not metric:
        raise ValueError(f"Métrique inconnue: {metric_id}")
    if metric.get("type") == "calculated":
        values = {dep: _metric_on_group(group, model, dep, cache) for dep in _formula_names(metric.get("formula", ""))}
        value = _formula_value(metric.get("formula", ""), values)
    else:
        col = f"{metric.get('table','base')}__{metric.get('column')}"
        if col not in group.columns:
            raise ValueError(f"Colonne métrique absente après relation: {col}")
        value = _metric_value(group[col], metric.get("aggregation", "mean"))
    cache[metric_id] = value
    return value


def _apply_semantic_filters(work: pd.DataFrame, model: dict[str, Any], filters: list[dict[str, Any]]) -> pd.DataFrame:
    out = work
    for f in filters or []:
        ref = str(f.get("dimension") or f.get("column") or "")
        dim = _resolve_dimension(model, ref)
        column = f"{dim.get('table','base')}__{dim.get('column')}" if dim else ref.replace(".", "__")
        if column not in out.columns:
            raise ValueError(f"Filtre sur dimension/colonne inconnue: {ref}")
        op, value = str(f.get("operator") or "eq"), f.get("value")
        s = out[column]
        if op == "eq": out = out[s.astype(str) == str(value)]
        elif op == "ne": out = out[s.astype(str) != str(value)]
        elif op == "contains": out = out[s.astype(str).str.contains(str(value), case=False, na=False)]
        elif op in {"gt", "gte", "lt", "lte"}:
            numeric = pd.to_numeric(s, errors="coerce"); val = float(value)
            mask = {"gt": numeric > val, "gte": numeric >= val, "lt": numeric < val, "lte": numeric <= val}[op]
            out = out[mask]
        elif op == "between":
            numeric = pd.to_numeric(s, errors="coerce")
            low, high = (value if isinstance(value, list) else [f.get("min"), f.get("max")])[:2]
            out = out[(numeric >= float(low)) & (numeric <= float(high))]
        elif op == "is_null": out = out[s.isna()]
        elif op == "not_null": out = out[s.notna()]
        else: raise ValueError(f"Opérateur de filtre non supporté: {op}")
    return out


def semantic_filtered_base(dataset_id: str, df: pd.DataFrame, filters: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    """Return base-table rows after semantic filters, including filters on linked dimensions.

    Safe relationships never fan out the fact table, so projecting base__ columns after the join
    preserves fact-row semantics. This powers dashboard cross-filtering across multiple tables.
    """
    if not filters:
        return df.copy()
    model = get_semantic_model(dataset_id, df)
    required_tables: set[str] = {"base"}
    normalized: list[dict[str, Any]] = []
    for raw in filters or []:
        ref = str(raw.get("dimension") or raw.get("column") or "")
        dim = _resolve_dimension(model, ref)
        op = "ne" if str(raw.get("operator") or "eq") == "neq" else str(raw.get("operator") or "eq")
        value = raw.get("value")
        if op == "between" and not isinstance(value, list):
            value = [raw.get("value"), raw.get("value2")]
        patch = {**raw, "operator": op, "value": value}
        if dim:
            required_tables.add(str(dim.get("table", "base")))
            normalized.append({**patch, "dimension": dim["id"]})
        else:
            # A raw base-table dashboard filter remains valid when a semantic dimension has not
            # been explicitly defined for the physical column.
            normalized.append({**patch, "column": f"base__{ref}" if ref and "__" not in ref else ref})
    joined = _joined_frame(dataset_id, df, model, required_tables)
    filtered = _apply_semantic_filters(joined, model, normalized)
    base_cols = [c for c in filtered.columns if c.startswith("base__")]
    out = filtered[base_cols].copy()
    out.columns = [c[len("base__"):] for c in base_cols]
    return out.reset_index(drop=True)


def _periodize(series: pd.Series, grain: str) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce")
    if grain == "day": return dates.dt.floor("D")
    if grain == "week": return dates.dt.to_period("W").dt.start_time
    if grain == "month": return dates.dt.to_period("M").dt.start_time
    if grain == "quarter": return dates.dt.to_period("Q").dt.start_time
    if grain == "year": return dates.dt.to_period("Y").dt.start_time
    raise ValueError(f"Granularité temporelle non supportée: {grain}")


def query_semantic_metric(
    dataset_id: str,
    df: pd.DataFrame,
    metric_id: str,
    dimensions: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    limit: int = 500,
    date_dimension: str | None = None,
    time_grain: str | None = None,
    comparison: str = "none",
    time_calculation: str = "none",
    rolling_window: int = 3,
    aggregation_override: str | None = None,
) -> dict[str, Any]:
    model = get_semantic_model(dataset_id, df)
    metric = _metric_by_id(model, metric_id)
    if not metric:
        raise ValueError(f"Métrique inconnue: {metric_id}")
    if aggregation_override:
        override = str(aggregation_override).lower()
        if metric.get("type") == "calculated":
            raise ValueError("Une agrégation explicite ne peut pas remplacer directement une métrique calculée.")
        if override not in _ALLOWED_AGGS:
            raise ValueError(f"Agrégation explicite non supportée: {override}")
        # Copy the semantic model so the saved governed definition is never mutated.
        model = {**model, "metrics": [{**m, "aggregation": override} if m.get("id") == metric_id else dict(m) for m in model.get("metrics", [])]}
        metric = _metric_by_id(model, metric_id)
    comparison = comparison if comparison in _ALLOWED_COMPARISONS else "none"
    time_calculation = time_calculation if time_calculation in _ALLOWED_TIME_CALCS else "none"
    if time_grain and time_grain not in _ALLOWED_TIME_GRAINS:
        raise ValueError(f"Granularité temporelle invalide: {time_grain}")

    selected_dims: list[dict[str, Any]] = []
    for ref in dimensions or []:
        dim = _resolve_dimension(model, ref)
        if not dim:
            raise ValueError(f"Dimension inconnue: {ref}")
        if dim.get("hidden"):
            raise ValueError(f"Dimension masquée: {ref}")
        selected_dims.append(dim)

    date_dim = _resolve_dimension(model, date_dimension) if date_dimension else None
    if date_dimension and not date_dim:
        raise ValueError(f"Dimension temporelle inconnue: {date_dimension}")

    base_metric_ids = _metric_dependencies(model, metric_id)
    required_tables = {(_metric_by_id(model, mid) or {}).get("table", "base") for mid in base_metric_ids}
    required_tables |= {d.get("table", "base") for d in selected_dims}
    if date_dim: required_tables.add(date_dim.get("table", "base"))
    for f in filters or []:
        dim = _resolve_dimension(model, str(f.get("dimension") or f.get("column") or ""))
        if dim: required_tables.add(dim.get("table", "base"))
    work = _joined_frame(dataset_id, df, model, {str(x) for x in required_tables if x})
    work = _apply_semantic_filters(work, model, filters or [])

    group_columns: list[tuple[str, str]] = []
    for dim in selected_dims:
        physical = f"{dim.get('table','base')}__{dim.get('column')}"
        group_columns.append((dim["id"], physical))

    time_output_id = None
    if date_dim and time_grain:
        physical = f"{date_dim.get('table','base')}__{date_dim.get('column')}"
        work = work.copy()
        work["__time_bucket__"] = _periodize(work[physical], time_grain)
        work = work.dropna(subset=["__time_bucket__"])
        time_output_id = date_dim["id"]
        group_columns.append((time_output_id, "__time_bucket__"))

    global_value = _metric_on_group(work, model, metric_id, {}) if len(work) else None
    rows: list[dict[str, Any]] = []
    if group_columns:
        physical_cols = [p for _, p in group_columns]
        grouper = physical_cols[0] if len(physical_cols) == 1 else physical_cols
        for keys, group in work.groupby(grouper, dropna=False, sort=False):
            keys_tuple = keys if isinstance(keys, tuple) else (keys,)
            row: dict[str, Any] = {}
            for (dim_id, _), value in zip(group_columns, keys_tuple):
                if isinstance(value, pd.Timestamp): value = value.isoformat()
                elif pd.isna(value): value = None
                elif isinstance(value, np.generic): value = value.item()
                row[dim_id] = value
            row["value"] = _metric_on_group(group, model, metric_id, {})
            row["rows"] = int(len(group))
            rows.append(row)
        if time_output_id:
            other_dims = [d["id"] for d in selected_dims]
            rows.sort(key=lambda r: tuple(str(r.get(d) or "") for d in other_dims) + (str(r.get(time_output_id) or ""),))
        else:
            rows.sort(key=lambda r: (r.get("value") is None, -(float(r.get("value") or 0))))
        rows = rows[:max(1, min(int(limit), 5000))]

    # Time intelligence is applied after deterministic period aggregation.
    if time_output_id and rows:
        other_dims = [d["id"] for d in selected_dims]
        buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in rows:
            key = tuple(row.get(d) for d in other_dims)
            buckets.setdefault(key, []).append(row)
        for group_rows in buckets.values():
            group_rows.sort(key=lambda r: str(r.get(time_output_id) or ""))
            period_map: dict[pd.Timestamp, dict[str, Any]] = {}
            for item in group_rows:
                try:
                    period_map[pd.Timestamp(item.get(time_output_id))] = item
                except Exception:
                    pass
            for i, row in enumerate(group_rows):
                previous = None
                if comparison == "previous_period" and i >= 1:
                    previous = group_rows[i-1].get("value")
                elif comparison == "yoy":
                    try:
                        current_period = pd.Timestamp(row.get(time_output_id))
                        previous_row = period_map.get(current_period - pd.DateOffset(years=1))
                        previous = previous_row.get("value") if previous_row else None
                    except Exception:
                        previous = None
                if comparison != "none" and previous is not None:
                    current = row.get("value")
                    row["comparison_value"] = previous
                    if current is not None:
                        row["delta"] = float(current) - float(previous)
                        row["delta_pct"] = ((float(current)-float(previous))/abs(float(previous))*100) if abs(float(previous)) > 1e-12 else None
                if time_calculation != "none":
                    values = [r.get("value") for r in group_rows[:i+1]]
                    clean = [float(v) for v in values if v is not None]
                    if time_calculation == "running_total": row["time_value"] = sum(clean)
                    elif time_calculation == "ytd":
                        year = str(row.get(time_output_id) or "")[:4]
                        yvals = [float(r["value"]) for r in group_rows[:i+1] if r.get("value") is not None and str(r.get(time_output_id) or "")[:4] == year]
                        row["time_value"] = sum(yvals)
                    elif time_calculation in {"rolling_mean", "rolling_sum"}:
                        window_rows = group_rows[max(0, i-max(1, rolling_window)+1):i+1]
                        wvals = [float(r["value"]) for r in window_rows if r.get("value") is not None]
                        row["time_value"] = (sum(wvals)/len(wvals) if time_calculation == "rolling_mean" and wvals else sum(wvals) if wvals else None)

    return {
        "metric": metric,
        "value": global_value,
        "rows": int(len(work)),
        "dimensions": [d["id"] for d in selected_dims] + ([time_output_id] if time_output_id else []),
        "result": rows,
        "filters": filters or [],
        "date_dimension": time_output_id,
        "time_grain": time_grain,
        "comparison": comparison,
        "time_calculation": time_calculation,
        "rolling_window": rolling_window,
        "aggregation_override": aggregation_override,
        "semantic_model_version": model.get("version"),
        "semantic_version": 2,
        "calculation_policy": "deterministic_semantic_engine",
    }


def evaluate_metric(dataset_id: str, df: pd.DataFrame, metric_id: str, dimensions: list[str] | None = None, filters: list[dict[str, Any]] | None = None, limit: int = 200) -> dict[str, Any]:
    """Backward-compatible v2.0 endpoint, now powered by the Semantic Query Engine v2."""
    return query_semantic_metric(dataset_id, df, metric_id, dimensions, filters, limit)


def metric_pulse(dataset_id: str, df: pd.DataFrame, metric_id: str, date_column: str | None = None, periods: int = 12) -> dict[str, Any]:
    model = get_semantic_model(dataset_id, df)
    metric = _metric_by_id(model, metric_id)
    if not metric:
        raise ValueError(f"Métrique inconnue: {metric_id}")
    current = query_semantic_metric(dataset_id, df, metric_id).get("value")
    result: dict[str, Any] = {"metric": metric, "current": current, "trend": [], "delta_pct": None, "status": "stable", "calculation_policy": "deterministic_semantic_engine"}
    if not date_column:
        return result
    dim = _resolve_dimension(model, date_column)
    if not dim:
        # Backward compatibility: create a transient date dimension for a base-table column.
        if date_column in df.columns:
            dim = {"id": _slug(date_column), "table": "base", "column": date_column, "hidden": False}
            model = {**model, "dimensions": [*model.get("dimensions", []), dim]}
        else:
            return result
    # query_semantic_metric reads the saved model, so raw-column fallback uses the previous local implementation.
    if not _resolve_dimension(get_semantic_model(dataset_id, df), dim["id"]):
        dates = pd.to_datetime(df[date_column], errors="coerce")
        work = df.assign(__date__=dates).dropna(subset=["__date__"]).copy()
        if work.empty or metric.get("type") == "calculated" or metric.get("table") != "base": return result
        work["__period__"] = work["__date__"].dt.to_period("M").dt.to_timestamp()
        grouped = [{"period": p.isoformat(), "value": _metric_value(g[metric["column"]], metric["aggregation"])} for p, g in work.groupby("__period__")]
    else:
        query = query_semantic_metric(dataset_id, df, metric_id, [], [], 500, dim["id"], "month", "previous_period")
        grouped = [{"period": r[dim["id"]], "value": r["value"]} for r in query["result"]]
    grouped = [x for x in grouped if x.get("value") is not None][-max(2, min(periods, 36)):]
    result["trend"] = grouped
    if len(grouped) >= 2:
        prev, last = float(grouped[-2]["value"]), float(grouped[-1]["value"])
        if abs(prev) > 1e-12:
            delta = (last-prev)/abs(prev)*100
            result["delta_pct"] = delta; result["status"] = "up" if delta > 1 else "down" if delta < -1 else "stable"
        history = np.array([float(x["value"]) for x in grouped[:-1]], dtype=float)
        if len(history) >= 4 and float(np.std(history)) > 0:
            z = (last-float(np.mean(history)))/float(np.std(history))
            result["anomaly_z"] = z; result["anomaly"] = abs(z) >= 2.5
    return result
