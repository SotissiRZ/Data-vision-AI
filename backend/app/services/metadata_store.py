from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

_ENGINES: dict[str, Engine] = {}
_SELECTED_BACKENDS: dict[str, str] = {}

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_members (
        organization_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (organization_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (organization_id, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_members (
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_datasets (
        workspace_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        bound_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, dataset_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS access_policies (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        name TEXT NOT NULL,
        allowed_columns_json TEXT NOT NULL,
        row_filters_json TEXT NOT NULL,
        applies_to_role TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        organization_id TEXT,
        workspace_id TEXT,
        user_id TEXT,
        event_type TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        outcome TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        organization_id TEXT,
        workspace_id TEXT,
        user_id TEXT,
        job_type TEXT NOT NULL,
        status TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        dataset_id TEXT,
        payload_json TEXT NOT NULL,
        result_json TEXT,
        error TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )
    """,
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:80] or "workspace"


def _fallback_url() -> str:
    settings = get_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    path = (settings.data_root / "metadata.db").resolve()
    return f"sqlite:///{path}"


def _make_engine(url: str) -> Engine:
    if url not in _ENGINES:
        kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        elif url.startswith("postgresql"):
            kwargs["connect_args"] = {"connect_timeout": 2}
        _ENGINES[url] = create_engine(url, **kwargs)
    return _ENGINES[url]


def _probe(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_engine() -> Engine:
    settings = get_settings()
    preferred = settings.database_url
    selected = _SELECTED_BACKENDS.get(preferred)
    if selected:
        return _make_engine(selected)
    engine = _make_engine(preferred)
    if _probe(engine):
        _SELECTED_BACKENDS[preferred] = preferred
        return engine
    if not settings.metadata_fallback_sqlite:
        raise RuntimeError("Metadata database unavailable and SQLite fallback disabled")
    fallback = _fallback_url()
    _SELECTED_BACKENDS[preferred] = fallback
    return _make_engine(fallback)


def init_metadata_store() -> Engine:
    engine = get_engine()
    with engine.begin() as conn:
        for ddl in SCHEMA_SQL:
            conn.execute(text(ddl))
    return engine


@contextmanager
def connection() -> Iterator[Any]:
    engine = init_metadata_store()
    with engine.begin() as conn:
        yield conn


def execute(sql: str, params: dict[str, Any] | None = None) -> None:
    with connection() as conn:
        conn.execute(text(sql), params or {})


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
        return [dict(r) for r in rows]


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def metadata_backend() -> dict[str, Any]:
    engine = init_metadata_store()
    return {
        "dialect": engine.dialect.name,
        "url": "postgresql" if engine.dialect.name == "postgresql" else "sqlite-local-fallback",
        "fallback_enabled": get_settings().metadata_fallback_sqlite,
    }
