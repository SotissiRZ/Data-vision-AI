from __future__ import annotations

from typing import Any
from pathlib import Path
import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings

from app.services.auth_service import (
    bootstrap, decode_token, get_user, login, session_payload, has_permission, workspace_role,
    validate_session_payload, refresh_authenticated_session, list_user_sessions, revoke_user_session, revoke_all_user_sessions,
)
from app.services.audit_service import list_events, record_event
from app.services.job_service import get_job, list_jobs, request_cancel, submit_job, queue_status
from app.services.metadata_store import metadata_backend, fetch_one
from app.services.collaboration import (
    add_comment, assign_review, create_review, get_review, list_notifications, list_reviews,
    mark_notification_read, mark_all_notifications_read, resolve_comment, review_summary, transition_review,
    certify_review, list_certifications, revoke_certification,
    list_teams, create_team, set_team_member, create_artifact_share, list_artifact_shares, revoke_artifact_share,
    review_snapshot_diff, decision_ledger, collaboration_activity, create_realtime_ticket, consume_realtime_ticket,
)
from app.services.connector_service import (
    create_connector, update_connector, get_connector, list_connectors, delete_connector, test_connector, discover_connector, connectors_catalog,
    create_source, get_source, list_sources, delete_source, preview_source, refresh_source,
    save_schedule, list_schedules, get_refresh_runs, workspace_refresh_health,
)
from app.services.cdc_ingestion import ingest_cdc_events, cdc_status
from app.services.operational_intelligence import (
    operational_overview, feature_usage, list_telemetry, list_trace_events, job_attempts,
    create_evaluation_suite, list_evaluation_suites, get_evaluation_suite, add_evaluation_case,
    run_evaluation_suite, list_evaluation_runs, get_evaluation_run,
)
from app.services.sre_operations import (
    sre_status, capture_sre_snapshot, emit_sre_alerts, list_sre_snapshots,
    list_sre_alert_routes, save_sre_alert_route, delete_sre_alert_route,
    run_dr_drill, list_dr_drills, run_chaos_drill, list_chaos_drills,
)
from app.services.backup_service import verify_backup_replications, list_backup_replications
from app.services.multi_cluster import cluster_topology_status, create_failover_plan, confirm_failover, list_failovers
from app.services.data_reliability import (
    save_contract, get_contract, list_contracts, delete_contract, run_contract, list_contract_runs,
    build_lineage_graph, impact_analysis, publication_gate, reliability_summary,
)
from app.services.data_catalog import (
    catalog_assets, catalog_summary, get_catalog_entry, save_catalog_entry,
)
from app.services.governed_actions import (
    action_summary, approve_run, create_destination, delete_destination, delete_rule, dispatch_event,
    get_run as get_action_run, list_destinations, list_rules as list_action_rules, list_runs as list_action_runs,
    reject_run, replay_run, save_rule as save_action_rule, test_destination_delivery,
)
from app.services.plugin_service import (
    delete_plugin, get_plugin, install_plugin, list_plugin_runs, list_plugins,
    sync_plugin, test_plugin, update_plugin,
)
from app.assistant.plugin_runtime import refresh_runtime_plugins
from app.services.user_preferences import get_user_preferences, save_user_preferences
from app.services.mfa_service import (
    begin_password_login, begin_registration, finish_registration,
    finish_password_login, mfa_status, disable_credential,
)
from app.services.secret_crypto import kms_status, rotate_kms_key, vault_key_status
from app.services.schema_migrations import migration_status
from app.services.upload_security import antivirus_status
from app.services.identity_service import (
    create_oidc_provider, list_oidc_providers, list_public_oidc_providers, delete_oidc_provider, oidc_start, oidc_exchange,
    create_secret, list_secrets, rotate_secret, test_secret,
)
from app.services.governance_control import control_plane_overview, capture_governance_snapshot, list_governance_snapshots
from app.services.entreprise_platform import (
    authenticate_scim_token, create_scim_token, deactivate_scim_user, discover_oidc_for_email,
    enforce_private_ai, entreprise_readiness, get_scim_user, list_scim_tokens, list_scim_users,
    patch_scim_user, private_ai_posture, prometheus_metrics, prometheus_all_metrics, provision_scim_user, revoke_scim_token,
    delete_scim_group, get_scim_group, list_scim_groups, patch_scim_group, provision_scim_group,
)
from app.services.session_security import (
    get_organization_security_policy, save_organization_security_policy, list_trusted_devices,
    trust_session_device, revoke_trusted_device, internal_metrics_token_valid,
)
from app.services.operational_security import (
    secret_rotation_status, rotate_due_secrets, list_secret_rotation_events,
    create_rollback_plan, confirm_rollback, rollback_drill,
)
from app.services.continuous_compliance import (
    run_compliance_scan, latest_compliance_scan, list_compliance_scans, create_evidence_pack, list_evidence_packs,
    record_runtime_security_event, list_runtime_security_events,
)
from app.services.regulatory_compliance import (
    control_catalog, posture as regulatory_posture, capture_posture_snapshot, posture_history,
    create_exception as create_compliance_exception, list_exceptions as list_compliance_exceptions,
    decide_exception as decide_compliance_exception, remediation_plan as regulatory_remediation_plan,
    create_regulatory_evidence_pack, list_regulatory_evidence_exports, get_regulatory_evidence_export,
)
from app.services.workspace_service import (
    bind_dataset,
    create_workspace,
    get_workspace,
    list_members,
    list_policies,
    list_workspace_datasets,
    save_access_policy,
    upsert_member,
    policies_for_access, apply_access_policies,
)

router = APIRouter(tags=["enterprise"])




class DataContractRequest(BaseModel):
    contract_id: str | None = None
    dataset_id: str
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=3000)
    rules: list[dict[str, Any]] = []
    enforcement_mode: str = Field(default="warn", pattern="^(monitor|warn|block)$")
    enabled: bool = True


class ContractRunRequest(BaseModel):
    dataset_id: str | None = None


class PublicationGateRequest(BaseModel):
    dataset_id: str


class CatalogAssetUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str = Field(default="", max_length=8000)
    business_domain: str = Field(default="", max_length=500)
    owner_user_id: str | None = Field(default=None, max_length=128)
    steward_user_id: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=100)
    glossary: dict[str, str] = Field(default_factory=dict)
    certification_status: str = Field(default="unreviewed", pattern="^(unreviewed|draft|certified|deprecated)$")


class PluginInstallRequest(BaseModel):
    plugin_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=180)
    version: str = Field(default="0.1.0", max_length=64)
    description: str = Field(default="", max_length=4000)
    protocol: str = Field(pattern="^(http_json|mcp_http)$")
    endpoint: str = Field(min_length=8, max_length=2000)
    network_scope: str = Field(default="public", pattern="^(public|private)$")
    auth_type: str = Field(default="none", pattern="^(none|bearer|api_key)$")
    auth_header: str | None = Field(default=None, max_length=120)
    secret_id: str | None = Field(default=None, max_length=128)
    context_policy: str = Field(default="none", pattern="^(none|semantic)$")
    timeout_seconds: int = Field(default=15, ge=2, le=30)
    enabled: bool = True
    protocol_version: str = Field(default="2025-03-26", max_length=32)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class PluginUpdateRequest(BaseModel):
    enabled: bool | None = None
    endpoint: str | None = Field(default=None, max_length=2000)
    network_scope: str | None = Field(default=None, pattern="^(public|private)$")
    secret_id: str | None = Field(default=None, max_length=128)
    auth_type: str | None = Field(default=None, pattern="^(none|bearer|api_key)$")
    auth_header: str | None = Field(default=None, max_length=120)
    context_policy: str | None = Field(default=None, pattern="^(none|semantic)$")
    timeout_seconds: int | None = Field(default=None, ge=2, le=30)

class SREAlertRouteRequest(BaseModel):
    route_id: str | None = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=180)
    min_severity: str = Field(default="medium", pattern="^(info|low|medium|high|critical)$")
    event_type: str = Field(default="sre_slo_breach", min_length=1, max_length=120)
    enabled: bool = True
    codes: list[str] = []


class DRDrillRequest(BaseModel):
    mode: str = Field(default="continuity", pattern="^(continuity|restore_only)$")


class ChaosDrillRequest(BaseModel):
    scenario: str = Field(pattern="^(queue_backlog|readiness_snapshot)$")
    intensity: int = Field(default=5, ge=1, le=20)


class FailoverPlanRequest(BaseModel):
    target_cluster_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="operational failover", min_length=3, max_length=1000)


class FailoverConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=20, max_length=512)


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="Administrateur", min_length=1, max_length=120)
    organization_name: str = Field(default="Mon organisation", min_length=1, max_length=160)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)



class WebAuthnRegistrationVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]
    label: str = Field(default="Passkey", max_length=160)


class WebAuthnLoginVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]


class UserPreferencesRequest(BaseModel):
    accessibility_mode: str | None = Field(
        default=None,
        pattern="^(normal|comfortable|large)$",
    )
    ui_zoom: int | None = Field(default=None, ge=90, le=140)
    compact_navigation: bool | None = None
    locale: str | None = Field(default=None, pattern="^(fr|en|es|ar)$")
    high_contrast: bool | None = None
    reduce_motion: bool | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=1000)


class OIDCProviderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    issuer: str = Field(min_length=5, max_length=2000)
    client_id: str = Field(min_length=1, max_length=1000)
    client_secret: str = Field(default="", max_length=4000)
    authorization_endpoint: str | None = Field(default=None, max_length=2000)
    token_endpoint: str | None = Field(default=None, max_length=2000)
    jwks_uri: str | None = Field(default=None, max_length=2000)
    scopes: list[str] = ["openid", "profile", "email"]
    allowed_domains: list[str] = []
    default_role: str = Field(default="viewer", pattern="^(owner|admin|data_scientist|analyst|viewer)$")
    email_claim: str = Field(default="email", max_length=120)
    name_claim: str = Field(default="name", max_length=120)
    groups_claim: str | None = Field(default=None, max_length=120)
    enabled: bool = True


class OIDCStartRequest(BaseModel):
    redirect_uri: str = Field(min_length=5, max_length=2000)


class OIDCExchangeRequest(BaseModel):
    provider_id: str
    code: str = Field(min_length=1, max_length=10000)
    state: str = Field(min_length=10, max_length=1000)
    redirect_uri: str = Field(min_length=5, max_length=2000)


class SecretCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    provider: str = Field(default="local_encrypted", pattern="^(local_encrypted|env|vault_kv2)$")
    value: str = Field(default="", max_length=12000)
    reference: dict[str, Any] = {}


class SecretRotateRequest(BaseModel):
    value: str = Field(default="", max_length=12000)


class SecretAutoRotateRequest(BaseModel):
    confirm: bool = False


class ReleaseRollbackPlanRequest(BaseModel):
    target_version: str = Field(pattern=r"^\d+(?:\.\d+){1,3}$")
    reason: str = Field(min_length=4, max_length=1000)
    artifact_sha256: str = Field(default="", max_length=64)


class ReleaseRollbackConfirmRequest(BaseModel):
    plan_id: str
    confirmation_token: str = Field(min_length=16, max_length=512)


class ReleaseRollbackDrillRequest(BaseModel):
    target_version: str = Field(pattern=r"^\d+(?:\.\d+){1,3}$")
    artifact_sha256: str = Field(default="", max_length=64)


class ComplianceScanRequest(BaseModel):
    observed: dict[str, Any] | None = None
    source: str = Field(default="api", min_length=1, max_length=120)


class RuntimeSecurityEventRequest(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    severity: str = Field(default="medium", pattern="^(info|low|medium|high|critical)$")
    rule: str = Field(min_length=1, max_length=240)
    details: dict[str, Any] = {}


class ComplianceExceptionRequest(BaseModel):
    control_id: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=10, max_length=4000)
    compensating_controls: list[str] = Field(default_factory=list, max_length=50)
    expires_at: str = Field(min_length=10, max_length=80)
    owner: str = Field(default="", max_length=180)


class ComplianceExceptionDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|revoked)$")
    note: str = Field(default="", max_length=2000)


class WorkspaceCreateRequest(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=160)


class ScimTokenRequest(BaseModel):
    workspace_id: str
    name: str = Field(default="Identity Provider SCIM", min_length=1, max_length=160)
    default_role: str = Field(default="viewer", pattern="^(owner|admin|data_scientist|analyst|viewer)$")


class SessionSecurityPolicyRequest(BaseModel):
    idle_timeout_minutes: int = Field(default=480, ge=5, le=10080)
    max_session_hours: int = Field(default=336, ge=1, le=2160)
    max_active_sessions: int = Field(default=10, ge=1, le=100)
    trusted_device_days: int = Field(default=30, ge=1, le=365)
    require_managed_device: bool = False


class TrustDeviceRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=160)
    label: str = Field(default="Appareil approuvé", max_length=160)


class MemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(pattern="^(owner|admin|data_scientist|analyst|viewer)$")
    display_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=200)


class BindDatasetRequest(BaseModel):
    dataset_id: str


class PolicyRequest(BaseModel):
    policy_id: str | None = None
    dataset_id: str
    name: str = Field(min_length=1, max_length=160)
    allowed_columns: list[str] = []
    row_filters: list[dict[str, Any]] = []
    applies_to_role: str | None = Field(default=None, pattern="^(owner|admin|data_scientist|analyst|viewer)$")


class JobSubmitRequest(BaseModel):
    workspace_id: str | None = None
    organization_id: str | None = None
    job_type: str = Field(pattern="^(automl|ai_analysis|forecast|report|proactive_scan|connector_refresh)$")
    dataset_id: str | None = None
    payload: dict[str, Any] = {}
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff_seconds: int = Field(default=15, ge=1, le=3600)


class EvaluationSuiteRequest(BaseModel):
    dataset_id: str
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=3000)


class EvaluationCaseRequest(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    expectations: dict[str, Any] = {}


class ReviewCreateRequest(BaseModel):
    resource_type: str = Field(pattern="^(dataset|semantic_metric|analysis|dashboard|report|model|visualization)$")
    resource_id: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=220)
    description: str = Field(default="", max_length=4000)
    dataset_id: str | None = None
    resource_version: str | None = Field(default=None, max_length=120)
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    owner_user_id: str | None = None
    reviewer_user_id: str | None = None
    due_at: str | None = None
    snapshot: dict[str, Any] = {}


class ReviewAssignRequest(BaseModel):
    owner_user_id: str | None = None
    reviewer_user_id: str | None = None
    due_at: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high|critical)$")


class ReviewTransitionRequest(BaseModel):
    action: str = Field(pattern="^(submit|approve|request_changes|reopen|archive)$")
    note: str = Field(default="", max_length=3000)


class ReviewCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=6000)
    mention_user_ids: list[str] = []


class ReviewCommentResolveRequest(BaseModel):
    resolved: bool = True


class CertificationRequest(BaseModel):
    valid_until: str | None = None
    notes: str = Field(default="", max_length=2000)


class CertificationRevokeRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class CollaborationTeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    member_user_ids: list[str] = Field(default_factory=list, max_length=200)


class CollaborationShareRequest(BaseModel):
    resource_type: str = Field(pattern="^(dataset|semantic_metric|analysis|dashboard|report|model|visualization)$")
    resource_id: str = Field(min_length=1, max_length=240)
    resource_version: str | None = Field(default=None, max_length=120)
    recipient_user_id: str | None = None
    recipient_team_id: str | None = None
    permission: str = Field(default="view", pattern="^(view|comment|review)$")
    note: str = Field(default="", max_length=2000)
    expires_at: str | None = None


class ActionDestinationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    kind: str = Field(default="webhook", pattern="^(webhook|slack|teams|jira|email)$")
    webhook_url: str = Field(default="", max_length=2000)
    secret: str = Field(default="", max_length=2000)
    headers: dict[str, str] = {}
    config: dict[str, Any] = {}
    credential_type: str = Field(default="none", pattern="^(none|hmac|bearer|basic|oauth2_client_credentials|smtp)$")
    credential: dict[str, Any] = {}
    oauth: dict[str, Any] = {}
    enabled: bool = True


class ActionRuleRequest(BaseModel):
    rule_id: str | None = None
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=3000)
    event_type: str = Field(pattern="^(manual|proactive_alert|reliability_failure|review_approved|certification_created)$")
    dataset_id: str | None = None
    destination_id: str
    conditions: list[dict[str, Any]] = []
    approval_mode: str = Field(default="always", pattern="^(always|critical_only|none|chain)$")
    approval_chain: list[dict[str, Any]] = []
    throttle_minutes: int = Field(default=15, ge=0, le=10080)
    dedupe_minutes: int = Field(default=1440, ge=0, le=43200)
    quiet_hours: dict[str, Any] | None = None
    payload_template: dict[str, Any] = {}
    enabled: bool = True
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff_seconds: int = Field(default=15, ge=1, le=3600)


class ActionEventRequest(BaseModel):
    event_type: str = Field(default="manual", pattern="^(manual|proactive_alert|reliability_failure|review_approved|certification_created)$")
    event_id: str | None = Field(default=None, max_length=300)
    dataset_id: str | None = None
    payload: dict[str, Any] = {}


class ActionDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=3000)


class ConnectorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    connector_type: str = Field(pattern="^(postgresql|mysql|mariadb|sqlite|sqlserver|oracle|redshift|snowflake|databricks|bigquery|mongodb|s3|gcs|azure_blob)$")
    host: str = Field(default="", max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str = Field(default="", max_length=2000)
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=20000)
    ssl_mode: str = Field(default="prefer", pattern="^(disable|prefer|require)$")
    options: dict[str, Any] = {}


class ConnectorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=2000)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=20000)
    ssl_mode: str | None = Field(default=None, pattern="^(disable|prefer|require)$")
    options: dict[str, Any] | None = None


class ConnectorSourceCreateRequest(BaseModel):
    connector_id: str
    name: str = Field(min_length=1, max_length=180)
    source_kind: str = Field(default="table", pattern="^(table|query|collection|object)$")
    table_name: str | None = Field(default=None, max_length=500)
    query: str | None = Field(default=None, max_length=50000)
    refresh_mode: str = Field(default="full", pattern="^(full|incremental|cdc)$")
    incremental_column: str | None = Field(default=None, max_length=255)
    freshness_sla_minutes: int = Field(default=1440, ge=5, le=525600)
    schema_drift_policy: str = Field(default="warn", pattern="^(warn|fail)$")
    source_options: dict[str, Any] = {}


class ConnectorRefreshRequest(BaseModel):
    background: bool = True


class CDCIngestRequest(BaseModel):
    events: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    event_format: str = Field(default="debezium-json", pattern="^(debezium-json|canonical)$")
    dry_run: bool = False


class RefreshScheduleRequest(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=1440, ge=15, le=43200)


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
        validate_session_payload(payload)
        user = get_user(payload["sub"])
        if not user or not user.get("is_active"):
            raise ValueError("Compte inactif")
        return user
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _workspace_permission(user_id: str, workspace_id: str, permission: str) -> None:
    if not has_permission(user_id, workspace_id, permission):
        raise HTTPException(status_code=403, detail=f"Permission requise: {permission}")


def _handle(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/bootstrap")
def auth_bootstrap(req: BootstrapRequest):
    try:
        out = bootstrap(req.email, req.password, req.display_name, req.organization_name)
        record_event("auth.bootstrap", user_id=out["user"]["id"], organization_id=out["organization_id"], workspace_id=out["workspace_id"], resource_type="user", resource_id=out["user"]["id"], payload={"email": req.email})
        return out
    except Exception as exc:
        _handle(exc)


@router.post("/auth/login")
def auth_login(req: LoginRequest, request: Request):
    try:
        out = begin_password_login(req.email, req.password, user_agent=request.headers.get("user-agent", ""))
        user = out.get("user") or {}
        record_event(
            "auth.login_mfa_challenge" if out.get("mfa_required") else "auth.login",
            user_id=user.get("id"),
            resource_type="user",
            resource_id=user.get("id"),
            payload={"email": req.email, "mfa_required": bool(out.get("mfa_required"))},
        )
        return out
    except Exception as exc:
        _handle(exc)


@router.get("/auth/me")
def auth_me(user=Depends(current_user)):
    try:
        return session_payload(user["id"])
    except Exception as exc:
        _handle(exc)



@router.get("/auth/mfa/status")
def auth_mfa_status(user=Depends(current_user)):
    try:
        return mfa_status(user["id"])
    except Exception as exc:
        _handle(exc)


@router.post("/auth/mfa/webauthn/register/options")
def auth_mfa_register_options(user=Depends(current_user)):
    try:
        return begin_registration(user["id"])
    except Exception as exc:
        _handle(exc)


@router.post("/auth/mfa/webauthn/register/verify")
def auth_mfa_register_verify(
    req: WebAuthnRegistrationVerifyRequest,
    user=Depends(current_user),
):
    try:
        out = finish_registration(
            user["id"],
            req.challenge_id,
            req.credential,
            label=req.label,
        )
        record_event(
            "auth.mfa_enrolled",
            user_id=user["id"],
            resource_type="user",
            resource_id=user["id"],
            payload={"method": "webauthn"},
        )
        return out
    except Exception as exc:
        _handle(exc)


@router.delete("/auth/mfa/webauthn/{credential_id}")
def auth_mfa_disable(credential_id: str, user=Depends(current_user)):
    try:
        out = disable_credential(user["id"], credential_id)
        record_event(
            "auth.mfa_credential_disabled",
            user_id=user["id"],
            resource_type="user",
            resource_id=user["id"],
            payload={"credential_id": credential_id},
        )
        return out
    except Exception as exc:
        _handle(exc)


@router.post("/auth/mfa/webauthn/login/verify")
def auth_mfa_login_verify(req: WebAuthnLoginVerifyRequest, request: Request):
    try:
        out = finish_password_login(req.challenge_id, req.credential, user_agent=request.headers.get("user-agent", ""))
        record_event(
            "auth.mfa_login",
            user_id=out["user"]["id"],
            resource_type="user",
            resource_id=out["user"]["id"],
            payload={"method": "webauthn"},
        )
        return out
    except Exception as exc:
        _handle(exc)


@router.get("/auth/preferences")
def auth_preferences(user=Depends(current_user)):
    try:
        return get_user_preferences(user["id"])
    except Exception as exc:
        _handle(exc)


@router.put("/auth/preferences")
def auth_preferences_save(
    req: UserPreferencesRequest,
    user=Depends(current_user),
):
    try:
        payload = {
            key: value
            for key, value in req.model_dump().items()
            if value is not None
        }
        return save_user_preferences(user["id"], payload)
    except Exception as exc:
        _handle(exc)


@router.post("/auth/refresh")
def auth_refresh(req: RefreshTokenRequest):
    try:
        return refresh_authenticated_session(req.refresh_token)
    except Exception as exc:
        _handle(exc)


@router.get("/auth/sessions")
def auth_sessions(user=Depends(current_user)):
    try:
        return {"sessions": list_user_sessions(user["id"])}
    except Exception as exc:
        _handle(exc)


@router.post("/auth/sessions/{session_id}/revoke")
def auth_session_revoke(session_id: str, user=Depends(current_user)):
    try:
        revoke_user_session(user["id"], session_id)
        return {"status": "revoked", "session_id": session_id}
    except Exception as exc:
        _handle(exc)


@router.post("/auth/logout-all")
def auth_logout_all(authorization: str | None = Header(default=None), user=Depends(current_user)):
    try:
        current_sid = None
        if authorization and authorization.lower().startswith("bearer "):
            current_sid = decode_token(authorization.split(" ", 1)[1].strip()).get("sid")
        count = revoke_all_user_sessions(user["id"], except_session_id=current_sid)
        return {"status": "ok", "revoked": count, "current_session_kept": bool(current_sid)}
    except Exception as exc:
        _handle(exc)


@router.get("/organizations/{organization_id}/security/session-policy")
def organization_session_policy(organization_id: str, user=Depends(current_user)):
    try:
        # list_trusted_devices enforces organization admin; use it as the authorization guard.
        list_trusted_devices(user["id"], organization_id)
        return get_organization_security_policy(organization_id)
    except Exception as exc:
        _handle(exc)


@router.put("/organizations/{organization_id}/security/session-policy")
def organization_session_policy_update(organization_id: str, req: SessionSecurityPolicyRequest, user=Depends(current_user)):
    try:
        return save_organization_security_policy(user["id"], organization_id, **req.model_dump())
    except Exception as exc:
        _handle(exc)


@router.get("/organizations/{organization_id}/security/trusted-devices")
def organization_trusted_devices(organization_id: str, user=Depends(current_user)):
    try:
        return {"devices": list_trusted_devices(user["id"], organization_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/organizations/{organization_id}/security/trusted-devices")
def organization_trust_device(organization_id: str, req: TrustDeviceRequest, user=Depends(current_user)):
    try:
        return trust_session_device(user["id"], organization_id, req.session_id, label=req.label)
    except Exception as exc:
        _handle(exc)


@router.delete("/organizations/{organization_id}/security/trusted-devices/{device_id}")
def organization_revoke_trusted_device(organization_id: str, device_id: str, user=Depends(current_user)):
    try:
        revoke_trusted_device(user["id"], organization_id, device_id)
        return {"status": "revoked", "id": device_id}
    except Exception as exc:
        _handle(exc)


@router.get("/auth/oidc/providers")
def auth_oidc_public_providers():
    try:
        return {"providers": list_public_oidc_providers()}
    except Exception as exc:
        _handle(exc)


@router.get("/auth/oidc/discover")
def auth_oidc_discover(email: str = Query(min_length=3, max_length=254)):
    try:
        return {"providers": discover_oidc_for_email(email), "email": email.strip().lower()}
    except Exception as exc:
        _handle(exc)


@router.post("/auth/oidc/{provider_id}/start")
def auth_oidc_start(provider_id: str, req: OIDCStartRequest):
    try:
        return oidc_start(provider_id, req.redirect_uri)
    except Exception as exc:
        _handle(exc)


@router.post("/auth/oidc/exchange")
def auth_oidc_exchange(req: OIDCExchangeRequest, request: Request):
    try:
        out = oidc_exchange(req.provider_id, req.code, req.state, req.redirect_uri, user_agent=request.headers.get("user-agent", ""))
        record_event("auth.oidc_login", user_id=out["user"]["id"], organization_id=out.get("organization_id"), workspace_id=out.get("workspace_id"), resource_type="oidc_provider", resource_id=req.provider_id, payload={"email": out["user"]["email"]})
        return out
    except Exception as exc:
        _handle(exc)


@router.get("/enterprise/status")
@router.get("/entreprise/status")
def enterprise_status():
    try:
        return {
            "metadata": metadata_backend(),
            "auth": "persistent_sessions_refresh_rotation_and_webauthn_mfa",
            "oidc": "authorization_code_pkce_rs256_jit_v2.12",
            "webauthn": mfa_status("__status_probe__") if False else {
                "enabled": get_settings().webauthn_enabled,
                "rp_id": get_settings().webauthn_rp_id,
                "origin": get_settings().webauthn_origin,
                "policy": get_settings().mfa_policy,
            },
            "secret_vault": "versioned_local_env_vault_kv2_aesgcm_envelope",
            "kms": kms_status(),
            "schema_migrations": migration_status(),
            "upload_antivirus": antivirus_status(),
            "rbac": "implemented_for_enterprise_resources",
            "row_column_policies": "policy_metadata_and_preview_ready",
            "async_jobs": "redis_worker",
            "collaboration_review": "implemented",
            "resource_certification": "implemented",
            "connectors": "11_governed_database_and_cloud_warehouse_connectors",
            "data_contracts": "implemented_v2.8",
            "lineage_impact": "implemented_v2.8",
            "publication_gate": "contract_aware_v2.8",
            "governed_actions": "native_action_connectors_and_staged_approval_v2.11",
            "action_safety": "dedupe_throttle_quiet_hours_ssrf_guard",
            "connector_secret_key": "dedicated" if bool(get_settings().connector_secret_key) else "auth_secret_fallback",
            "refresh_scheduler": "worker_polling_with_atomic_schedule_claim",
            "queue": queue_status(),
            "token_expiry_minutes": get_settings().access_token_minutes,
            "refresh_token_days": get_settings().refresh_token_days,
            "security_warning": "AUTH_SECRET doit être remplacé avant tout déploiement partagé." if get_settings().auth_secret.startswith("change-") else None,
        }
    except Exception as exc:
        _handle(exc)


@router.get("/organizations/{organization_id}/kms/status")
def organization_kms_status(organization_id: str, user=Depends(current_user)):
    try:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org": organization_id, "user": user["id"]})
        if not member or member.get("role") not in {"owner", "admin"}:
            raise PermissionError("Administration de l’organisation requise.")
        return {"kms": kms_status(), "external_key": vault_key_status() if get_settings().secret_kms_provider == "vault_transit" else None}
    except Exception as exc:
        _handle(exc)


@router.post("/organizations/{organization_id}/kms/rotate")
def organization_kms_rotate(organization_id: str, user=Depends(current_user)):
    try:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org": organization_id, "user": user["id"]})
        if not member or member.get("role") not in {"owner", "admin"}:
            raise PermissionError("Administration de l’organisation requise.")
        result = rotate_kms_key(actor_user_id=user["id"], organization_id=organization_id)
        record_event("security.kms_rotate", user_id=user["id"], organization_id=organization_id, resource_type="kms_key", resource_id=str(result.get("key_id")), payload=result)
        return result
    except Exception as exc:
        _handle(exc)


@router.post("/organizations/{organization_id}/release/rollback/plan")
def release_rollback_plan(organization_id: str, req: ReleaseRollbackPlanRequest, user=Depends(current_user)):
    try:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org": organization_id, "user": user["id"]})
        if not member or member.get("role") not in {"owner", "admin"}:
            raise PermissionError("Administration de l’organisation requise.")
        return create_rollback_plan(user["id"], target_version=req.target_version, reason=req.reason, artifact_sha256=req.artifact_sha256)
    except Exception as exc:
        _handle(exc)


@router.post("/organizations/{organization_id}/release/rollback/confirm")
def release_rollback_confirm(organization_id: str, req: ReleaseRollbackConfirmRequest, user=Depends(current_user)):
    try:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org": organization_id, "user": user["id"]})
        if not member or member.get("role") not in {"owner", "admin"}:
            raise PermissionError("Administration de l’organisation requise.")
        return confirm_rollback(user["id"], plan_id=req.plan_id, confirmation_token=req.confirmation_token)
    except Exception as exc:
        _handle(exc)


@router.post("/organizations/{organization_id}/release/rollback/drill")
def release_rollback_drill(organization_id: str, req: ReleaseRollbackDrillRequest, user=Depends(current_user)):
    try:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org": organization_id, "user": user["id"]})
        if not member or member.get("role") not in {"owner", "admin"}:
            raise PermissionError("Administration de l’organisation requise.")
        return rollback_drill(user["id"], target_version=req.target_version, artifact_sha256=req.artifact_sha256)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/compliance/status")
def workspace_compliance_status(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"latest": latest_compliance_scan(workspace_id), "scans": list_compliance_scans(workspace_id, 20), "evidence_packs": list_evidence_packs(workspace_id, 20)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/compliance/scan")
def workspace_compliance_scan(workspace_id: str, req: ComplianceScanRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return run_compliance_scan(user["id"], workspace_id=workspace_id, observed=req.observed, source=req.source)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/compliance/evidence-pack")
def workspace_compliance_evidence_pack(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return create_evidence_pack(user["id"], workspace_id=workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/catalog")
def workspace_regulatory_catalog(workspace_id: str, framework_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return control_catalog(framework_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/posture")
def workspace_regulatory_posture(workspace_id: str, framework_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return regulatory_posture(workspace_id, actor_id=user["id"], framework_id=framework_id, ensure_scan=True)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/regulatory/posture/snapshot")
def workspace_regulatory_posture_snapshot(workspace_id: str, framework_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return capture_posture_snapshot(user["id"], workspace_id=workspace_id, framework_id=framework_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/posture/history")
def workspace_regulatory_posture_history(workspace_id: str, framework_id: str | None = Query(default=None), limit: int = Query(default=90, ge=1, le=365), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"history": posture_history(workspace_id, framework_id=framework_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/exceptions")
def workspace_regulatory_exceptions(workspace_id: str, include_expired: bool = Query(default=True), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"exceptions": list_compliance_exceptions(workspace_id, include_expired=include_expired)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/regulatory/exceptions")
def workspace_regulatory_exception_create(workspace_id: str, req: ComplianceExceptionRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return create_compliance_exception(user["id"], workspace_id=workspace_id, control_id=req.control_id, reason=req.reason, compensating_controls=req.compensating_controls, expires_at=req.expires_at, owner=req.owner)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/regulatory/exceptions/{exception_id}/decision")
def workspace_regulatory_exception_decision(workspace_id: str, exception_id: str, req: ComplianceExceptionDecisionRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return decide_compliance_exception(user["id"], workspace_id=workspace_id, exception_id=exception_id, decision=req.decision, note=req.note)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/remediation")
def workspace_regulatory_remediation(workspace_id: str, framework_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return regulatory_remediation_plan(workspace_id, framework_id=framework_id)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/regulatory/evidence-pack")
def workspace_regulatory_evidence_pack(workspace_id: str, framework_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return create_regulatory_evidence_pack(user["id"], workspace_id=workspace_id, framework_id=framework_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/evidence-packs")
def workspace_regulatory_evidence_packs(workspace_id: str, limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"exports": list_regulatory_evidence_exports(workspace_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/regulatory/evidence-packs/{export_id}/download")
def workspace_regulatory_evidence_download(workspace_id: str, export_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        item = get_regulatory_evidence_export(workspace_id, export_id)
        path = str(item.get("path") or "")
        if not path or not Path(path).is_file():
            raise ValueError("Archive de conformité indisponible")
        return FileResponse(path, media_type="application/zip", filename=f"datavision-regulatory-evidence-{export_id}.zip")
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/runtime-security/events")
def workspace_runtime_security_events(workspace_id: str, min_severity: str = Query(default="info", pattern="^(info|low|medium|high|critical)$"), limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"events": list_runtime_security_events(workspace_id, min_severity=min_severity, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/runtime-security/events")
def workspace_runtime_security_event(workspace_id: str, req: RuntimeSecurityEventRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return record_runtime_security_event(user["id"], workspace_id=workspace_id, source=req.source, severity=req.severity, rule=req.rule, details=req.details)
    except Exception as exc:
        _handle(exc)


@router.get("/organizations/{organization_id}/scim/tokens")
def scim_tokens_list(organization_id: str, user=Depends(current_user)):
    try:
        return {"tokens": list_scim_tokens(user["id"], organization_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/organizations/{organization_id}/scim/tokens")
def scim_token_create(organization_id: str, req: ScimTokenRequest, user=Depends(current_user)):
    try:
        return create_scim_token(user["id"], organization_id, req.workspace_id, name=req.name, default_role=req.default_role)
    except Exception as exc:
        _handle(exc)


@router.delete("/organizations/{organization_id}/scim/tokens/{token_id}")
def scim_token_revoke(organization_id: str, token_id: str, user=Depends(current_user)):
    try:
        revoke_scim_token(user["id"], organization_id, token_id)
        return {"status": "revoked", "id": token_id}
    except Exception as exc:
        _handle(exc)


def _scim_auth_context(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Jeton SCIM requis")
    try:
        return authenticate_scim_token(authorization.split(" ", 1)[1].strip())
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/scim/v2/Users")
def scim_users_list(
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    try:
        return list_scim_users(_scim_auth_context(authorization), start_index=startIndex, count=count)
    except Exception as exc:
        _handle(exc)


@router.post("/scim/v2/Users", status_code=201)
def scim_users_create(payload: dict[str, Any], authorization: str | None = Header(default=None)):
    try:
        return provision_scim_user(_scim_auth_context(authorization), payload)
    except Exception as exc:
        _handle(exc)


@router.get("/scim/v2/Users/{user_id}")
def scim_users_get(user_id: str, authorization: str | None = Header(default=None)):
    try:
        return get_scim_user(_scim_auth_context(authorization), user_id)
    except Exception as exc:
        _handle(exc)


@router.patch("/scim/v2/Users/{user_id}")
def scim_users_patch(user_id: str, payload: dict[str, Any], authorization: str | None = Header(default=None)):
    try:
        return patch_scim_user(_scim_auth_context(authorization), user_id, payload)
    except Exception as exc:
        _handle(exc)


@router.delete("/scim/v2/Users/{user_id}", status_code=204)
def scim_users_delete(user_id: str, authorization: str | None = Header(default=None)):
    try:
        deactivate_scim_user(_scim_auth_context(authorization), user_id)
        return None
    except Exception as exc:
        _handle(exc)


@router.get("/scim/v2/Groups")
def scim_groups_list(
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    try:
        return list_scim_groups(_scim_auth_context(authorization), start_index=startIndex, count=count)
    except Exception as exc:
        _handle(exc)


@router.post("/scim/v2/Groups", status_code=201)
def scim_groups_create(payload: dict[str, Any], authorization: str | None = Header(default=None)):
    try:
        return provision_scim_group(_scim_auth_context(authorization), payload)
    except Exception as exc:
        _handle(exc)


@router.get("/scim/v2/Groups/{group_id}")
def scim_groups_get(group_id: str, authorization: str | None = Header(default=None)):
    try:
        return get_scim_group(_scim_auth_context(authorization), group_id)
    except Exception as exc:
        _handle(exc)


@router.patch("/scim/v2/Groups/{group_id}")
def scim_groups_patch(group_id: str, payload: dict[str, Any], authorization: str | None = Header(default=None)):
    try:
        return patch_scim_group(_scim_auth_context(authorization), group_id, payload)
    except Exception as exc:
        _handle(exc)


@router.delete("/scim/v2/Groups/{group_id}", status_code=204)
def scim_groups_delete(group_id: str, authorization: str | None = Header(default=None)):
    try:
        delete_scim_group(_scim_auth_context(authorization), group_id)
        return None
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/entreprise/readiness")
def entreprise_workspace_readiness(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return entreprise_readiness(user["id"], workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/entreprise/private-ai")
def entreprise_private_ai(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return private_ai_posture(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/entreprise/private-ai/enforce")
def entreprise_private_ai_enforce(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return enforce_private_ai(user["id"], workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/metrics/internal", response_class=PlainTextResponse, include_in_schema=False)
def internal_prometheus_metrics(
    hours: int = Query(default=24, ge=1, le=720),
    x_datavision_metrics_token: str = Header(default="", alias="X-DataVision-Metrics-Token"),
    authorization: str | None = Header(default=None),
):
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    if not internal_metrics_token_valid(x_datavision_metrics_token or bearer):
        raise HTTPException(status_code=401, detail="Jeton de métriques interne invalide")
    return PlainTextResponse(prometheus_all_metrics(hours=hours), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/workspaces/{workspace_id}/metrics/prometheus", response_class=PlainTextResponse)
def workspace_prometheus_metrics(workspace_id: str, hours: int = Query(default=24, ge=1, le=720), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return PlainTextResponse(prometheus_metrics(workspace_id, hours=hours), media_type="text/plain; version=0.0.4; charset=utf-8")
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces")
def workspace_create(req: WorkspaceCreateRequest, user=Depends(current_user)):
    try:
        ws = create_workspace(user["id"], req.organization_id, req.name)
        record_event("workspace.create", user_id=user["id"], organization_id=req.organization_id, workspace_id=ws["id"], resource_type="workspace", resource_id=ws["id"], payload={"name": ws["name"]})
        return {"workspace": ws}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/identity/oidc")
def workspace_oidc_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"providers": list_oidc_providers(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/identity/oidc")
def workspace_oidc_create(workspace_id: str, req: OIDCProviderRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        item = create_oidc_provider(user["id"], workspace_id, **req.model_dump())
        record_event("identity.oidc_provider_create", user_id=user["id"], workspace_id=workspace_id, resource_type="oidc_provider", resource_id=item["id"], payload={"name": item["name"], "issuer": item["issuer"]})
        return {"provider": item}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/identity/oidc/{provider_id}")
def workspace_oidc_delete(workspace_id: str, provider_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        delete_oidc_provider(workspace_id, provider_id)
        record_event("identity.oidc_provider_disable", user_id=user["id"], workspace_id=workspace_id, resource_type="oidc_provider", resource_id=provider_id)
        return {"status": "disabled"}
    except Exception as exc:
        _handle(exc)



@router.get("/workspaces/{workspace_id}/plugins")
def workspace_plugins_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:read")
        return {"plugins": list_plugins(workspace_id), "runs": list_plugin_runs(workspace_id, limit=50)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/plugins")
def workspace_plugin_install(workspace_id: str, req: PluginInstallRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:manage")
        plugin = install_plugin(user["id"], workspace_id, req.model_dump())
        refresh_runtime_plugins()
        return {"plugin": plugin}
    except Exception as exc:
        _handle(exc)


@router.patch("/workspaces/{workspace_id}/plugins/{plugin_id}")
def workspace_plugin_update(workspace_id: str, plugin_id: str, req: PluginUpdateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:manage")
        plugin = update_plugin(user["id"], workspace_id, plugin_id, **req.model_dump(exclude_none=True))
        refresh_runtime_plugins()
        return {"plugin": plugin}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/plugins/{plugin_id}")
def workspace_plugin_delete(workspace_id: str, plugin_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:manage")
        result = delete_plugin(user["id"], workspace_id, plugin_id)
        refresh_runtime_plugins()
        return result
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/plugins/{plugin_id}/test")
def workspace_plugin_test(workspace_id: str, plugin_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:manage")
        result = test_plugin(workspace_id, plugin_id)
        record_event(
            "plugin.test", user_id=user["id"], workspace_id=workspace_id,
            resource_type="plugin", resource_id=plugin_id,
            outcome="success" if result.get("ok") else "failed",
            payload={"ok": bool(result.get("ok")), "status": result.get("status")},
        )
        return result
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/plugins/{plugin_id}/sync")
def workspace_plugin_sync(workspace_id: str, plugin_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:manage")
        plugin = sync_plugin(user["id"], workspace_id, plugin_id)
        refresh_runtime_plugins()
        return {"plugin": plugin}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/plugins/{plugin_id}")
def workspace_plugin_detail(workspace_id: str, plugin_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "plugins:read")
        return {
            "plugin": get_plugin(workspace_id, plugin_id),
            "runs": list_plugin_runs(workspace_id, plugin_id=plugin_id, limit=100),
        }
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/secrets")
def workspace_secrets_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"secrets": list_secrets(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/secrets")
def workspace_secret_create(workspace_id: str, req: SecretCreateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        item = create_secret(user["id"], workspace_id, **req.model_dump())
        record_event("secret.create", user_id=user["id"], workspace_id=workspace_id, resource_type="secret", resource_id=item["id"], payload={"name": item["name"], "provider": item["provider"]})
        return {"secret": item}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/secrets/{secret_id}/rotate")
def workspace_secret_rotate(workspace_id: str, secret_id: str, req: SecretRotateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        item = rotate_secret(user["id"], workspace_id, secret_id, value=req.value)
        record_event("secret.rotate", user_id=user["id"], workspace_id=workspace_id, resource_type="secret", resource_id=secret_id, payload={"version": item.get("current_version")})
        return {"secret": item}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/secrets/{secret_id}/test")
def workspace_secret_test(workspace_id: str, secret_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        result = test_secret(workspace_id, secret_id)
        record_event("secret.test", user_id=user["id"], workspace_id=workspace_id, resource_type="secret", resource_id=secret_id, payload={"ok": result.get("ok")})
        return result
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/secrets/rotation/status")
def workspace_secret_rotation_status(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return secret_rotation_status(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/secrets/rotation/events")
def workspace_secret_rotation_events(workspace_id: str, limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return {"events": list_secret_rotation_events(workspace_id, limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/secrets/rotation/run")
def workspace_secret_rotation_run(workspace_id: str, req: SecretAutoRotateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return rotate_due_secrets(user["id"], workspace_id=workspace_id, confirm=req.confirm)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id: str, user=Depends(current_user)):
    try:
        return {"workspace": get_workspace(user["id"], workspace_id), "members": list_members(user["id"], workspace_id), "datasets": list_workspace_datasets(user["id"], workspace_id), "policies": list_policies(user["id"], workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/members")
def workspace_member(workspace_id: str, req: MemberRequest, user=Depends(current_user)):
    try:
        member = upsert_member(user["id"], workspace_id, req.email, req.role, display_name=req.display_name, password=req.password)
        ws = get_workspace(user["id"], workspace_id)
        record_event("workspace.member.upsert", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="user", resource_id=member["id"], payload={"role": req.role})
        return {"member": member}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/datasets")
def workspace_dataset(workspace_id: str, req: BindDatasetRequest, user=Depends(current_user)):
    try:
        bound = bind_dataset(user["id"], workspace_id, req.dataset_id)
        ws = get_workspace(user["id"], workspace_id)
        record_event("workspace.dataset.bind", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="dataset", resource_id=req.dataset_id)
        return bound
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/policies")
def workspace_policies(workspace_id: str, user=Depends(current_user)):
    try:
        return {"policies": list_policies(user["id"], workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/policies")
def workspace_policy_save(workspace_id: str, req: PolicyRequest, user=Depends(current_user)):
    try:
        policy = save_access_policy(user["id"], workspace_id, req.dataset_id, req.name, req.allowed_columns, req.row_filters, req.applies_to_role, req.policy_id)
        ws = get_workspace(user["id"], workspace_id)
        record_event("workspace.policy.save", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="access_policy", resource_id=policy["id"], payload={"dataset_id": req.dataset_id, "role": req.applies_to_role})
        return {"policy": policy}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/datasets/{dataset_id}/governed-preview")
def governed_dataset_preview(workspace_id: str, dataset_id: str, limit: int = Query(default=50, ge=1, le=500), simulate_role: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "dataset:read")
        if simulate_role:
            if simulate_role not in {"owner","admin","data_scientist","analyst","viewer"}:
                raise ValueError("Rôle de simulation invalide")
            _workspace_permission(user["id"], workspace_id, "policies:manage")
        linked = fetch_one("SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws AND dataset_id=:ds", {"ws":workspace_id,"ds":dataset_id})
        if not linked:
            raise KeyError("Dataset non lié à ce workspace")
        from app.services.storage import load_dataframe
        df = load_dataframe(dataset_id)
        effective_role = simulate_role or workspace_role(user["id"], workspace_id)
        policies = policies_for_access(user["id"], workspace_id, dataset_id, role_override=simulate_role)
        governed, applied = apply_access_policies(df, policies)
        rows = governed.head(limit).where(governed.head(limit).notna(), None).to_dict(orient="records")
        record_event("dataset.governed_preview", user_id=user["id"], workspace_id=workspace_id, resource_type="dataset", resource_id=dataset_id, payload={"rows_before":len(df),"rows_after":len(governed),"policies":len(policies),"effective_role":effective_role})
        return {"columns":[str(c) for c in governed.columns],"rows":rows,"returned_rows":len(rows),"total_rows":len(governed),"policies":policies,"applied":applied,"effective_role":effective_role}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/governance/control-plane")
def governance_control_plane(workspace_id: str, dataset_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "audit:read")
        return control_plane_overview(user["id"], workspace_id, dataset_id)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/governance/snapshots")
def governance_snapshot_capture(workspace_id: str, req: BindDatasetRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "audit:read")
        dataset_id = req.dataset_id or None
        return {"snapshot": capture_governance_snapshot(user["id"], workspace_id, dataset_id)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/governance/snapshots")
def governance_snapshots(workspace_id: str, limit: int = Query(default=30, ge=1, le=200), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "audit:read")
        return {"snapshots": list_governance_snapshots(user["id"], workspace_id, limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/audit")
def audit_list(workspace_id: str | None = Query(default=None), organization_id: str | None = Query(default=None), limit: int = Query(default=200, ge=1, le=1000), user=Depends(current_user)):
    if workspace_id:
        _workspace_permission(user["id"], workspace_id, "audit:read")
    elif organization_id:
        member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org":organization_id,"user":user["id"]})
        if not member or member["role"] not in {"owner","admin"}:
            raise HTTPException(status_code=403, detail="Permission audit organisation insuffisante")
    else:
        raise HTTPException(status_code=400, detail="workspace_id ou organization_id requis")
    return {"events": list_events(organization_id=organization_id, workspace_id=workspace_id, limit=limit)}


@router.post("/jobs")
def jobs_submit(req: JobSubmitRequest, user=Depends(current_user)):
    try:
        if req.job_type == "action_delivery":
            raise PermissionError("action_delivery est un job interne et ne peut pas être soumis directement.")
        if req.workspace_id:
            perm = "model:run" if req.job_type == "automl" else "analysis:run"
            _workspace_permission(user["id"], req.workspace_id, perm)
        job = submit_job(user_id=user["id"], organization_id=req.organization_id, workspace_id=req.workspace_id, job_type=req.job_type, dataset_id=req.dataset_id, payload=req.payload, max_retries=req.max_retries, retry_backoff_seconds=req.retry_backoff_seconds)
        record_event("job.submit", user_id=user["id"], organization_id=req.organization_id, workspace_id=req.workspace_id, resource_type="job", resource_id=job["id"], payload={"job_type": req.job_type, "dataset_id": req.dataset_id})
        return {"job": job}
    except Exception as exc:
        _handle(exc)


@router.get("/jobs")
def jobs_list(workspace_id: str | None = Query(default=None), user=Depends(current_user)):
    if workspace_id and not workspace_role(user["id"], workspace_id):
        raise HTTPException(status_code=403, detail="Accès au workspace refusé")
    return {"jobs": list_jobs(user["id"], workspace_id)}


@router.get("/jobs/{job_id}")
def jobs_detail(job_id: str, user=Depends(current_user)):
    try:
        job = get_job(job_id)
        if job["user_id"] != user["id"] and (not job.get("workspace_id") or not has_permission(user["id"], job["workspace_id"], "jobs:manage")):
            raise PermissionError("Accès au job refusé")
        return {"job": job}
    except Exception as exc:
        _handle(exc)


@router.post("/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str, user=Depends(current_user)):
    try:
        job = request_cancel(job_id, user["id"])
        record_event("job.cancel", user_id=user["id"], organization_id=job.get("organization_id"), workspace_id=job.get("workspace_id"), resource_type="job", resource_id=job_id)
        return {"job": job}
    except Exception as exc:
        _handle(exc)


@router.get("/jobs/{job_id}/attempts")
def jobs_attempts(job_id: str, user=Depends(current_user)):
    try:
        job = get_job(job_id)
        if job["user_id"] != user["id"] and (not job.get("workspace_id") or not has_permission(user["id"], job["workspace_id"], "jobs:manage")):
            raise PermissionError("Accès au job refusé")
        return {"attempts": job_attempts(job_id)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/overview")
def operational_workspace_overview(workspace_id: str, hours: int = Query(default=24, ge=1, le=2160), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return operational_overview(workspace_id, hours=hours)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/traces/{trace_id}")
def operational_trace_detail(workspace_id: str, trace_id: str, hours: int = Query(default=24, ge=1, le=720), limit: int = Query(default=200, ge=1, le=1000), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"trace_id": trace_id, "events": list_trace_events(workspace_id, trace_id, hours=hours, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/sre")
def operational_sre_status(workspace_id: str, hours: int = Query(default=24, ge=1, le=720), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return sre_status(workspace_id, hours=hours)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/sre/snapshot")
def operational_sre_snapshot(workspace_id: str, hours: int = Query(default=24, ge=1, le=720), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        return capture_sre_snapshot(workspace_id, hours=hours)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/sre/emit")
def operational_sre_emit(workspace_id: str, hours: int = Query(default=24, ge=1, le=720), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        result = emit_sre_alerts(user["id"], workspace_id, hours=hours)
        record_event("sre.alerts.evaluate", user_id=user["id"], workspace_id=workspace_id, resource_type="workspace", resource_id=workspace_id, payload={"alerts": len(result.get("alerts") or []), "status": result.get("status")})
        return result
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/sre/snapshots")
def operational_sre_snapshots(workspace_id: str, limit: int = Query(default=50, ge=1, le=200), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"snapshots": list_sre_snapshots(workspace_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/sre/routes")
def operational_sre_routes(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"routes": list_sre_alert_routes(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.put("/workspaces/{workspace_id}/operational/sre/routes")
def operational_sre_route_save(workspace_id: str, req: SREAlertRouteRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        route = save_sre_alert_route(
            workspace_id,
            route_id=req.route_id,
            name=req.name,
            min_severity=req.min_severity,
            event_type=req.event_type,
            enabled=req.enabled,
            codes=req.codes,
        )
        record_event("sre.alert_route.save", user_id=user["id"], workspace_id=workspace_id, resource_type="sre_alert_route", resource_id=route["id"], payload={"min_severity": route["min_severity"], "event_type": route["event_type"]})
        return {"route": route}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/operational/sre/routes/{route_id}")
def operational_sre_route_delete(workspace_id: str, route_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        deleted = delete_sre_alert_route(workspace_id, route_id)
        if not deleted:
            raise KeyError("Route SRE introuvable")
        record_event("sre.alert_route.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="sre_alert_route", resource_id=route_id)
        return {"deleted": True}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/dr-drills")
def operational_dr_drill_run(workspace_id: str, req: DRDrillRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": workspace_id}) or {}
        result = run_dr_drill(user["id"], workspace_id, organization_id=ws.get("organization_id"), mode=req.mode)
        record_event("sre.dr_drill", user_id=user["id"], workspace_id=workspace_id, resource_type="dr_drill", resource_id=result["id"], payload={"mode": req.mode, "status": result["status"]})
        return {"drill": result}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/dr-drills")
def operational_dr_drill_list(workspace_id: str, limit: int = Query(default=25, ge=1, le=100), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"drills": list_dr_drills(workspace_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/replications")
def operational_replications(workspace_id: str, backup_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"replications": list_backup_replications(backup_id=backup_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/replications/{backup_id}/verify")
def operational_replications_verify(workspace_id: str, backup_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        result = verify_backup_replications(backup_id)
        record_event("sre.replication.verify", user_id=user["id"], workspace_id=workspace_id, resource_type="backup", resource_id=backup_id, payload={"status": result.get("status"), "targets": len(result.get("results") or [])})
        return result
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/clusters")
def operational_cluster_topology(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return cluster_topology_status(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/failovers")
def operational_failovers(workspace_id: str, limit: int = Query(default=50, ge=1, le=200), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"failovers": list_failovers(workspace_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/failovers/plan")
def operational_failover_plan(workspace_id: str, req: FailoverPlanRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        result = create_failover_plan(user["id"], workspace_id, target_cluster_id=req.target_cluster_id, reason=req.reason)
        record_event("sre.failover.plan", user_id=user["id"], workspace_id=workspace_id, resource_type="cluster_failover", resource_id=result["id"], payload={"source": result.get("source_cluster_id"), "target": result.get("target_cluster_id"), "expires_at": result.get("expires_at")})
        return {"plan": result}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/failovers/{plan_id}/confirm")
def operational_failover_confirm(workspace_id: str, plan_id: str, req: FailoverConfirmRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        result = confirm_failover(user["id"], workspace_id, plan_id=plan_id, confirmation_token=req.confirmation_token)
        record_event("sre.failover.confirm", user_id=user["id"], workspace_id=workspace_id, resource_type="cluster_failover", resource_id=plan_id, payload={"source": result.get("source_cluster_id"), "target": result.get("target_cluster_id"), "executor": result.get("executor"), "traffic_switched": result.get("traffic_switched")})
        return {"failover": result}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/operational/chaos")
def operational_chaos_run(workspace_id: str, req: ChaosDrillRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "workspace:manage")
        ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": workspace_id}) or {}
        result = run_chaos_drill(user["id"], workspace_id, scenario=req.scenario, intensity=req.intensity, organization_id=ws.get("organization_id"))
        record_event("sre.chaos_drill", user_id=user["id"], workspace_id=workspace_id, resource_type="chaos_drill", resource_id=result["id"], payload={"scenario": req.scenario, "intensity": req.intensity})
        return {"drill": result}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/chaos")
def operational_chaos_list(workspace_id: str, limit: int = Query(default=25, ge=1, le=100), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"drills": list_chaos_drills(workspace_id, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/usage")
def operational_usage(workspace_id: str, hours: int = Query(default=720, ge=1, le=2160), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return feature_usage(workspace_id, hours=hours)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/operational/telemetry")
def operational_telemetry(workspace_id: str, hours: int = Query(default=24, ge=1, le=2160), event_kind: str | None = Query(default=None), limit: int = Query(default=200, ge=1, le=1000), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"events": list_telemetry(workspace_id, hours=hours, limit=limit, event_kind=event_kind)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/evaluations/suites")
def evaluations_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"suites": list_evaluation_suites(workspace_id), "runs": list_evaluation_runs(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/evaluations/suites")
def evaluations_create(workspace_id: str, req: EvaluationSuiteRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "evaluation:manage")
        from app.services.tenant_access import context_for_job, authorize_dataset
        ctx = context_for_job(user["id"], workspace_id)
        if ctx: authorize_dataset(req.dataset_id, "analysis:run", ctx)
        suite = create_evaluation_suite(user["id"], workspace_id, req.dataset_id, req.name, req.description)
        record_event("evaluation.suite.create", user_id=user["id"], workspace_id=workspace_id, resource_type="evaluation_suite", resource_id=suite["id"], payload={"dataset_id":req.dataset_id})
        return {"suite": suite}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/evaluations/suites/{suite_id}")
def evaluations_detail(workspace_id: str, suite_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"suite": get_evaluation_suite(workspace_id, suite_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/evaluations/suites/{suite_id}/cases")
def evaluations_add_case(workspace_id: str, suite_id: str, req: EvaluationCaseRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "evaluation:manage")
        case = add_evaluation_case(user["id"], workspace_id, suite_id, req.question, req.expectations)
        record_event("evaluation.case.create", user_id=user["id"], workspace_id=workspace_id, resource_type="evaluation_case", resource_id=case["id"], payload={"suite_id":suite_id})
        return {"case": case}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/evaluations/suites/{suite_id}/run")
def evaluations_run(workspace_id: str, suite_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "evaluation:manage")
        result = run_evaluation_suite(user["id"], workspace_id, suite_id)
        record_event("evaluation.run", user_id=user["id"], workspace_id=workspace_id, resource_type="evaluation_run", resource_id=result["id"], outcome=result["status"], payload={"suite_id":suite_id,"score":result["score"]})
        return {"run": result}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/evaluations/runs/{run_id}")
def evaluations_run_detail(workspace_id: str, run_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "observability:read")
        return {"run": get_evaluation_run(workspace_id, run_id)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews/summary")
def reviews_summary(workspace_id: str, user=Depends(current_user)):
    try:
        return review_summary(user["id"], workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews")
def reviews_list(workspace_id: str, status: str | None = Query(default=None), scope: str = Query(default="all"), limit: int = Query(default=200, ge=1, le=500), user=Depends(current_user)):
    try:
        return {"reviews": list_reviews(user["id"], workspace_id, status=status, scope=scope, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews")
def reviews_create(workspace_id: str, req: ReviewCreateRequest, user=Depends(current_user)):
    try:
        review = create_review(
            user["id"], workspace_id, resource_type=req.resource_type, resource_id=req.resource_id, title=req.title,
            description=req.description, dataset_id=req.dataset_id, resource_version=req.resource_version, priority=req.priority,
            owner_user_id=req.owner_user_id, reviewer_user_id=req.reviewer_user_id, due_at=req.due_at, snapshot=req.snapshot,
        )
        ws = get_workspace(user["id"], workspace_id)
        record_event("review.create", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="review", resource_id=review["id"], payload={"resource_type":req.resource_type,"resource_id":req.resource_id})
        if req.reviewer_user_id:
            try:
                dispatch_event(user["id"], workspace_id, event_type="review_assigned", event_id=review["id"], dataset_id=review.get("dataset_id"), payload={"review_id":review["id"],"title":review.get("title"),"reviewer_user_id":req.reviewer_user_id})
            except Exception:
                pass
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews/{review_id}")
def reviews_detail(workspace_id: str, review_id: str, user=Depends(current_user)):
    try:
        return {"review": get_review(user["id"], workspace_id, review_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/assign")
def reviews_assign(workspace_id: str, review_id: str, req: ReviewAssignRequest, user=Depends(current_user)):
    try:
        review = assign_review(user["id"], workspace_id, review_id, owner_user_id=req.owner_user_id, reviewer_user_id=req.reviewer_user_id, due_at=req.due_at, priority=req.priority)
        record_event("review.assign", user_id=user["id"], workspace_id=workspace_id, resource_type="review", resource_id=review_id, payload={"reviewer_user_id":req.reviewer_user_id,"owner_user_id":req.owner_user_id})
        if req.reviewer_user_id:
            try:
                dispatch_event(user["id"], workspace_id, event_type="review_assigned", event_id=review_id, dataset_id=review.get("dataset_id"), payload={"review_id":review_id,"title":review.get("title"),"reviewer_user_id":req.reviewer_user_id})
            except Exception:
                pass
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/transition")
def reviews_transition(workspace_id: str, review_id: str, req: ReviewTransitionRequest, user=Depends(current_user)):
    try:
        review = transition_review(user["id"], workspace_id, review_id, req.action, req.note)
        record_event(f"review.{req.action}", user_id=user["id"], workspace_id=workspace_id, resource_type="review", resource_id=review_id, payload={"status":review["status"]})
        event_type = {"approve":"review_approved","submit":"review_submitted","request_changes":"review_changes_requested"}.get(req.action)
        if event_type:
            try:
                dispatch_event(user["id"], workspace_id, event_type=event_type, event_id=review_id, dataset_id=review.get("dataset_id"), payload={"review_id":review_id,"title":review.get("title"),"resource_type":review.get("resource_type"),"resource_id":review.get("resource_id"),"priority":review.get("priority"),"status":review.get("status"),"note":req.note})
            except Exception:
                pass
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/comments")
def reviews_comment(workspace_id: str, review_id: str, req: ReviewCommentRequest, user=Depends(current_user)):
    try:
        review = add_comment(user["id"], workspace_id, review_id, req.body, req.mention_user_ids)
        record_event("review.comment", user_id=user["id"], workspace_id=workspace_id, resource_type="review", resource_id=review_id)
        try:
            dispatch_event(user["id"], workspace_id, event_type="review_comment", event_id=str((review.get("comments") or [{}])[-1].get("id") or review_id), dataset_id=review.get("dataset_id"), payload={"review_id":review_id,"title":review.get("title"),"comment":req.body[:500]})
            mentions = (review.get("comments") or [{}])[-1].get("mentions") or []
            if mentions:
                dispatch_event(user["id"], workspace_id, event_type="review_mention", event_id=str((review.get("comments") or [{}])[-1].get("id") or review_id), dataset_id=review.get("dataset_id"), payload={"review_id":review_id,"title":review.get("title"),"mention_user_ids":mentions})
        except Exception:
            pass
        return {"review": review}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/comments/{comment_id}/resolve")
def reviews_comment_resolve(workspace_id: str, review_id: str, comment_id: str, req: ReviewCommentResolveRequest, user=Depends(current_user)):
    try:
        return {"review": resolve_comment(user["id"], workspace_id, review_id, comment_id, req.resolved)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/collaboration/notifications")
def collaboration_notifications(workspace_id: str, limit: int = Query(default=100, ge=1, le=300), user=Depends(current_user)):
    try:
        return {"notifications": list_notifications(user["id"], workspace_id, limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/notifications/{notification_id}/read")
def collaboration_notification_read(workspace_id: str, notification_id: str, user=Depends(current_user)):
    try:
        return {"notification": mark_notification_read(user["id"], workspace_id, notification_id)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/collaboration/activity")
def collaboration_activity_feed(workspace_id: str, since: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=300), user=Depends(current_user)):
    try:
        return collaboration_activity(user["id"], workspace_id, since=since, limit=limit)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/collaboration/decisions")
def collaboration_decisions(workspace_id: str, limit: int = Query(default=200, ge=1, le=500), user=Depends(current_user)):
    try:
        return {"decisions": decision_ledger(user["id"], workspace_id, limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/collaboration/teams")
def collaboration_teams(workspace_id: str, user=Depends(current_user)):
    try:
        return {"teams": list_teams(user["id"], workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/teams")
def collaboration_team_create(workspace_id: str, req: CollaborationTeamCreateRequest, user=Depends(current_user)):
    try:
        team = create_team(user["id"], workspace_id, name=req.name, description=req.description, member_user_ids=req.member_user_ids)
        record_event("collaboration.team.create", user_id=user["id"], workspace_id=workspace_id, resource_type="team", resource_id=team["id"], payload={"name": team["name"]})
        return {"team": team}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/teams/{team_id}/members/{member_user_id}")
def collaboration_team_member_add(workspace_id: str, team_id: str, member_user_id: str, user=Depends(current_user)):
    try:
        return {"team": set_team_member(user["id"], workspace_id, team_id, member_user_id, present=True)}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/collaboration/teams/{team_id}/members/{member_user_id}")
def collaboration_team_member_remove(workspace_id: str, team_id: str, member_user_id: str, user=Depends(current_user)):
    try:
        return {"team": set_team_member(user["id"], workspace_id, team_id, member_user_id, present=False)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/collaboration/shares")
def collaboration_shares(workspace_id: str, scope: str = Query(default="received"), limit: int = Query(default=200, ge=1, le=500), user=Depends(current_user)):
    try:
        return {"shares": list_artifact_shares(user["id"], workspace_id, scope=scope, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/shares")
def collaboration_share_create(workspace_id: str, req: CollaborationShareRequest, user=Depends(current_user)):
    try:
        share = create_artifact_share(user["id"], workspace_id, **req.model_dump())
        record_event("collaboration.share.create", user_id=user["id"], workspace_id=workspace_id, resource_type=req.resource_type, resource_id=req.resource_id, payload={"share_id": share["id"], "permission": req.permission})
        try:
            dispatch_event(user["id"], workspace_id, event_type="artifact_shared", event_id=share["id"], payload={"share_id":share["id"],"resource_type":req.resource_type,"resource_id":req.resource_id,"permission":req.permission})
        except Exception:
            pass
        return {"share": share}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/shares/{share_id}/revoke")
def collaboration_share_revoke(workspace_id: str, share_id: str, user=Depends(current_user)):
    try:
        return {"share": revoke_artifact_share(user["id"], workspace_id, share_id)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/reviews/{review_id}/diff")
def collaboration_review_diff(workspace_id: str, review_id: str, against_review_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        return {"diff": review_snapshot_diff(user["id"], workspace_id, review_id, against_review_id=against_review_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/notifications/read-all")
def collaboration_notifications_read_all(workspace_id: str, user=Depends(current_user)):
    try:
        return {"marked_read": mark_all_notifications_read(user["id"], workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/collaboration/ws-ticket")
def collaboration_ws_ticket(workspace_id: str, user=Depends(current_user)):
    try:
        return create_realtime_ticket(user["id"], workspace_id)
    except Exception as exc:
        _handle(exc)


@router.websocket("/workspaces/{workspace_id}/collaboration/ws")
async def collaboration_websocket(websocket: WebSocket, workspace_id: str):
    ticket = str(websocket.query_params.get("ticket") or "")
    try:
        ticket_row = consume_realtime_ticket(ticket, workspace_id)
        user = get_user(ticket_row["user_id"])
        if not user or not user.get("is_active"):
            raise PermissionError("Compte inactif.")
    except Exception:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    cursor = str(websocket.query_params.get("cursor") or "") or None
    heartbeat = 0
    try:
        initial = collaboration_activity(user["id"], workspace_id, since=cursor, limit=100)
        cursor = initial.get("cursor") or cursor
        await websocket.send_json({"type":"collaboration.snapshot", **initial})
        while True:
            await asyncio.sleep(1.25)
            update = collaboration_activity(user["id"], workspace_id, since=cursor, limit=100)
            if update.get("items"):
                cursor = update.get("cursor") or cursor
                heartbeat = 0
                await websocket.send_json({"type":"collaboration.activity", **update})
            else:
                heartbeat += 1
                if heartbeat >= 12:
                    heartbeat = 0
                    await websocket.send_json({"type":"collaboration.heartbeat", "cursor": cursor, "summary": update.get("summary")})
    except (WebSocketDisconnect, RuntimeError):
        return


@router.get("/workspaces/{workspace_id}/certifications")
def certifications_list(workspace_id: str, status: str = Query(default="active"), user=Depends(current_user)):
    try:
        return {"certifications": list_certifications(user["id"], workspace_id, status=status)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/reviews/{review_id}/certify")
def reviews_certify(workspace_id: str, review_id: str, req: CertificationRequest, user=Depends(current_user)):
    try:
        cert = certify_review(user["id"], workspace_id, review_id, valid_until=req.valid_until, notes=req.notes)
        record_event("review.certify", user_id=user["id"], workspace_id=workspace_id, resource_type="certification", resource_id=cert["id"], payload={"review_id":review_id,"valid_until":req.valid_until})
        try:
            dispatch_event(user["id"], workspace_id, event_type="certification_created", event_id=cert["id"], dataset_id=cert.get("dataset_id"), payload={"certification_id":cert["id"],"review_id":review_id,"resource_type":cert.get("resource_type"),"resource_id":cert.get("resource_id"),"valid_until":cert.get("valid_until"),"status":cert.get("status")})
        except Exception:
            pass
        return {"certification": cert}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/certifications/{certification_id}/revoke")
def certifications_revoke(workspace_id: str, certification_id: str, req: CertificationRevokeRequest, user=Depends(current_user)):
    try:
        return {"certification": revoke_certification(user["id"], workspace_id, certification_id, req.note)}
    except Exception as exc:
        _handle(exc)


def _connector_catalog_for_user(user_id: str, workspace_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connectors = list_connectors(workspace_id)
    sources = list_sources(workspace_id)
    if has_permission(user_id, workspace_id, "connectors:manage"):
        return connectors, sources
    safe_connectors = []
    for c in connectors:
        safe_connectors.append({k:v for k,v in c.items() if k in {"id","workspace_id","name","connector_type","status","last_tested_at","last_error","ssl_mode","created_at","updated_at"}})
    safe_sources = []
    for src in sources:
        safe = dict(src)
        safe.pop("source_query", None)
        safe.pop("schema", None)
        safe_sources.append(safe)
    return safe_connectors, safe_sources


# ---------------------------- Connecteurs d’actions Entreprise v2.11 ----------------------------

@router.get("/workspaces/{workspace_id}/actions/summary")
def actions_summary(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:read")
        return action_summary(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/actions/destinations")
def actions_destinations_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:read")
        return {"destinations": list_destinations(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/destinations")
def actions_destinations_create(workspace_id: str, req: ActionDestinationRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:manage")
        dest = create_destination(user["id"], workspace_id, **req.model_dump())
        record_event("action.destination.create", user_id=user["id"], workspace_id=workspace_id, resource_type="action_destination", resource_id=dest["id"], payload={"name":req.name})
        return {"destination": dest}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/destinations/{destination_id}/test")
def actions_destination_test(workspace_id: str, destination_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:manage")
        out = test_destination_delivery(workspace_id, destination_id, user["id"])
        record_event("action.destination.test", user_id=user["id"], workspace_id=workspace_id, resource_type="action_destination", resource_id=destination_id, payload={"ok":out.get("ok"),"kind":out.get("kind")})
        return out
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/actions/destinations/{destination_id}")
def actions_destinations_delete(workspace_id: str, destination_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:manage")
        delete_destination(workspace_id, destination_id)
        record_event("action.destination.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="action_destination", resource_id=destination_id)
        return {"deleted": True, "destination_id": destination_id}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/actions/rules")
def actions_rules_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:read")
        return {"rules": list_action_rules(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/rules")
def actions_rules_save(workspace_id: str, req: ActionRuleRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:manage")
        rule = save_action_rule(user["id"], workspace_id, **req.model_dump())
        record_event("action.rule.save", user_id=user["id"], workspace_id=workspace_id, resource_type="action_rule", resource_id=rule["id"], payload={"event_type":rule["event_type"],"approval_mode":rule["approval_mode"]})
        return {"rule": rule}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/actions/rules/{rule_id}")
def actions_rules_delete(workspace_id: str, rule_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:manage")
        delete_rule(workspace_id, rule_id)
        record_event("action.rule.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="action_rule", resource_id=rule_id)
        return {"deleted": True, "rule_id": rule_id}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/events")
def actions_events_dispatch(workspace_id: str, req: ActionEventRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:trigger")
        out = dispatch_event(user["id"], workspace_id, event_type=req.event_type, event_id=req.event_id, payload=req.payload, dataset_id=req.dataset_id, enqueue=True)
        record_event("action.event.dispatch", user_id=user["id"], workspace_id=workspace_id, resource_type="action_event", resource_id=out["event_id"], payload={"event_type":req.event_type,"matched_rules":out["matched_rules"]})
        return out
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/actions/runs")
def actions_runs_list(workspace_id: str, status: str | None = Query(default=None), limit: int = Query(default=200, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:read")
        return {"runs": list_action_runs(workspace_id, status=status, limit=limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/actions/runs/{run_id}")
def actions_run_detail(workspace_id: str, run_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:read")
        return {"run": get_action_run(workspace_id, run_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/runs/{run_id}/approve")
def actions_run_approve(workspace_id: str, run_id: str, req: ActionDecisionRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:approve")
        run = approve_run(user["id"], workspace_id, run_id, req.note)
        record_event("action.run.approve", user_id=user["id"], workspace_id=workspace_id, resource_type="action_run", resource_id=run_id, payload={"status":run["status"]})
        return {"run": run}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/runs/{run_id}/reject")
def actions_run_reject(workspace_id: str, run_id: str, req: ActionDecisionRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:approve")
        run = reject_run(user["id"], workspace_id, run_id, req.note)
        record_event("action.run.reject", user_id=user["id"], workspace_id=workspace_id, resource_type="action_run", resource_id=run_id)
        return {"run": run}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/actions/runs/{run_id}/replay")
def actions_run_replay(workspace_id: str, run_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "actions:approve")
        run = replay_run(user["id"], workspace_id, run_id)
        record_event("action.run.replay", user_id=user["id"], workspace_id=workspace_id, resource_type="action_run", resource_id=run["id"], payload={"replay_of":run_id})
        return {"run": run}
    except Exception as exc:
        _handle(exc)


# ---------------------------- Data connectors & refresh v2.7 ----------------------------


@router.get("/workspaces/{workspace_id}/connectors/catalog")
def connectors_catalog_endpoint(
    workspace_id: str,
    user=Depends(current_user),
):
    try:
        _workspace_permission(
            user["id"],
            workspace_id,
            "connectors:read",
        )
        return connectors_catalog()
    except Exception as exc:
        _raise_api(exc)


@router.get("/workspaces/{workspace_id}/connectors/health")
def connectors_health(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        return workspace_refresh_health(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/connectors")
def connectors_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        connectors, sources = _connector_catalog_for_user(user["id"], workspace_id)
        return {"connectors": connectors, "sources": sources, "schedules": list_schedules(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/connectors")
def connectors_create(workspace_id: str, req: ConnectorCreateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        connector = create_connector(user["id"], workspace_id, name=req.name, connector_type=req.connector_type, host=req.host, port=req.port, database=req.database, username=req.username, password=req.password, ssl_mode=req.ssl_mode, options=req.options)
        record_event("connector.create", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector["id"], payload={"type":req.connector_type,"host":req.host,"database":req.database})
        return {"connector": connector}
    except Exception as exc:
        _handle(exc)


@router.patch("/workspaces/{workspace_id}/connectors/{connector_id}")
def connectors_update(workspace_id: str, connector_id: str, req: ConnectorUpdateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        connector = update_connector(user["id"], workspace_id, connector_id, **req.model_dump())
        record_event("connector.update", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector_id)
        return {"connector": connector}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/connectors/{connector_id}")
def connectors_delete(workspace_id: str, connector_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        delete_connector(workspace_id, connector_id)
        record_event("connector.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector_id)
        return {"deleted": True, "connector_id": connector_id}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/connectors/{connector_id}/test")
def connectors_test(workspace_id: str, connector_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        result = test_connector(workspace_id, connector_id)
        record_event("connector.test", user_id=user["id"], workspace_id=workspace_id, resource_type="connector", resource_id=connector_id, outcome="success" if result.get("ok") else "failed", payload={"status":result.get("status")})
        return result
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/connectors/{connector_id}/discover")
def connectors_discover(workspace_id: str, connector_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        return discover_connector(workspace_id, connector_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/sources")
def connector_sources_list(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        _, sources = _connector_catalog_for_user(user["id"], workspace_id)
        return {"sources": sources, "health": workspace_refresh_health(workspace_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources")
def connector_sources_create(workspace_id: str, req: ConnectorSourceCreateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        source = create_source(user["id"], workspace_id, connector_id=req.connector_id, name=req.name, source_kind=req.source_kind, table_name=req.table_name, query=req.query, refresh_mode=req.refresh_mode, incremental_column=req.incremental_column, freshness_sla_minutes=req.freshness_sla_minutes, schema_drift_policy=req.schema_drift_policy, source_options=req.source_options)
        record_event("connector.source.create", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source["id"], payload={"connector_id":req.connector_id,"mode":req.refresh_mode})
        return {"source": source}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/sources/{source_id}")
def connector_sources_delete(workspace_id: str, source_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        delete_source(workspace_id, source_id)
        record_event("connector.source.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id)
        return {"deleted": True, "source_id": source_id}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/sources/{source_id}/preview")
def connector_source_preview(workspace_id: str, source_id: str, limit: int = Query(default=50, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        return preview_source(workspace_id, source_id, limit)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources/{source_id}/refresh")
def connector_source_refresh(workspace_id: str, source_id: str, req: ConnectorRefreshRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "refresh:run")
        source = get_source(workspace_id, source_id)
        if req.background:
            ws = get_workspace(user["id"], workspace_id)
            job = submit_job(user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, job_type="connector_refresh", dataset_id=source.get("dataset_id"), payload={"source_id":source_id,"trigger":"manual"})
            record_event("connector.refresh.queued", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id, payload={"job_id":job["id"]})
            return {"queued": True, "job": job}
        result = refresh_source(workspace_id, source_id, actor_id=user["id"], trigger="manual")
        record_event("connector.refresh.completed", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id, payload={"dataset_id":result.get("dataset_id"),"rows":result.get("rows_fetched")})
        return {"queued": False, "refresh": result}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/sources/{source_id}/cdc")
def connector_source_cdc_status(workspace_id: str, source_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        return cdc_status(workspace_id, source_id)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources/{source_id}/cdc/events")
def connector_source_cdc_ingest(workspace_id: str, source_id: str, req: CDCIngestRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "refresh:run")
        result = ingest_cdc_events(workspace_id, source_id, actor_id=user["id"], events=req.events, event_format=req.event_format, dry_run=req.dry_run)
        record_event(
            "connector.cdc.ingest",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="connector_source",
            resource_id=source_id,
            outcome="preview" if req.dry_run else "success",
            payload={
                "batch_id": result.get("batch_id"),
                "events_received": result.get("events_received"),
                "events_applied": result.get("events_applied"),
                "duplicates": result.get("duplicates"),
                "stale_events": result.get("stale_events"),
                "dataset_id": result.get("dataset_id"),
            },
        )
        return result
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/sources/{source_id}/schedule")
def connector_source_schedule(workspace_id: str, source_id: str, req: RefreshScheduleRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:manage")
        schedule = save_schedule(workspace_id, source_id, enabled=req.enabled, interval_minutes=req.interval_minutes, actor_id=user["id"])
        record_event("connector.schedule.save", user_id=user["id"], workspace_id=workspace_id, resource_type="connector_source", resource_id=source_id, payload={"enabled":req.enabled,"interval_minutes":req.interval_minutes})
        return {"schedule": schedule}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/refresh-runs")
def connector_refresh_runs(workspace_id: str, source_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "connectors:read")
        return {"runs": get_refresh_runs(workspace_id, source_id, limit)}
    except Exception as exc:
        _handle(exc)

# ---------------------------- Data Catalog & Discovery v2.68 ----------------------------

@router.get("/workspaces/{workspace_id}/catalog/assets")
def workspace_catalog_assets(
    workspace_id: str,
    q: str = Query(default="", max_length=300),
    resource_type: str | None = Query(default=None, max_length=80),
    certification_status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=250, ge=1, le=1000),
    user=Depends(current_user),
):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return catalog_assets(workspace_id, query=q, resource_type=resource_type, certification_status=certification_status, limit=limit)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/catalog/summary")
def workspace_catalog_summary(workspace_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return catalog_summary(workspace_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/catalog/assets/{resource_type}/{resource_id}")
def workspace_catalog_asset_detail(workspace_id: str, resource_type: str, resource_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        item = get_catalog_entry(workspace_id, resource_type, resource_id)
        if item is None:
            raise KeyError("Entrée de catalogue introuvable")
        return {"entry": item}
    except Exception as exc:
        _handle(exc)


@router.put("/workspaces/{workspace_id}/catalog/assets/{resource_type}/{resource_id}")
def workspace_catalog_asset_update(workspace_id: str, resource_type: str, resource_id: str, req: CatalogAssetUpdateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:manage")
        item = save_catalog_entry(
            user["id"], workspace_id, resource_type, resource_id,
            title=req.title, description=req.description, business_domain=req.business_domain,
            owner_user_id=req.owner_user_id, steward_user_id=req.steward_user_id, tags=req.tags,
            glossary=req.glossary, certification_status=req.certification_status,
        )
        record_event("catalog.asset.update", user_id=user["id"], workspace_id=workspace_id, resource_type=resource_type, resource_id=resource_id, payload={"certification_status": req.certification_status, "tags": req.tags})
        return {"entry": item}
    except Exception as exc:
        _handle(exc)


# ---------------------------- Data Reliability & Lineage v2.8 ----------------------------

@router.get("/workspaces/{workspace_id}/reliability/summary")
def reliability_workspace_summary(workspace_id: str, dataset_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return reliability_summary(workspace_id, dataset_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/contracts")
def contracts_list(workspace_id: str, dataset_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return {"contracts": list_contracts(workspace_id, dataset_id)}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/contracts")
def contracts_save(workspace_id: str, req: DataContractRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:manage")
        contract = save_contract(user["id"], workspace_id, req.dataset_id, name=req.name, description=req.description, rules=req.rules, enforcement_mode=req.enforcement_mode, enabled=req.enabled, contract_id=req.contract_id)
        record_event("reliability.contract.save", user_id=user["id"], workspace_id=workspace_id, resource_type="data_contract", resource_id=contract["id"], payload={"dataset_id":req.dataset_id,"enforcement_mode":req.enforcement_mode})
        return {"contract": contract}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/contracts/{contract_id}")
def contracts_detail(workspace_id: str, contract_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return {"contract": get_contract(workspace_id, contract_id), "runs": list_contract_runs(workspace_id, contract_id, limit=50)}
    except Exception as exc:
        _handle(exc)


@router.delete("/workspaces/{workspace_id}/contracts/{contract_id}")
def contracts_delete(workspace_id: str, contract_id: str, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:manage")
        delete_contract(workspace_id, contract_id)
        record_event("reliability.contract.delete", user_id=user["id"], workspace_id=workspace_id, resource_type="data_contract", resource_id=contract_id)
        return {"deleted": True, "contract_id": contract_id}
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/contracts/{contract_id}/run")
def contracts_run(workspace_id: str, contract_id: str, req: ContractRunRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:run")
        result = run_contract(user["id"], workspace_id, contract_id, req.dataset_id)
        record_event("reliability.contract.run", user_id=user["id"], workspace_id=workspace_id, resource_type="data_contract", resource_id=contract_id, outcome="success" if result.get("status") == "healthy" else "failed", payload={"run_id":result.get("id"),"score":result.get("score"),"status":result.get("status")})
        if result.get("status") != "healthy":
            try:
                severity = "critical" if int(result.get("blocking_failures") or 0) > 0 else "high"
                dispatch_event(user["id"], workspace_id, event_type="reliability_failure", event_id=str(result.get("id")), dataset_id=result.get("dataset_id"), payload={"contract_id":contract_id,"run_id":result.get("id"),"status":result.get("status"),"score":result.get("score"),"blocking_failures":result.get("blocking_failures"),"severity":severity})
            except Exception:
                pass
        return {"run": result}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/contract-runs")
def contracts_runs(workspace_id: str, contract_id: str | None = Query(default=None), dataset_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return {"runs": list_contract_runs(workspace_id, contract_id, dataset_id, limit)}
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/lineage")
def lineage_graph(workspace_id: str, dataset_id: str | None = Query(default=None), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return build_lineage_graph(workspace_id, dataset_id)
    except Exception as exc:
        _handle(exc)


@router.get("/workspaces/{workspace_id}/impact/{resource_type}/{resource_id}")
def lineage_impact(workspace_id: str, resource_type: str, resource_id: str, depth: int = Query(default=6, ge=1, le=12), user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return impact_analysis(workspace_id, resource_type, resource_id, depth)
    except Exception as exc:
        _handle(exc)


@router.post("/workspaces/{workspace_id}/publication-gate")
def reliability_publication_gate(workspace_id: str, req: PublicationGateRequest, user=Depends(current_user)):
    try:
        _workspace_permission(user["id"], workspace_id, "reliability:read")
        return publication_gate(workspace_id, req.dataset_id)
    except Exception as exc:
        _handle(exc)

