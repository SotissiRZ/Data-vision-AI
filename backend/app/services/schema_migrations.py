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
    Migration(
        version="2.61.0-001",
        name="sre_multizone_continuity",
        statements=(
            """CREATE TABLE IF NOT EXISTS sre_alert_routes (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                min_severity TEXT NOT NULL DEFAULT 'medium',
                event_type TEXT NOT NULL DEFAULT 'sre_slo_breach',
                route_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_sre_alert_routes_workspace
               ON sre_alert_routes(workspace_id, enabled)""",
            """CREATE TABLE IF NOT EXISTS backup_replications (
                id TEXT PRIMARY KEY,
                backup_id TEXT,
                target_name TEXT NOT NULL,
                status TEXT NOT NULL,
                object_uri TEXT,
                object_key TEXT,
                sha256 TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_backup_replications_backup
               ON backup_replications(backup_id, started_at)""",
            """CREATE TABLE IF NOT EXISTS dr_drills (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                checks_json TEXT,
                created_by TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_dr_drills_workspace_started
               ON dr_drills(workspace_id, started_at)""",
        ),
    ),
    Migration(
        version="2.62.0-001",
        name="distributed_observability_multicluster",
        statements=(
            "ALTER TABLE backup_replications ADD COLUMN verification_status TEXT",
            "ALTER TABLE backup_replications ADD COLUMN verified_at TEXT",
            "ALTER TABLE backup_replications ADD COLUMN verification_json TEXT",
            """CREATE TABLE IF NOT EXISTS cluster_control_state (
                workspace_id TEXT PRIMARY KEY,
                active_cluster_id TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS cluster_failover_events (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                source_cluster_id TEXT NOT NULL,
                target_cluster_id TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                confirmation_token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                executor_mode TEXT NOT NULL,
                result_json TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                confirmed_at TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_cluster_failover_workspace_created
               ON cluster_failover_events(workspace_id, created_at)""",
        ),
    ),
    Migration(
        version="2.63.0-001",
        name="operational_security_supply_chain",
        statements=(
            """CREATE TABLE IF NOT EXISTS secret_rotation_events (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                secret_id TEXT NOT NULL,
                status TEXT NOT NULL,
                previous_version INTEGER,
                new_version INTEGER,
                due_at TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                details_json TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_secret_rotation_workspace_created
               ON secret_rotation_events(workspace_id, created_at)""",
            """CREATE TABLE IF NOT EXISTS release_rollback_events (
                id TEXT PRIMARY KEY,
                current_version TEXT NOT NULL,
                target_version TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                confirmation_token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                executor_mode TEXT NOT NULL,
                artifact_sha256 TEXT,
                result_json TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                confirmed_at TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_release_rollback_created
               ON release_rollback_events(created_at)""",
        ),
    ),
    Migration(
        version="2.64.0-001",
        name="runtime_security_continuous_compliance",
        statements=(
            """CREATE TABLE IF NOT EXISTS continuous_compliance_runs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                control_count INTEGER NOT NULL,
                drift_count INTEGER NOT NULL,
                unknown_count INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_compliance_runs_workspace_created
               ON continuous_compliance_runs(workspace_id, created_at)""",
            """CREATE TABLE IF NOT EXISTS runtime_security_events (
                id TEXT PRIMARY KEY,
                workspace_id TEXT,
                source TEXT NOT NULL,
                severity TEXT NOT NULL,
                rule TEXT NOT NULL,
                details_json TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_runtime_security_workspace_created
               ON runtime_security_events(workspace_id, created_at)""",
            """CREATE TABLE IF NOT EXISTS compliance_evidence_packs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT,
                status TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                path TEXT NOT NULL,
                summary_json TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_evidence_packs_workspace_created
               ON compliance_evidence_packs(workspace_id, created_at)""",
        ),
    ),

    Migration(
        version="2.65.0-001",
        name="regulatory_compliance_posture",
        statements=(
            """CREATE TABLE IF NOT EXISTS regulatory_posture_snapshots (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                framework_id TEXT NOT NULL,
                status TEXT NOT NULL,
                score REAL NOT NULL,
                sha256 TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_regulatory_posture_workspace_created
               ON regulatory_posture_snapshots(workspace_id, created_at)""",
            """CREATE TABLE IF NOT EXISTS compliance_exceptions (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                control_id TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                compensating_controls_json TEXT,
                owner TEXT,
                expires_at TEXT NOT NULL,
                requested_by TEXT,
                reviewed_by TEXT,
                review_note TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )""",
            """CREATE INDEX IF NOT EXISTS idx_compliance_exceptions_workspace_control
               ON compliance_exceptions(workspace_id, control_id, status)""",
            """CREATE TABLE IF NOT EXISTS regulatory_evidence_exports (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                framework_id TEXT NOT NULL,
                status TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                path TEXT NOT NULL,
                summary_json TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_regulatory_evidence_workspace_created
               ON regulatory_evidence_exports(workspace_id, created_at)""",
        ),
    ),

    Migration(
        version="2.67.0-001",
        name="persistent_notebook_runtime",
        statements=(
            """CREATE TABLE IF NOT EXISTS notebook_environments (
                notebook_id TEXT PRIMARY KEY,
                python_requirements_json TEXT NOT NULL,
                r_requirements_json TEXT NOT NULL,
                python_lock_json TEXT NOT NULL,
                r_lock_json TEXT NOT NULL,
                policy_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS notebook_kernel_sessions (
                notebook_id TEXT NOT NULL,
                language TEXT NOT NULL,
                session_id TEXT NOT NULL,
                generation TEXT,
                state_status TEXT NOT NULL,
                execution_count INTEGER NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(notebook_id, language)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_notebook_kernel_sessions_state
               ON notebook_kernel_sessions(state_status, last_seen_at)""",
        ),
    ),

    Migration(
        version="2.76.0-001",
        name="workspace_runtime_environments",
        statements=(
            """CREATE TABLE IF NOT EXISTS workspace_runtime_environments (
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                python_requirements_json TEXT NOT NULL,
                r_requirements_json TEXT NOT NULL,
                python_lock_json TEXT NOT NULL,
                r_lock_json TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                fingerprint_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                policy_json TEXT NOT NULL,
                inventory_sha256 TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                synced_at TEXT,
                PRIMARY KEY(scope_type, scope_id)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_workspace_runtime_env_status
               ON workspace_runtime_environments(status, updated_at)""",
        ),
    ),

    Migration(
        version="2.77.0-001",
        name="performance_slo_evidence",
        statements=(
            """CREATE TABLE IF NOT EXISTS performance_evidence_runs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                source TEXT NOT NULL,
                execution_context TEXT NOT NULL,
                target TEXT,
                status TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_performance_evidence_workspace_created
               ON performance_evidence_runs(workspace_id, created_at)""",
        ),
    ),


    Migration(
        version="2.68.0-001",
        name="data_catalog_discovery",
        statements=(
            """CREATE TABLE IF NOT EXISTS data_catalog_entries (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                title TEXT,
                description TEXT,
                business_domain TEXT,
                owner_user_id TEXT,
                steward_user_id TEXT,
                tags_json TEXT,
                glossary_json TEXT,
                certification_status TEXT NOT NULL DEFAULT 'unreviewed',
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workspace_id, resource_type, resource_id)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_data_catalog_workspace_type
               ON data_catalog_entries(workspace_id, resource_type, updated_at)""",
        ),
    ),

    Migration(
        version="2.78.0-001",
        name="cdc_gap_closure",
        statements=(
            """CREATE TABLE IF NOT EXISTS organization_plan_assignments (
                organization_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                updated_by TEXT,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS plan_usage_daily (
                workspace_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                amount INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id, metric, usage_date)
            )""",
            """CREATE TABLE IF NOT EXISTS proactive_scan_schedules (
                dataset_id TEXT PRIMARY KEY,
                workspace_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                interval_minutes INTEGER NOT NULL DEFAULT 1440,
                next_run_at TEXT NOT NULL,
                last_run_at TEXT,
                last_status TEXT,
                watch_ids_json TEXT NOT NULL DEFAULT '[]',
                auto_configure INTEGER NOT NULL DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_plan_usage_workspace_date
               ON plan_usage_daily(workspace_id, usage_date)""",
            """CREATE INDEX IF NOT EXISTS idx_proactive_schedule_due
               ON proactive_scan_schedules(enabled, next_run_at)""",
        ),
    ),

    Migration(
        version="2.79.0-001",
        name="release_candidate_hardening_marker",
        statements=(),
    ),

    Migration(
        version="2.80.0-001",
        name="release_candidate_freeze_marker",
        statements=(),
    ),

    Migration(
        version="2.81.0-001",
        name="security_documentation_freeze",
        statements=(
            """CREATE TABLE IF NOT EXISTS auth_login_throttle (
                principal_hash TEXT PRIMARY KEY,
                failures INTEGER NOT NULL DEFAULT 0,
                window_started_at TEXT NOT NULL,
                locked_until TEXT,
                updated_at TEXT NOT NULL
            )""",
            """CREATE INDEX IF NOT EXISTS idx_auth_login_throttle_locked
               ON auth_login_throttle(locked_until)""",
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


def _migration_sort_key(migration: Migration) -> tuple[int, int, int, int]:
    release, _, sequence = migration.version.partition("-")
    parts = [int(part) for part in release.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2], int(sequence or 0)


def ordered_migrations() -> tuple[Migration, ...]:
    """Return migrations in release order even if declaration blocks are moved by backports."""
    return tuple(sorted(MIGRATIONS, key=_migration_sort_key))


def pending_migrations(conn) -> list[Migration]:
    applied = applied_versions(conn)
    return [migration for migration in ordered_migrations() if migration.version not in applied]


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
        migrations = ordered_migrations()
        pending = [m.version for m in migrations if m.version not in applied]
    return {
        "current": migrations[-1].version if migrations else None,
        "applied": sorted(applied),
        "pending": pending,
        "ready": not pending,
    }
