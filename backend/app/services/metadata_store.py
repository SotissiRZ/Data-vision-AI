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
    CREATE TABLE IF NOT EXISTS review_items (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        organization_id TEXT,
        dataset_id TEXT,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        resource_version TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'normal',
        status TEXT NOT NULL DEFAULT 'draft',
        owner_user_id TEXT,
        reviewer_user_id TEXT,
        created_by TEXT NOT NULL,
        due_at TEXT,
        snapshot_json TEXT NOT NULL,
        decision_note TEXT,
        submitted_at TEXT,
        decided_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_comments (
        id TEXT PRIMARY KEY,
        review_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        body TEXT NOT NULL,
        mentions_json TEXT NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0,
        resolved_by TEXT,
        resolved_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_events (
        id TEXT PRIMARY KEY,
        review_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        actor_user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_certifications (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        review_id TEXT NOT NULL,
        owner_user_id TEXT,
        certified_by TEXT NOT NULL,
        certified_at TEXT NOT NULL,
        valid_until TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collaboration_notifications (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        review_id TEXT,
        notification_type TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        read_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_connectors (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        connector_type TEXT NOT NULL,
        host TEXT NOT NULL,
        port INTEGER NOT NULL,
        database_name TEXT NOT NULL,
        username TEXT NOT NULL,
        password_ciphertext TEXT NOT NULL,
        ssl_mode TEXT NOT NULL DEFAULT 'prefer',
        options_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'untested',
        last_tested_at TEXT,
        last_error TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS connector_sources (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        connector_id TEXT NOT NULL,
        name TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        table_name TEXT,
        source_query TEXT,
        refresh_mode TEXT NOT NULL DEFAULT 'full',
        incremental_column TEXT,
        watermark_json TEXT,
        freshness_sla_minutes INTEGER NOT NULL DEFAULT 1440,
        schema_drift_policy TEXT NOT NULL DEFAULT 'warn',
        source_options_json TEXT NOT NULL,
        dataset_id TEXT,
        schema_json TEXT,
        schema_drift_json TEXT,
        status TEXT NOT NULL DEFAULT 'never_refreshed',
        last_refresh_started_at TEXT,
        last_refresh_finished_at TEXT,
        last_success_at TEXT,
        last_rows_fetched INTEGER,
        last_error TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_schedules (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        interval_minutes INTEGER NOT NULL,
        next_run_at TEXT,
        last_enqueued_at TEXT,
        created_by TEXT NOT NULL,
        updated_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (workspace_id, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_runs (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        connector_id TEXT NOT NULL,
        dataset_id_before TEXT,
        dataset_id_after TEXT,
        mode TEXT NOT NULL,
        status TEXT NOT NULL,
        trigger_type TEXT NOT NULL,
        triggered_by TEXT,
        job_id TEXT,
        rows_fetched INTEGER,
        rows_written INTEGER,
        watermark_before_json TEXT,
        watermark_after_json TEXT,
        schema_drift_json TEXT,
        error TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT
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
    """
    CREATE TABLE IF NOT EXISTS data_contracts (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        dataset_root_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        rules_json TEXT NOT NULL,
        enforcement_mode TEXT NOT NULL DEFAULT 'warn',
        enabled INTEGER NOT NULL DEFAULT 1,
        owner_user_id TEXT,
        status TEXT NOT NULL DEFAULT 'never_run',
        last_score REAL,
        last_run_at TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_contract_runs (
        id TEXT PRIMARY KEY,
        contract_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        dataset_version INTEGER,
        status TEXT NOT NULL,
        score REAL NOT NULL,
        checks_total INTEGER NOT NULL,
        checks_passed INTEGER NOT NULL,
        checks_failed INTEGER NOT NULL,
        blocking_failures INTEGER NOT NULL,
        results_json TEXT NOT NULL,
        baseline_dataset_id TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lineage_registry (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(workspace_id, source_type, source_id, target_type, target_id, relation)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reliability_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        details_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL,
        resolved_at TEXT
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
