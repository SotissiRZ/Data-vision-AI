from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.datasets import router as datasets_router
from app.api.routes.enterprise import router as enterprise_router
from app.core.config import get_settings
from app.services.auth_service import has_permission
from app.services.tenant_access import (
    authorize_dataset,
    build_access_context,
    reset_access_context,
    set_access_context,
)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.2.0", docs_url="/docs", redoc_url="/redoc")
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
        if any(x in path for x in ("/transform", "/combine", "/pipelines")):
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


@app.get("/health")
def health():
    return {"status": "ok", "product": settings.app_name, "version": "2.2.0"}


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
        ],
        "partial": [
            "shap", "fairness", "nlq", "running_job_preemptive_cancellation", "refresh_tokens", "secret_vault",
            "model_artifact_policy_snapshot", "database_native_rls",
        ],
        "planned": [
            "multi_agent", "r_workspace", "collaboration", "oidc_sso", "kubernetes_enterprise",
        ],
    }


app.include_router(datasets_router, prefix="/api/v1")
app.include_router(enterprise_router, prefix="/api/v1")
