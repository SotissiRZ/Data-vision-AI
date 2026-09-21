from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import text


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version="2.59.0-001",
        name="resilience_operations",
        statements=(
            """CREATE TABLE IF NOT EXISTS backup_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                kind TEXT NOT NULL,
                archive_path TEXT,
                sha256 TEXT,
                database_backend TEXT,
                size_bytes INTEGER,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                details_json TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS kms_rotation_events (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                key_id TEXT NOT NULL,
                previous_version INTEGER,
                new_version INTEGER,
                actor_user_id TEXT,
                organization_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                details_json TEXT
            )""",
        ),
    ),
    Migration(
        version="2.60.0-001",
        name="sre_operations",
        statements=(
            "ALTER TABLE backup_runs ADD COLUMN object_uri TEXT",
            "ALTER TABLE backup_runs ADD COLUMN object_key TEXT",
            """CREATE TABLE IF NOT EXISTS restore_drills (
                id TEXT PRIMARY KEY,
                backup_id TEXT,
                status TEXT NOT NULL,
                archive_sha256 TEXT,
                checks_json TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS sre_alert_snapshots (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                status TEXT NOT NULL,
                alerts_json TEXT,
                error_budget_json TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_sre_alert_snapshots_workspace_created
               ON sre_alert_snapshots(workspace_id, created_at)""",
            """CREATE TABLE IF NOT EXISTS chaos_drills (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                status TEXT NOT NULL,
                intensity INTEGER NOT NULL,
                result_json TEXT,
                created_by TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_chaos_drills_workspace_started
               ON chaos_drills(workspace_id, started_at)""",
        ),
    ),
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_migration_table(conn) -> None:
    conn.execute(text("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )"""))


def applied_versions(conn) -> set[str]:
    ensure_migration_table(conn)
    rows = conn.execute(text("SELECT version FROM schema_migrations")).all()
    return {str(row[0]) for row in rows}


def pending_migrations(conn) -> list[Migration]:
    applied = applied_versions(conn)
    return [migration for migration in MIGRATIONS if migration.version not in applied]


def apply_pending_migrations(conn) -> list[str]:
    ensure_migration_table(conn)
    applied_now: list[str] = []
    for migration in pending_migrations(conn):
        for statement in migration.statements:
            conn.execute(text(statement))
        conn.execute(
            text("INSERT INTO schema_migrations(version,name,applied_at) VALUES(:version,:name,:applied_at)"),
            {"version": migration.version, "name": migration.name, "applied_at": _utcnow()},
        )
        applied_now.append(migration.version)
    return applied_now


def migration_status() -> dict:
    # Lazy import avoids a module cycle with metadata_store.init_metadata_store().
    from app.services.metadata_store import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        ensure_migration_table(conn)
        applied = applied_versions(conn)
        pending = [m.version for m in MIGRATIONS if m.version not in applied]
    return {
        "current": MIGRATIONS[-1].version if MIGRATIONS else None,
        "applied": sorted(applied),
        "pending": pending,
        "ready": not pending,
    }
