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
    CREATE TABLE IF NOT EXISTS assistant_session_memory (
        session_id TEXT PRIMARY KEY,
        workspace_id TEXT,
        active_entities_json TEXT NOT NULL DEFAULT '{}',
        facts_json TEXT NOT NULL DEFAULT '{}',
        decisions_json TEXT NOT NULL DEFAULT '[]',
        last_intent TEXT,
        last_entities_json TEXT NOT NULL DEFAULT '{}',
        recent_columns_json TEXT NOT NULL DEFAULT '[]',
        recent_intents_json TEXT NOT NULL DEFAULT '[]',
        last_result_summary TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_project_memory (
        id TEXT PRIMARY KEY,
        scope_id TEXT NOT NULL,
        workspace_id TEXT,
        user_id TEXT,
        session_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        dataset_id TEXT,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        pinned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL,
        UNIQUE(scope_id, artifact_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_project_memory_policy (
        scope_id TEXT PRIMARY KEY,
        policy_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
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
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id TEXT PRIMARY KEY,
        preferences_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
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
    CREATE TABLE IF NOT EXISTS collaboration_teams (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collaboration_team_members (
        team_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        added_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(team_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collaboration_artifact_shares (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        resource_version TEXT,
        recipient_user_id TEXT,
        recipient_team_id TEXT,
        permission TEXT NOT NULL DEFAULT 'view',
        note TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL,
        expires_at TEXT,
        revoked_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collaboration_ws_tickets (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_registry_entries (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        model_key TEXT NOT NULL,
        version_no INTEGER NOT NULL,
        name TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'draft',
        role TEXT NOT NULL DEFAULT 'candidate',
        artifact_sha256 TEXT NOT NULL,
        card_sha256 TEXT NOT NULL,
        registered_by TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        promoted_at TEXT,
        retired_at TEXT,
        notes TEXT,
        UNIQUE(workspace_id, model_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_registry_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        registry_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        action TEXT NOT NULL,
        from_stage TEXT,
        to_stage TEXT,
        actor_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_monitoring_runs (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        registry_id TEXT,
        reference_dataset_id TEXT NOT NULL,
        current_dataset_id TEXT NOT NULL,
        status TEXT NOT NULL,
        rows_evaluated INTEGER NOT NULL DEFAULT 0,
        performance_json TEXT NOT NULL,
        drift_json TEXT NOT NULL,
        policy_json TEXT NOT NULL,
        degradation_json TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_monitor_schedules (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        current_dataset_id TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 0,
        interval_minutes INTEGER NOT NULL DEFAULT 1440,
        policy_json TEXT NOT NULL,
        next_run_at TEXT,
        last_enqueued_at TEXT,
        created_by TEXT NOT NULL,
        updated_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id, model_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_retraining_policies (
        workspace_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 0,
        min_rows INTEGER NOT NULL DEFAULT 100,
        metric_degradation_threshold REAL NOT NULL DEFAULT 0.15,
        feature_drift_threshold REAL NOT NULL DEFAULT 0.35,
        cooldown_hours INTEGER NOT NULL DEFAULT 168,
        auto_create_request INTEGER NOT NULL DEFAULT 1,
        updated_by TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id, model_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_retraining_requests (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        registry_id TEXT,
        source_monitoring_run_id TEXT,
        status TEXT NOT NULL DEFAULT 'requested',
        reasons_json TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,

"""
CREATE TABLE IF NOT EXISTS feature_sets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    source_dataset_id TEXT NOT NULL,
    entity_keys_json TEXT NOT NULL,
    event_time_column TEXT,
    features_json TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    schema_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, name)
)
""",
"""
CREATE TABLE IF NOT EXISTS feature_materializations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    feature_set_id TEXT NOT NULL,
    source_dataset_id TEXT NOT NULL,
    source_dataset_version INTEGER NOT NULL,
    materialized_dataset_id TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    schema_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""",
"""
CREATE TABLE IF NOT EXISTS model_deployments (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    endpoint_key TEXT NOT NULL,
    name TEXT NOT NULL,
    model_key TEXT NOT NULL,
    primary_model_id TEXT NOT NULL,
    secondary_model_id TEXT,
    strategy TEXT NOT NULL DEFAULT 'champion',
    traffic_percent REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'inactive',
    feature_contract_json TEXT NOT NULL,
    revision_no INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, endpoint_key)
)
""",
"""
CREATE TABLE IF NOT EXISTS model_deployment_revisions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    reason TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(deployment_id, revision_no)
)
""",
"""
CREATE TABLE IF NOT EXISTS model_serving_requests (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    shadow_model_id TEXT,
    strategy TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    schema_valid INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    status TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS ai_analysis_runs (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_version INTEGER NOT NULL,
    workspace_id TEXT,
    organization_id TEXT,
    user_id TEXT,
    cache_key TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    current_tool TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    cached INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
)
""",
"""
CREATE INDEX IF NOT EXISTS idx_ai_analysis_runs_dataset_created
ON ai_analysis_runs(dataset_id, created_at)
""",
"""
CREATE TABLE IF NOT EXISTS ai_analysis_cache (
    cache_key TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_version INTEGER NOT NULL,
    semantic_version TEXT,
    engine_version TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_hit_at TEXT,
    hit_count INTEGER NOT NULL DEFAULT 0
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
    """
    CREATE TABLE IF NOT EXISTS telemetry_events (
        id TEXT PRIMARY KEY,
        organization_id TEXT,
        workspace_id TEXT,
        user_id TEXT,
        event_kind TEXT NOT NULL,
        feature TEXT,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        latency_ms REAL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        estimated_cost_usd REAL,
        resource_type TEXT,
        resource_id TEXT,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_attempts (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        status TEXT NOT NULL,
        error TEXT,
        latency_ms REAL,
        scheduled_retry_at TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        UNIQUE(job_id, attempt_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_suites (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_cases (
        id TEXT PRIMARY KEY,
        suite_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        question TEXT NOT NULL,
        expectations_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_runs (
        id TEXT PRIMARY KEY,
        suite_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        status TEXT NOT NULL,
        score REAL NOT NULL,
        cases_total INTEGER NOT NULL,
        cases_passed INTEGER NOT NULL,
        cases_failed INTEGER NOT NULL,
        duration_ms REAL NOT NULL,
        triggered_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_results (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        status TEXT NOT NULL,
        score REAL NOT NULL,
        duration_ms REAL NOT NULL,
        checks_json TEXT NOT NULL,
        result_snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_destinations (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'webhook',
        webhook_url TEXT NOT NULL,
        secret_ciphertext TEXT NOT NULL,
        headers_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_rules (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        event_type TEXT NOT NULL,
        dataset_id TEXT,
        destination_id TEXT NOT NULL,
        conditions_json TEXT NOT NULL,
        approval_mode TEXT NOT NULL DEFAULT 'always',
        throttle_minutes INTEGER NOT NULL DEFAULT 15,
        dedupe_minutes INTEGER NOT NULL DEFAULT 1440,
        quiet_hours_json TEXT,
        payload_template_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        max_retries INTEGER NOT NULL DEFAULT 2,
        retry_backoff_seconds INTEGER NOT NULL DEFAULT 15,
        last_triggered_at TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_runs (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        rule_id TEXT NOT NULL,
        destination_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_id TEXT NOT NULL,
        dataset_id TEXT,
        status TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        trigger_payload_json TEXT NOT NULL,
        rendered_payload_json TEXT NOT NULL,
        approval_required INTEGER NOT NULL DEFAULT 0,
        requested_by TEXT,
        approved_by TEXT,
        approval_note TEXT,
        approved_at TEXT,
        scheduled_for TEXT,
        job_id TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_response_code INTEGER,
        last_response_body TEXT,
        error TEXT,
        replay_of TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_delivery_attempts (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        status TEXT NOT NULL,
        response_code INTEGER,
        response_body TEXT,
        latency_ms REAL,
        error TEXT,
        created_at TEXT NOT NULL,
        finished_at TEXT,
        UNIQUE(run_id, attempt_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_destination_options (
        destination_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        config_json TEXT NOT NULL,
        credential_type TEXT NOT NULL DEFAULT 'none',
        credential_ciphertext TEXT NOT NULL DEFAULT '',
        oauth_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_rule_approval_chains (
        rule_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        steps_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_approval_steps (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        step_order INTEGER NOT NULL,
        label TEXT NOT NULL,
        required_role TEXT,
        required_user_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        acted_by TEXT,
        note TEXT,
        acted_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(run_id, step_order)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'local',
        refresh_token_hash TEXT NOT NULL,
        device_label TEXT,
        user_agent TEXT,
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        rotated_at TEXT
    )
    """,

"""
CREATE TABLE IF NOT EXISTS auth_webauthn_credentials (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    credential_id TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    transports_json TEXT NOT NULL DEFAULT '[]',
    label TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    disabled_at TEXT
)
""",
"""
CREATE TABLE IF NOT EXISTS auth_mfa_challenges (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    challenge_type TEXT NOT NULL,
    challenge_b64 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
)
""",
"""
CREATE TABLE IF NOT EXISTS upload_security_scans (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    engine TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
)
""",
    """
    CREATE TABLE IF NOT EXISTS oidc_providers (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        issuer TEXT NOT NULL,
        client_id TEXT NOT NULL,
        client_secret_ciphertext TEXT NOT NULL,
        authorization_endpoint TEXT NOT NULL,
        token_endpoint TEXT NOT NULL,
        jwks_uri TEXT NOT NULL,
        scopes_json TEXT NOT NULL,
        email_claim TEXT NOT NULL DEFAULT 'email',
        name_claim TEXT NOT NULL DEFAULT 'name',
        groups_claim TEXT,
        allowed_domains_json TEXT NOT NULL,
        default_role TEXT NOT NULL DEFAULT 'viewer',
        enabled INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_tested_at TEXT,
        last_error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS oidc_login_states (
        state_hash TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        code_verifier_ciphertext TEXT NOT NULL,
        redirect_uri TEXT NOT NULL,
        nonce_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_identities (
        provider_id TEXT NOT NULL,
        subject TEXT NOT NULL,
        user_id TEXT NOT NULL,
        email TEXT,
        created_at TEXT NOT NULL,
        last_login_at TEXT NOT NULL,
        PRIMARY KEY(provider_id, subject)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS secret_vault_items (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'local_encrypted',
        reference_json TEXT NOT NULL DEFAULT '{}',
        current_version INTEGER NOT NULL DEFAULT 0,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(workspace_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS secret_vault_versions (
        id TEXT PRIMARY KEY,
        secret_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        ciphertext TEXT NOT NULL,
        checksum TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        rotated_from INTEGER,
        UNIQUE(secret_id, version)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS organization_scim_tokens (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        token_prefix TEXT NOT NULL,
        default_role TEXT NOT NULL DEFAULT 'viewer',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        revoked_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scim_provisioned_users (
        organization_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        external_id TEXT,
        provisioned_by_token_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (organization_id, user_id)
    )
    """,

"""
CREATE TABLE IF NOT EXISTS plugin_installations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    plugin_key TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT NOT NULL,
    protocol TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    network_scope TEXT NOT NULL DEFAULT 'public',
    auth_type TEXT NOT NULL DEFAULT 'none',
    auth_header TEXT,
    secret_id TEXT,
    context_policy TEXT NOT NULL DEFAULT 'none',
    timeout_seconds INTEGER NOT NULL DEFAULT 15,
    manifest_json TEXT NOT NULL,
    checksum TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'installed',
    last_error TEXT,
    last_synced_at TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, plugin_key)
)
""",
"""
CREATE TABLE IF NOT EXISTS plugin_tools (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    remote_name TEXT NOT NULL,
    namespaced_name TEXT NOT NULL,
    description TEXT NOT NULL,
    input_schema_json TEXT NOT NULL,
    declared_risk TEXT NOT NULL DEFAULT 'read',
    required_permissions_json TEXT NOT NULL,
    requires_dataset INTEGER NOT NULL DEFAULT 0,
    requires_model INTEGER NOT NULL DEFAULT 0,
    http_method TEXT,
    http_path TEXT,
    metadata_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, namespaced_name)
)
""",
"""
CREATE TABLE IF NOT EXISTS plugin_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    user_id TEXT,
    status TEXT NOT NULL,
    argument_keys_json TEXT NOT NULL,
    error TEXT,
    duration_ms REAL,
    created_at TEXT NOT NULL,
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
    try:
        engine = _make_engine(preferred)
        if _probe(engine):
            _SELECTED_BACKENDS[preferred] = preferred
            return engine
    except Exception:
        if not settings.metadata_fallback_sqlite:
            raise
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
        from app.services.schema_migrations import apply_pending_migrations
        if get_settings().schema_auto_migrate:
            apply_pending_migrations(conn)
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
