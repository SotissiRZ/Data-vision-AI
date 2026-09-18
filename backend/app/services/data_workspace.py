from __future__ import annotations

import re
import sqlite3
import time
from typing import Any

import pandas as pd

try:  # Preferred analytical engine in packaged environments.
    import duckdb  # type: ignore
except ImportError:  # Development/test fallback only.
    duckdb = None

try:
    import polars as pl  # type: ignore
except ImportError:
    pl = None

FORBIDDEN_SQL = re.compile(r"\b(attach|detach|copy|install|load|pragma|create|drop|alter|insert|update|delete|merge|export|import|call|set|reset|vacuum)\b", re.I)


def engine_info(df: pd.DataFrame) -> dict:
    if pl is not None:
        pl_df = pl.from_pandas(df)
        size = int(pl_df.estimated_size())
    else:
        size = int(df.memory_usage(deep=True).sum())
    return {
        "preferred_engine": "duckdb" if duckdb is not None else "sqlite-fallback",
        "engines": {
            "pandas": pd.__version__,
            "polars": getattr(pl, "__version__", None),
            "duckdb": getattr(duckdb, "__version__", None),
        },
        "dataset": {"rows": int(len(df)), "columns": int(len(df.columns)), "estimated_size_bytes": size},
        "capabilities": ["SQL local read-only", "projection", "filtering", "aggregation", "CTE", "pagination"],
        "notes": [] if duckdb is not None and pl is not None else ["DuckDB/Polars sont déclarés comme dépendances de production; ce runtime utilise un fallback compatible pour les tests hors-ligne."],
    }


def _validate_query(sql: str) -> str:
    query = (sql or "").strip()
    if not query:
        raise ValueError("La requête SQL est vide")
    clean = query.rstrip(";").strip()
    if ";" in clean:
        raise ValueError("Une seule requête SQL est autorisée")
    if not re.match(r"^(select|with)\b", clean, re.I):
        raise ValueError("Le SQL Workspace est en lecture seule : utilisez SELECT ou WITH")
    if FORBIDDEN_SQL.search(clean):
        raise ValueError("Instruction SQL interdite dans le workspace en lecture seule")
    return clean


def run_sql(df: pd.DataFrame, sql: str, limit: int = 500) -> dict:
    query = _validate_query(sql)
    limit = max(1, min(int(limit), 5000))
    started = time.perf_counter()
    if duckdb is not None:
        con = duckdb.connect(database=":memory:")
        try:
            con.register("dataset", df)
            result = con.execute(f"SELECT * FROM ({query}) AS datavision_query LIMIT {limit + 1}").fetchdf()
        finally:
            con.close()
        engine = "duckdb"
    else:
        con = sqlite3.connect(":memory:")
        try:
            df.to_sql("dataset", con, index=False, if_exists="replace")
            result = pd.read_sql_query(f"SELECT * FROM ({query}) AS datavision_query LIMIT {limit + 1}", con)
        finally:
            con.close()
        engine = "sqlite-fallback"
    elapsed = (time.perf_counter() - started) * 1000
    truncated = len(result) > limit
    if truncated:
        result = result.iloc[:limit]
    safe = result.astype(object).where(pd.notna(result), None)
    return {
        "columns": [str(c) for c in safe.columns],
        "rows": safe.to_dict(orient="records"),
        "returned_rows": int(len(safe)),
        "truncated": truncated,
        "limit": limit,
        "elapsed_ms": round(elapsed, 3),
        "engine": engine,
        "query": query,
    }
