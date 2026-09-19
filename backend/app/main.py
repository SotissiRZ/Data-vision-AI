from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.datasets import router as datasets_router
from app.api.routes.enterprise import router as enterprise_router
from app.assistant.router import router as assistant_router
from app.core.config import get_settings
from app.services.auth_service import has_permission
from app.services.tenant_access import (
    authorize_dataset,
    build_access_context,
    reset_access_context,
    set_access_context,
)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.17.0", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-DataVision-Governed", "X-DataVision-Role", "X-DataVision-Workspace"],
)


def _dataset_permission(path: str, method: str) -> str:
    """Map every legacy dataset route to an Enterprise permission.

    The mapping is deliberately conservative: write/publish/model/analysis endpoints require
    their dedicated permission, while GET endpoints require dataset:read.
    """
    method = method.upper()
    if method == "POST" and path.rstrip("/").endswith("/datasets"):
        return "dataset:write"
    if any(x in path for x in ("/models/train", "/models/automl")):
        return "model:run"
    if "/models/" in path and any(x in path for x in ("/predict", "/diagnostics", "/explain", "/what-if", "/sensitivity")):
        return "analysis:run"
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        if any(x in path for x in ("/transform", "/combine", "/pipelines", "/proactive/watches")):
            return "dataset:write"
        if "/proactive/scan" in path:
            return "analysis:run"
        if "/proactive/inbox/" in path and path.endswith("/status"):
            return "dataset:write"
        if path.rstrip("/").endswith("/semantic"):
            return "dataset:write"
        if any(x in path for x in ("/reports", "/visualizations/saved", "/dashboards")) and "/dashboards/preview" not in path:
            return "publish:write"
        if any(x in path for x in ("/analysis/", "/workspace/sql", "/workspace/nlq", "/ai/analyze", "/visualizations/", "/dashboard")):
            return "analysis:run"
    return "dataset:read"


def _dataset_id_from_path(path: str) -> str | None:
    prefix = "/api/v1/datasets/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    if not rest or rest.startswith("catalog/"):
        return None
    parts = [p for p in rest.split("/") if p]
    if not parts:
        return None
    if parts[0] == "models" and len(parts) >= 2:
        try:
            from app.services.modeling import get_model_card
            card = get_model_card(parts[1])
            return card.get("dataset", {}).get("id")
        except Exception:
            return None
    return parts[0]


@app.middleware("http")
async def operational_telemetry(request: Request, call_next):
    """Best-effort platform telemetry. Never blocks a user request if observability storage fails."""
    started = time.perf_counter()
    response = None
    error_name = None
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        error_name = type(exc).__name__
        raise
    finally:
        path = request.url.path
        if path.startswith("/api/v1"):
            try:
                from app.services.auth_service import decode_token
                from app.services.metadata_store import fetch_one
                from app.services.operational_intelligence import feature_for_path, record_telemetry
                workspace_id = request.headers.get("x-workspace-id")
                if not workspace_id and path.startswith("/api/v1/workspaces/"):
                    parts = [p for p in path.split("/") if p]
                    if len(parts) >= 4:
                        workspace_id = parts[3]
                user_id = None
                auth = request.headers.get("authorization") or ""
                if auth.lower().startswith("bearer "):
                    try: user_id = decode_token(auth.split(" ", 1)[1].strip()).get("sub")
                    except Exception: user_id = None
                organization_id = None
                if workspace_id:
                    row = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": workspace_id})
                    organization_id = row.get("organization_id") if row else None
                status_code = response.status_code if response is not None else 500
                record_telemetry(
                    event_kind="http", name=f"{request.method.upper()} {path}", status=str(status_code),
                    workspace_id=workspace_id, organization_id=organization_id, user_id=user_id,
                    feature=feature_for_path(path), latency_ms=(time.perf_counter()-started)*1000.0,
                    resource_type="http", resource_id=path,
                    metadata={"method":request.method.upper(),"query":str(request.url.query or ""),"error":error_name},
                )
            except Exception:
                pass


@app.middleware("http")
async def tenant_aware_data_access(request: Request, call_next):
    """Apply RBAC/RLS/column security to every /datasets route when Enterprise headers exist.

    This is the v2.2 security boundary. Because the context is also consumed by storage.load_dataframe,
    the same governed frame reaches statistics, SQL, ML, XAI, dashboards, AI Analyst and reporting.
    """
    path = request.url.path
    if request.method.upper() == "OPTIONS" or not path.startswith("/api/v1/datasets"):
        return await call_next(request)

    authorization = request.headers.get("authorization")
    workspace_id = request.headers.get("x-workspace-id")
    token = None
    ctx = None
    try:
        ctx = build_access_context(authorization, workspace_id)
        token = set_access_context(ctx)
        if ctx:
            permission = _dataset_permission(path, request.method)
            dataset_id = _dataset_id_from_path(path)
            if dataset_id:
                authorize_dataset(dataset_id, permission, ctx)
            elif not has_permission(ctx.user_id, ctx.workspace_id, permission):
                raise PermissionError(f"Permission insuffisante: {permission}.")
        response = await call_next(request)
        if ctx:
            response.headers["X-DataVision-Governed"] = "true"
            response.headers["X-DataVision-Role"] = ctx.role
            response.headers["X-DataVision-Workspace"] = ctx.workspace_id
        return response
    except PermissionError as exc:
        if ctx is not None:
            try:
                from app.services.audit_service import record_event
                record_event(
                    "security.access_denied", user_id=ctx.user_id, organization_id=ctx.organization_id,
                    workspace_id=ctx.workspace_id, resource_type="http", resource_id=path,
                    outcome="denied", payload={"method": request.method, "reason": str(exc)},
                )
            except Exception:
                pass
        return JSONResponse(status_code=403, content={"detail": str(exc), "security_boundary": "tenant-aware-data-access"})
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"detail": str(exc), "security_boundary": "tenant-aware-data-access"})
    finally:
        if token is not None:
            reset_access_context(token)


@app.middleware("http")
async def assistant_tenant_access(request: Request, call_next):
    """Propagate the existing v2.12 Enterprise auth context into assistant tools."""
    path = request.url.path
    if request.method.upper() == "OPTIONS" or not path.startswith("/api/v1/ai/assistant"):
        return await call_next(request)

    workspace_id = request.headers.get("x-workspace-id")
    authorization = request.headers.get("authorization")
    token = None
    try:
        ctx = build_access_context(authorization, workspace_id)
        token = set_access_context(ctx)
        return await call_next(request)
    except PermissionError as exc:
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "security_boundary": "assistant-tenant-access"},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc), "security_boundary": "assistant-tenant-access"},
        )
    finally:
        if token is not None:
            reset_access_context(token)


@app.get("/health")
def health():
    return {"status": "ok", "product": settings.app_name, "version": "2.17.0"}


@app.get("/api/v1/capabilities")
def capabilities():
    return {
        "implemented": [
            "file_upload", "dataset_preview", "profiling", "column_descriptive_analysis",
            "quality_rules", "decision_support", "data_preparation", "dataset_versioning",
            "rollback_by_version", "visual_preparation_pipeline", "saved_replayable_pipelines",
            "dataset_join_concat", "groupby_aggregation", "pivot_unpivot", "feature_engineering",
            "one_hot_encoding", "statistical_test_advisor", "parametric_tests", "nonparametric_tests",
            "correlations", "visualization_studio", "sql_workspace_readonly", "duckdb_polars_layer",
            "linear_regression", "anova_one_way", "anova_two_way", "pca", "kmeans_clustering",
            "ml_train_validation_test", "ml_cross_validation", "automl_benchmark", "controlled_hyperparameter_tuning",
            "ml_guardrails", "class_imbalance_detection", "leakage_heuristics", "feature_importance",
            "local_model_registry", "model_cards", "prediction_api",
            "forecasting", "forecast_model_benchmark", "prediction_intervals", "anomaly_detection",
            "xai_diagnostics", "confusion_matrix", "roc_pr_curves", "binary_calibration", "local_perturbation_explanations",
            "ai_analyst_orchestrator", "natural_language_intent_routing", "analytic_tool_registry", "critic_validation", "analysis_provenance",
            "analytical_dashboard", "deterministic_insight_feed", "saved_visualizations", "report_visualization_assets",
            "dashboard_builder", "dashboard_global_filters", "dashboard_cross_filtering", "dashboard_persistence",
            "local_authentication", "organizations", "enterprise_workspaces", "workspace_rbac", "member_provisioning",
            "postgres_metadata_store", "sqlite_metadata_fallback", "workspace_dataset_binding", "access_policy_registry",
            "governed_dataset_preview", "consolidated_audit_log", "redis_job_queue", "background_worker", "job_tracking",
            "queued_job_cancellation", "governance_center_ui",
            "tenant_aware_dataset_access", "global_row_level_security", "global_column_level_security",
            "workspace_catalog_isolation", "derived_version_policy_inheritance", "governed_background_jobs",
            "proactive_metric_watches", "analytical_inbox", "deterministic_change_detection", "semantic_metric_monitoring",
            "alert_acknowledgement", "investigation_recommendations",
            "collaboration_reviews", "review_workflows", "review_comments", "review_mentions", "review_notifications", "review_decision_history",
            "postgresql_connectors", "mysql_connectors", "encrypted_connector_credentials", "source_discovery", "manual_refresh",
            "scheduled_refresh", "incremental_refresh", "refresh_watermarks", "freshness_sla", "schema_drift_detection", "connector_observability",
            "data_contracts", "contract_rule_engine", "distribution_drift_detection", "reliability_events", "end_to_end_lineage",
            "impact_analysis", "publication_reliability_gate", "contract_aware_report_export", "contract_aware_certification", "automatic_contract_checks_on_derived_versions",
            "platform_telemetry", "feature_usage_analytics", "operational_slo_dashboard", "job_attempt_tracking", "job_retry_backoff", "ai_evaluation_suites", "ai_regression_benchmarks",
            "semantic_layer", "semantic_multitable", "semantic_calculated_metrics", "semantic_time_intelligence",
            "semantic_nlq_multitable", "semantic_dashboard_widgets", "semantic_drilldown",
            "governed_actions", "human_approval_actions", "signed_webhooks", "action_idempotency", "action_deduplication",
            "action_throttling", "action_quiet_hours", "action_replay", "webhook_ssrf_guard", "action_delivery_audit",
            "native_slack_actions", "native_teams_actions", "native_jira_actions", "native_email_actions",
            "encrypted_action_credentials", "oauth2_client_credentials", "staged_action_approvals", "action_connector_tests",
            "persistent_auth_sessions", "rotating_refresh_tokens", "server_side_session_revocation",
            "oidc_sso", "oidc_authorization_code_pkce", "oidc_rs256_validation", "oidc_jit_provisioning",
            "versioned_secret_vault", "environment_secret_references", "hashicorp_vault_kv2_references",
            "floating_voice_assistant", "semantic_context_engine", "assistant_tool_registry",
            "assistant_action_lifecycle", "assistant_plan_validation", "assistant_turn_resume",
            "assistant_model_gateway", "assistant_privacy_routing",
        ],
        "partial": [
            "scheduled_proactive_scans", "shap", "fairness", "nlq", "running_job_preemptive_cancellation",
            "model_artifact_policy_snapshot", "database_native_rls", "provider_token_cost_instrumentation", "external_kms_key_management",
            "assistant_gis_execution", "assistant_pptx_export", "assistant_shap_provider",
        ],
        "planned": [
            "multi_agent", "r_workspace", "kubernetes_enterprise", "scim_provisioning",
        ],
    }


app.include_router(datasets_router, prefix="/api/v1")
app.include_router(enterprise_router, prefix="/api/v1")

app.include_router(assistant_router, prefix="/api/v1")
