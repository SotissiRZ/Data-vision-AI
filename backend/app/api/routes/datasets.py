from typing import Any
from pathlib import Path
import time
from fastapi import APIRouter, File, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.services.upload_security import scan_upload
from app.services.storage import (
    save_upload, save_zip_upload, load_dataframe, get_meta, save_dataframe_version,
    get_lineage, list_versions, list_dataset_catalog,
)
from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.modeling import train_model, algorithm_availability, predict, get_model_card, list_model_cards
from app.services.automl_engine import run_automl_experiment, run_automl_benchmark, list_automl_experiments, get_automl_experiment, audit_automl_safety
from app.services.decision import decision_support
from app.services.exploration import analyze_column, preview_dataframe
from app.services.advanced_analysis import regression_analysis, anova_analysis, pca_analysis, clustering_analysis
from app.services.preparation import apply_operation, combine_dataframes
from app.services.pipelines import list_pipelines, save_lineage_as_pipeline, run_pipeline, validate_pipeline
from app.services.statistics_engine import correlation_analysis, statistical_test, test_advisor
from app.services.data_workspace import engine_info, run_sql
from app.services.visualization import build_visualization, recommend_visualizations, edit_visualization, build_visualization_composition
from app.services.forecasting import forecast_series
from app.services.anomaly_detection import detect_anomalies
from app.services.xai import model_diagnostics, local_explanation, xai_capabilities, partial_dependence, shap_explanation, generate_counterfactuals, xai_audit
from app.services.ai_analyst import AnalystContext, analyze_dataset, tool_registry
from app.services.analysis_history import save_analysis, list_analyses, get_analysis
from app.services.ai_analysis_runtime import (
    assert_run_access, cancel_analysis_run, get_analysis_run,
    stream_analysis_events, submit_analysis_run,
)
from app.services.nlq_sql import run_nlq
from app.services.report_builder import build_report, list_reports, get_report, export_report, validate_report
from app.services.dashboard import dashboard_overview
from app.services.insight_engine import generate_insights, insight_history
from app.services.saved_visualizations import save_visualization, list_visualizations
from app.services.dashboard_builder import save_dashboard, list_dashboards, get_dashboard_definition, delete_dashboard, preview_dashboard
from app.services.semantic_layer import (
    get_semantic_model, save_semantic_model, evaluate_metric, metric_pulse,
    semantic_table_catalog, validate_semantic_model, query_semantic_metric,
)
from app.services.trust_center import trust_center
from app.services.decision_lab import model_what_if, sensitivity_curve, optimize_scenarios
from app.services.root_cause import root_cause_analysis
from app.services.feature_store import (
    create_feature_set, get_feature_set, list_feature_sets,
    materialize_feature_set, model_feature_contract,
    set_feature_set_status,
)
from app.services.model_serving import (
    batch_score_dataset, create_deployment, deployment_metrics,
    get_deployment, list_deployments, rollback_deployment,
    score_deployment, update_deployment,
)
from app.services.job_service import submit_job
from app.services.model_registry import (
    LOCAL_ACTOR, LOCAL_WORKSPACE, check_retraining, get_registry_entry,
    get_retraining_policy, list_monitoring_runs, list_registry_entries,
    list_retraining_requests, monitor_model, register_model, registry_summary,
    save_retraining_policy, transition_model, get_monitor_schedule,
    list_monitor_schedules, save_monitor_schedule,
)
from app.services.auth_service import has_permission
from app.services.responsible_ai import (
    fairness_report,
    model_risk_assessment,
    population_drift,
    responsible_ai_gate,
    persist_responsible_ai_summary,
)
from app.services.tenant_access import access_summary, current_access_context, authorize_dataset
from app.services.data_reliability import publication_gate
from app.services.operational_intelligence import record_telemetry
from app.services.proactive_intelligence import (
    list_watches as proactive_list_watches, save_watch as proactive_save_watch, delete_watch as proactive_delete_watch,
    auto_configure_watches as proactive_auto_configure, scan as proactive_scan, list_alerts as proactive_list_alerts,
    update_alert_status as proactive_update_alert_status, proactive_summary,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _registry_identity(permission: str | None = None) -> tuple[str, str]:
    access = current_access_context()
    if access is None:
        return LOCAL_ACTOR, LOCAL_WORKSPACE
    if permission and not has_permission(access.user_id, access.workspace_id, permission):
        raise PermissionError(f"Permission requise: {permission}")
    return str(access.user_id), str(access.workspace_id)


def _registry_error(exc: Exception):
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Modèle ou dataset introuvable") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=f"Opération MLOps impossible: {exc}") from exc



class InsightScanRequest(BaseModel):
    max_insights: int = Field(default=20, ge=1, le=100)


class TrainRequest(BaseModel):
    target: str
    task: str = Field(default="auto", pattern="^(auto|classification|regression)$")
    algorithm: str = Field(
        default="auto",
        pattern="^(auto|linear_regression|ridge|logistic_regression|random_forest|extra_trees|gradient_boosting|hist_gradient_boosting|svm|xgboost|lightgbm|catboost)$",
    )


class AutoMLRequest(BaseModel):
    target: str | None = None
    task: str = Field(default="auto", pattern="^(auto|classification|regression|clustering)$")
    features: list[str] | None = None
    primary_metric: str = Field(default="auto", pattern="^(auto|accuracy|balanced_accuracy|f1_weighted|roc_auc|rmse|mae|r2|silhouette|calinski_harabasz|davies_bouldin)$")
    cv_folds: int = Field(default=5, ge=2, le=10)
    tune: bool = True
    max_candidates: int = Field(default=7, ge=2, le=24)
    split_strategy: str = Field(default="auto", pattern="^(auto|random|temporal)$")
    time_column: str | None = None


class MLSafetyAuditRequest(BaseModel):
    target: str | None = None
    task: str = Field(default="auto", pattern="^(auto|classification|regression|clustering)$")
    features: list[str] | None = None
    primary_metric: str = Field(default="auto")
    split_strategy: str = Field(default="auto", pattern="^(auto|random|temporal)$")
    time_column: str | None = None


class BenchmarkRequest(BaseModel):
    target: str | None = None
    task: str = Field(default="auto", pattern="^(auto|classification|regression|clustering)$")
    features: list[str] | None = None
    primary_metric: str = Field(default="auto", pattern="^(auto|accuracy|balanced_accuracy|f1_weighted|roc_auc|rmse|mae|r2|silhouette|calinski_harabasz|davies_bouldin)$")
    cv_folds: int = Field(default=5, ge=2, le=10)
    max_candidates: int = Field(default=10, ge=2, le=24)
    split_strategy: str = Field(default="auto", pattern="^(auto|random|temporal)$")
    time_column: str | None = None


class PredictRequest(BaseModel):
    rows: list[dict]


class RegressionRequest(BaseModel):
    dependent: str
    independents: list[str]


class AnovaRequest(BaseModel):
    response: str
    factor1: str
    factor2: str | None = None


class PCARequest(BaseModel):
    columns: list[str]
    scale: bool = True


class ClusterRequest(BaseModel):
    columns: list[str]
    k: int = Field(default=3, ge=2, le=10)


class TransformRequest(BaseModel):
    operation: dict


class CombineRequest(BaseModel):
    other_dataset_id: str
    operation: dict


class PipelineSaveRequest(BaseModel):
    name: str


class PipelineRunRequest(BaseModel):
    bindings: dict[str, str] = Field(default_factory=dict)


class CorrelationRequest(BaseModel):
    columns: list[str]
    method: str = Field(default="pearson", pattern="^(pearson|spearman)$")


class StatisticalTestRequest(BaseModel):
    test: str
    value: str | None = None
    group: str | None = None
    x: str | None = None
    y: str | None = None
    paired: bool = False


class TestAdvisorRequest(BaseModel):
    value: str | None = None
    group: str | None = None
    x: str | None = None
    y: str | None = None
    paired: bool = False


class SQLRequest(BaseModel):
    sql: str
    limit: int = Field(default=500, ge=1, le=5000)


class VisualizationRequest(BaseModel):
    chart_type: str = "auto"
    x: str | None = None
    y: str | None = None
    color: str | None = None
    size: str | None = None
    facet: str | None = None
    aggregation: str = "none"
    bins: int = Field(default=20, ge=5, le=80)
    columns: list[str] = Field(default_factory=list)
    cluster_k: int = Field(default=3, ge=2, le=10)
    max_points: int = Field(default=3000, ge=100, le=10000)


class VisualizationRecommendRequest(BaseModel):
    columns: list[str] = Field(default_factory=list)


class VisualizationEditRequest(BaseModel):
    visualization: dict
    instruction: str = Field(min_length=2, max_length=500)


class VisualizationComposeRequest(BaseModel):
    columns: list[str] = Field(default_factory=list)
    intent: str = Field(default="overview", max_length=80)
    max_views: int = Field(default=4, ge=2, le=6)


class ForecastRequest(BaseModel):
    date_column: str
    target: str
    horizon: int = Field(default=12, ge=1, le=365)
    frequency: str = Field(default="auto", pattern="^(auto|daily|weekly|monthly|quarterly|yearly)$")
    method: str = Field(default="auto", pattern="^(auto|naive|seasonal_naive|linear_trend|exponential_smoothing)$")
    backtest_windows: int = Field(default=3, ge=1, le=8)
    interval_level: float = Field(default=0.95, ge=0.5, le=0.99)
    missing_strategy: str = Field(default="none", pattern="^(none|interpolate|ffill|zero)$")
    selection_metric: str = Field(default="rmse", pattern="^(rmse|mae|smape)$")


class AnomalyRequest(BaseModel):
    columns: list[str] = []
    method: str = Field(default="auto", pattern="^(auto|iqr|robust_z|isolation_forest|consensus)$")
    contamination: float = Field(default=0.05, ge=0.001, le=0.4)
    threshold: float = Field(default=3.5, ge=1.0, le=10.0)


class LocalExplanationRequest(BaseModel):
    row: dict


class PDPRequest(BaseModel):
    features: list[str] = Field(min_length=1, max_length=8)
    grid_points: int = Field(default=20, ge=3, le=40)
    class_label: str | int | float | None = None


class SHAPRequest(BaseModel):
    row: dict | None = None
    max_rows: int = Field(default=60, ge=10, le=80)


class CounterfactualRequest(BaseModel):
    row: dict
    desired_class: str | int | float | None = None
    desired_value: float | None = None
    direction: str | None = Field(
        default=None,
        pattern="^(increase|decrease)?$",
    )
    max_changes: int = Field(default=2, ge=1, le=2)
    max_results: int = Field(default=5, ge=1, le=10)
    immutable_features: list[str] = []
    actionable_features: list[str] | None = None
    feature_constraints: dict[str, dict[str, Any]] = {}


class XAIAuditRequest(BaseModel):
    row: dict | None = None
    pdp_features: list[str] = Field(default_factory=list, max_length=8)
    include_shap: bool = False
    persist: bool = True


class FairnessRequest(BaseModel):
    protected_columns: list[str] = Field(min_length=1, max_length=3)
    positive_label: str | int | float | bool | None = None
    mode: str = Field(default="both", pattern="^(separate|intersectional|both)$")
    min_group_size: int = Field(default=20, ge=2, le=100000)
    persist_summary: bool = False


class ResponsibleAIGateRequest(FairnessRequest):
    policy: dict[str, Any] = {}


class ResponsibleAIRiskRequest(BaseModel):
    protected_columns: list[str] = Field(default_factory=list, max_length=3)
    positive_label: str | int | float | bool | None = None
    mode: str = Field(default="both", pattern="^(separate|intersectional|both)$")
    min_group_size: int = Field(default=20, ge=2, le=100000)
    persist_summary: bool = False


class PopulationDriftRequest(FairnessRequest):
    current_dataset_id: str




class ModelRegistryRegisterRequest(BaseModel):
    name: str | None = Field(default=None, max_length=240)
    notes: str = Field(default="", max_length=2000)


class ModelStageTransitionRequest(BaseModel):
    target_stage: str = Field(pattern="^(draft|staging|production|retired)$")
    note: str = Field(default="", max_length=2000)


class ModelMonitorRequest(BaseModel):
    current_dataset_id: str
    policy: dict[str, Any] | None = None


class MonitorScheduleRequest(BaseModel):
    current_dataset_id: str
    enabled: bool = True
    interval_minutes: int = Field(default=1440, ge=15, le=43200)
    policy: dict[str, Any] | None = None


class RetrainingPolicyRequest(BaseModel):
    enabled: bool = False
    min_rows: int = Field(default=100, ge=10, le=10000000)
    metric_degradation_threshold: float = Field(default=0.15, ge=0.0, le=10.0)
    feature_drift_threshold: float = Field(default=0.35, ge=0.0, le=10.0)
    cooldown_hours: int = Field(default=168, ge=0, le=8760)
    auto_create_request: bool = True


class RetrainingCheckRequest(BaseModel):
    create_request: bool = True




class FeatureSetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    source_dataset_id: str
    features: list[str] = Field(min_length=1, max_length=500)
    entity_keys: list[str] = Field(default_factory=list, max_length=20)
    event_time_column: str | None = None
    description: str = Field(default="", max_length=2000)


class FeatureSetStatusRequest(BaseModel):
    status: str = Field(pattern="^(draft|active|archived)$")


class FeatureMaterializeRequest(BaseModel):
    source_dataset_id: str | None = None


class DeploymentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    endpoint_key: str = Field(min_length=1, max_length=120)
    primary_model_id: str
    strategy: str = Field(
        default="champion",
        pattern="^(champion|shadow|canary)$",
    )
    secondary_model_id: str | None = None
    traffic_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    status: str = Field(default="active", pattern="^(active|inactive)$")


class DeploymentUpdateRequest(BaseModel):
    primary_model_id: str | None = None
    strategy: str | None = Field(
        default=None,
        pattern="^(champion|shadow|canary)$",
    )
    secondary_model_id: str | None = None
    traffic_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    status: str | None = Field(
        default=None,
        pattern="^(active|inactive)$",
    )
    reason: str = Field(default="deployment_updated", max_length=1000)


class ServingPredictRequest(BaseModel):
    rows: list[dict] = Field(min_length=1, max_length=5000)
    request_id: str | None = Field(default=None, max_length=200)


class BatchScoreRequest(BaseModel):
    dataset_id: str
    prediction_column: str = Field(
        default="prediction",
        min_length=1,
        max_length=120,
    )
    background: bool = False


class NLQRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=200, ge=1, le=5000)


class ReportCreateRequest(BaseModel):
    title: str = Field(default="Rapport DataVision", min_length=1, max_length=180)
    subtitle: str | None = Field(default=None, max_length=240)
    author: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=120)
    template: str = Field(default="analytical", pattern="^(executive|analytical|technical)$")
    sections: list[str] = ["executive_summary", "analytical_story", "overview", "quality", "descriptive", "visualizations", "ai_analysis", "limitations", "methodology", "provenance"]
    analysis_session_id: str | None = None
    visualization_ids: list[str] = []
    auto_story: bool = False
    auto_visualizations: bool = False
    max_visualizations: int = Field(default=6, ge=1, le=10)
    custom_blocks: list[dict] = Field(default_factory=list)
    block_order: list[str] = Field(default_factory=list)



class SaveVisualizationRequest(BaseModel):
    title: str = Field(default="Visualisation DataVision", min_length=1, max_length=180)
    visualization: dict



class DashboardSaveRequest(BaseModel):
    dashboard_id: str | None = None
    name: str = Field(default="Dashboard DataVision", min_length=1, max_length=180)
    description: str = Field(default="", max_length=500)
    filters: list[dict] = []
    widgets: list[dict] = []


class DashboardPreviewRequest(BaseModel):
    filters: list[dict] = []
    widgets: list[dict] = []

class SemanticSaveRequest(BaseModel):
    tables: list[dict] = []
    relationships: list[dict] = []
    metrics: list[dict] = []
    dimensions: list[dict] = []
    hierarchies: list[dict] = []
    business_glossary: list[dict] = []


class SemanticQueryRequest(BaseModel):
    metric_id: str
    dimensions: list[str] = []
    filters: list[dict] = []
    limit: int = Field(default=500, ge=1, le=5000)
    date_dimension: str | None = None
    time_grain: str | None = Field(default=None, pattern="^(day|week|month|quarter|year)?$")
    comparison: str = Field(default="none", pattern="^(none|previous_period|yoy)$")
    time_calculation: str = Field(default="none", pattern="^(none|running_total|ytd|rolling_mean|rolling_sum)$")
    rolling_window: int = Field(default=3, ge=2, le=36)


class MetricEvaluateRequest(BaseModel):
    metric_id: str
    dimensions: list[str] = []
    filters: list[dict] = []
    limit: int = Field(default=200, ge=1, le=500)


class MetricPulseRequest(BaseModel):
    metric_id: str
    date_column: str | None = None
    periods: int = Field(default=12, ge=2, le=36)


class WhatIfRequest(BaseModel):
    base_row: dict
    scenarios: list[dict] = []


class SensitivityRequest(BaseModel):
    base_row: dict
    feature: str
    values: list






class RootCauseRequest(BaseModel):
    target: str
    comparison_column: str
    baseline_value: str | int | float | bool | None = None
    current_value: str | int | float | bool | None = None
    metric: str = Field(default="mean", pattern="^(mean|sum|count)$")
    dimensions: list[str] | None = None
    time_grain: str = Field(
        default="auto",
        pattern="^(auto|raw|day|week|month|quarter|year)$",
    )
    min_segment_size: int = Field(default=5, ge=1, le=10000)
    top_n: int = Field(default=8, ge=1, le=20)


class ScenarioOptimizeRequest(BaseModel):
    base_row: dict
    controls: dict[str, dict]
    objective: str = Field(
        default="maximize",
        pattern="^(maximize|minimize|target)$",
    )
    target_value: float | None = None
    desired_class: str | int | float | bool | None = None
    max_candidates: int = Field(default=2000, ge=10, le=5000)
    max_results: int = Field(default=10, ge=1, le=20)


class ProactiveWatchRequest(BaseModel):
    id: str | None = None
    name: str | None = None
    metric_id: str
    date_dimension: str
    time_grain: str = Field(default="month", pattern="^(day|week|month|quarter|year)$")
    direction: str = Field(default="both", pattern="^(both|up|down)$")
    threshold_pct: float = Field(default=10.0, ge=0.1, le=1000)
    anomaly_z_threshold: float = Field(default=2.5, ge=1.0, le=10.0)
    min_history: int = Field(default=4, ge=3, le=120)
    filters: list[dict] = []
    enabled: bool = True


class ProactiveAutoRequest(BaseModel):
    threshold_pct: float = Field(default=10.0, ge=0.1, le=1000)
    time_grain: str = Field(default="month", pattern="^(day|week|month|quarter|year)$")


class ProactiveScanRequest(BaseModel):
    watch_ids: list[str] = []
    auto_configure: bool = True


class ProactiveAlertStatusRequest(BaseModel):
    status: str = Field(pattern="^(open|acknowledged|dismissed|resolved)$")

class AIAnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    target: str | None = None
    date_column: str | None = None
    variables: list[str] = []
    group: str | None = None
    horizon: int = Field(default=12, ge=1, le=365)
    mode: str = Field(default="auto", pattern="^(auto|fast|deep)$")
    use_cache: bool = True


def _dataset_payload(meta: dict) -> dict:
    return {
        "id": meta["id"],
        "name": meta["original_name"],
        "format": meta["extension"],
        "version": meta.get("version", 1),
        "parent_id": meta.get("parent_id"),
        "root_id": meta.get("root_id", meta["id"]),
        "operation": meta.get("operation"),
    }


def _bundle(meta: dict, frame=None) -> dict:
    df = frame if frame is not None else load_dataframe(meta["id"])
    profile = profile_dataframe(df)
    quality = quality_report(df)
    return {
        "dataset": _dataset_payload(meta),
        "profile": profile,
        "quality": quality,
        "preview": preview_dataframe(df, 25),
        "decision": decision_support(profile, quality),
        "versions": dataset_versions(meta["id"]),
        "access": access_summary(meta["id"]),
    }


@router.post("")
async def upload_dataset(request: Request, file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename or "dataset"
        scan = scan_upload(filename, content)
        if Path(filename).suffix.lower() == ".zip":
            metas = save_zip_upload(filename, content, scan_member=scan_upload)
        else:
            metas = [save_upload(filename, content)]
        for meta in metas:
            meta["security_scan"] = {
                "id": scan.get("id"),
                "status": scan.get("status"),
                "engine": scan.get("engine"),
                "sha256": scan.get("sha256"),
            }
        meta = metas[0]
        workspace_id = request.headers.get("x-workspace-id")
        authorization = request.headers.get("authorization")
        if workspace_id and authorization and authorization.lower().startswith("bearer "):
            try:
                from app.services.auth_service import decode_token, get_user
                from app.services.workspace_service import bind_dataset, get_workspace
                from app.services.audit_service import record_event
                payload = decode_token(authorization.split(" ", 1)[1].strip())
                user = get_user(payload["sub"])
                if not user:
                    raise ValueError("Utilisateur introuvable")
                ws = get_workspace(user["id"], workspace_id)
                for imported_meta in metas:
                    bind_dataset(user["id"], workspace_id, imported_meta["id"])
                    record_event("dataset.upload", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="dataset", resource_id=imported_meta["id"], payload={"name": imported_meta["original_name"], "archive": imported_meta.get("archive")})
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=401, detail=f"Contexte workspace invalide: {exc}") from exc
        return {"dataset": {"id": meta["id"], "name": meta["original_name"], "format": meta["extension"]}, "datasets": [{"id": x["id"], "name": x["original_name"], "format": x["extension"], "archive": x.get("archive")} for x in metas], "imported_count": len(metas)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/catalog/all")
def dataset_catalog():
    return {"datasets": list_dataset_catalog()}


@router.get("/{dataset_id}")
def dataset_metadata(dataset_id: str):
    try:
        return _dataset_payload(get_meta(dataset_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/preview")
def dataset_preview(dataset_id: str, limit: int = 25):
    try:
        return preview_dataframe(load_dataframe(dataset_id), limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/columns/{column}/analysis")
def dataset_column_analysis(dataset_id: str, column: str):
    try:
        return analyze_column(load_dataframe(dataset_id), column)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/access-context")
def dataset_access_context(dataset_id: str):
    try:
        # load_dataframe performs the same authorization/policy resolution used by every engine.
        df = load_dataframe(dataset_id)
        summary = access_summary(dataset_id)
        summary.update({"effective_rows": int(len(df)), "effective_columns": [str(c) for c in df.columns]})
        return summary
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/profile")
def dataset_profile(dataset_id: str):
    try:
        return profile_dataframe(load_dataframe(dataset_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Profilage impossible: {exc}") from exc


@router.get("/{dataset_id}/quality")
def dataset_quality(dataset_id: str):
    try:
        return quality_report(load_dataframe(dataset_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Contrôle qualité impossible: {exc}") from exc


@router.get("/{dataset_id}/decision-support")
def dataset_decision_support(dataset_id: str):
    try:
        df = load_dataframe(dataset_id)
        profile = profile_dataframe(df)
        quality = quality_report(df)
        return decision_support(profile, quality)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/models/train")
def dataset_train(dataset_id: str, request: TrainRequest):
    try:
        meta = get_meta(dataset_id)
        result = train_model(load_dataframe(dataset_id), request.target, request.task, request.algorithm, _dataset_payload(meta))
        actor_id, workspace_id = _registry_identity("model:run")
        registry = register_model(actor_id, workspace_id, result.model_id)
        payload = dict(result.__dict__)
        payload["registry"] = registry
        return payload
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Entraînement impossible: {exc}") from exc


@router.post("/{dataset_id}/models/safety-audit")
def dataset_ml_safety_audit(dataset_id: str, request: MLSafetyAuditRequest):
    try:
        return audit_automl_safety(
            load_dataframe(dataset_id), target=request.target, task=request.task, features=request.features,
            primary_metric=request.primary_metric, split_strategy=request.split_strategy, time_column=request.time_column,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Audit ML Safety impossible: {exc}") from exc


@router.post("/{dataset_id}/models/automl")
def dataset_automl(dataset_id: str, request: AutoMLRequest):
    try:
        meta = get_meta(dataset_id)
        result = run_automl_experiment(
            load_dataframe(dataset_id), target=request.target, task=request.task, features=request.features,
            primary_metric=request.primary_metric, cv_folds=request.cv_folds, tune=request.tune,
            max_candidates=request.max_candidates, dataset_context=_dataset_payload(meta),
            split_strategy=request.split_strategy, time_column=request.time_column,
        )
        actor_id, workspace_id = _registry_identity("model:run")
        result["registry"] = register_model(actor_id, workspace_id, result["model_id"])
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"AutoML impossible: {exc}") from exc


@router.post("/{dataset_id}/models/benchmark")
def dataset_model_benchmark(
    dataset_id: str,
    request: BenchmarkRequest,
):
    try:
        return run_automl_benchmark(
            load_dataframe(dataset_id), target=request.target, task=request.task, features=request.features,
            primary_metric=request.primary_metric, cv_folds=request.cv_folds, max_candidates=request.max_candidates,
            split_strategy=request.split_strategy, time_column=request.time_column,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Dataset introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Benchmark impossible: {exc}",
        ) from exc





@router.get("/feature-store")
def feature_store_list(status: str | None = None):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        rows = list_feature_sets(workspace_id, status=status)
        return {"feature_sets": rows, "count": len(rows)}
    except Exception as exc:
        _registry_error(exc)


@router.post("/feature-store")
def feature_store_create(request: FeatureSetCreateRequest):
    try:
        actor_id, workspace_id = _registry_identity("dataset:write")
        return create_feature_set(
            actor_id,
            workspace_id,
            name=request.name,
            source_dataset_id=request.source_dataset_id,
            features=request.features,
            entity_keys=request.entity_keys,
            event_time_column=request.event_time_column,
            description=request.description,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/feature-store/{feature_set_id}")
def feature_store_detail(feature_set_id: str):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return get_feature_set(workspace_id, feature_set_id)
    except Exception as exc:
        _registry_error(exc)


@router.put("/feature-store/{feature_set_id}/status")
def feature_store_status(
    feature_set_id: str,
    request: FeatureSetStatusRequest,
):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return set_feature_set_status(
            actor_id,
            workspace_id,
            feature_set_id,
            request.status,
        )
    except Exception as exc:
        _registry_error(exc)


@router.post("/feature-store/{feature_set_id}/materialize")
def feature_store_materialize(
    feature_set_id: str,
    request: FeatureMaterializeRequest,
):
    try:
        actor_id, workspace_id = _registry_identity("dataset:write")
        return materialize_feature_set(
            actor_id,
            workspace_id,
            feature_set_id,
            source_dataset_id=request.source_dataset_id,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/{model_id}/feature-contract")
def model_serving_feature_contract(model_id: str):
    try:
        _registry_identity("dataset:read")
        return model_feature_contract(model_id)
    except Exception as exc:
        _registry_error(exc)


@router.get("/serving/deployments")
def serving_deployments():
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        rows = list_deployments(workspace_id)
        return {"deployments": rows, "count": len(rows)}
    except Exception as exc:
        _registry_error(exc)


@router.post("/serving/deployments")
def serving_deployment_create(request: DeploymentCreateRequest):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return create_deployment(
            actor_id,
            workspace_id,
            name=request.name,
            endpoint_key=request.endpoint_key,
            primary_model_id=request.primary_model_id,
            strategy=request.strategy,
            secondary_model_id=request.secondary_model_id,
            traffic_percent=request.traffic_percent,
            status=request.status,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/serving/deployments/{deployment_id}")
def serving_deployment_detail(deployment_id: str):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return get_deployment(workspace_id, deployment_id)
    except Exception as exc:
        _registry_error(exc)


@router.put("/serving/deployments/{deployment_id}")
def serving_deployment_update(
    deployment_id: str,
    request: DeploymentUpdateRequest,
):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return update_deployment(
            actor_id,
            workspace_id,
            deployment_id,
            primary_model_id=request.primary_model_id,
            strategy=request.strategy,
            secondary_model_id=request.secondary_model_id,
            traffic_percent=request.traffic_percent,
            status=request.status,
            reason=request.reason,
        )
    except Exception as exc:
        _registry_error(exc)


@router.post("/serving/deployments/{deployment_id}/rollback")
def serving_deployment_rollback(deployment_id: str):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return rollback_deployment(
            actor_id,
            workspace_id,
            deployment_id,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/serving/deployments/{deployment_id}/metrics")
def serving_deployment_metrics(
    deployment_id: str,
    limit: int = 500,
):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return deployment_metrics(
            workspace_id,
            deployment_id,
            limit=limit,
        )
    except Exception as exc:
        _registry_error(exc)


@router.post("/serving/{endpoint_key}/predict")
def serving_predict(
    endpoint_key: str,
    request: ServingPredictRequest,
):
    try:
        _actor_id, workspace_id = _registry_identity("model:run")
        return score_deployment(
            workspace_id,
            endpoint_key,
            request.rows,
            request_id=request.request_id,
        )
    except Exception as exc:
        _registry_error(exc)


@router.post("/models/{model_id}/batch-score")
def model_batch_score(
    model_id: str,
    request: BatchScoreRequest,
):
    try:
        actor_id, workspace_id = _registry_identity("model:run")
        access = current_access_context()
        if request.background and access is not None:
            return submit_job(
                user_id=access.user_id,
                organization_id=access.organization_id,
                workspace_id=access.workspace_id,
                job_type="batch_scoring",
                dataset_id=request.dataset_id,
                payload={
                    "model_id": model_id,
                    "prediction_column": request.prediction_column,
                },
            )
        return batch_score_dataset(
            actor_id,
            workspace_id,
            model_id=model_id,
            dataset_id=request.dataset_id,
            prediction_column=request.prediction_column,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/registry/summary")
def model_registry_summary():
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return registry_summary(workspace_id)
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/registry/entries")
def model_registry_entries(
    dataset_id: str | None = None,
    stage: str | None = None,
    model_key: str | None = None,
):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        rows = list_registry_entries(
            workspace_id,
            dataset_id=dataset_id,
            stage=stage,
            model_key=model_key,
        )
        return {"models": rows, "count": len(rows)}
    except Exception as exc:
        _registry_error(exc)


@router.post("/models/{model_id}/registry/register")
def model_registry_register(model_id: str, request: ModelRegistryRegisterRequest):
    try:
        actor_id, workspace_id = _registry_identity("model:run")
        return register_model(
            actor_id,
            workspace_id,
            model_id,
            name=request.name,
            notes=request.notes,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/{model_id}/registry")
def model_registry_detail(model_id: str):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return get_registry_entry(workspace_id, model_id)
    except Exception as exc:
        _registry_error(exc)


@router.post("/models/{model_id}/registry/transition")
def model_registry_transition(model_id: str, request: ModelStageTransitionRequest):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return transition_model(
            actor_id,
            workspace_id,
            model_id,
            target_stage=request.target_stage,
            note=request.note,
        )
    except Exception as exc:
        _registry_error(exc)


@router.post("/models/{model_id}/monitor")
def model_monitoring_run(model_id: str, request: ModelMonitorRequest):
    try:
        actor_id, workspace_id = _registry_identity("model:run")
        return monitor_model(
            actor_id,
            workspace_id,
            model_id,
            current_dataset_id=request.current_dataset_id,
            policy=request.policy,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/{model_id}/monitoring")
def model_monitoring_history(model_id: str, limit: int = 100):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        rows = list_monitoring_runs(workspace_id, model_id, limit=limit)
        return {"runs": rows, "count": len(rows)}
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/registry/schedules")
def model_monitor_schedules():
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        rows = list_monitor_schedules(workspace_id)
        return {"schedules": rows, "count": len(rows)}
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/{model_id}/monitor-schedule")
def model_monitor_schedule_get(model_id: str):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return get_monitor_schedule(workspace_id, model_id) or {
            "model_id": model_id,
            "enabled": False,
            "interval_minutes": 1440,
            "current_dataset_id": "",
            "policy": {},
        }
    except Exception as exc:
        _registry_error(exc)


@router.put("/models/{model_id}/monitor-schedule")
def model_monitor_schedule_put(model_id: str, request: MonitorScheduleRequest):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return save_monitor_schedule(
            actor_id,
            workspace_id,
            model_id,
            current_dataset_id=request.current_dataset_id,
            enabled=request.enabled,
            interval_minutes=request.interval_minutes,
            policy=request.policy,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/{model_id}/retraining-policy")
def model_retraining_policy_get(model_id: str):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        return get_retraining_policy(workspace_id, model_id)
    except Exception as exc:
        _registry_error(exc)


@router.put("/models/{model_id}/retraining-policy")
def model_retraining_policy_put(model_id: str, request: RetrainingPolicyRequest):
    try:
        actor_id, workspace_id = _registry_identity("publish:write")
        return save_retraining_policy(
            actor_id,
            workspace_id,
            model_id,
            enabled=request.enabled,
            min_rows=request.min_rows,
            metric_degradation_threshold=request.metric_degradation_threshold,
            feature_drift_threshold=request.feature_drift_threshold,
            cooldown_hours=request.cooldown_hours,
            auto_create_request=request.auto_create_request,
        )
    except Exception as exc:
        _registry_error(exc)


@router.post("/models/{model_id}/retraining/check")
def model_retraining_check(model_id: str, request: RetrainingCheckRequest):
    try:
        actor_id, workspace_id = _registry_identity("model:run")
        return check_retraining(
            actor_id,
            workspace_id,
            model_id,
            create_request=request.create_request,
        )
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/{model_id}/retraining/requests")
def model_retraining_requests(model_id: str):
    try:
        _actor_id, workspace_id = _registry_identity("dataset:read")
        rows = list_retraining_requests(workspace_id, model_id)
        return {"requests": rows, "count": len(rows)}
    except Exception as exc:
        _registry_error(exc)


@router.get("/models/engines")
def model_engines():
    return {"engines": algorithm_availability()}


@router.get("/{dataset_id}/models")
def dataset_models(dataset_id: str):
    try:
        get_meta(dataset_id)
        cards = list_model_cards(dataset_id)
        return {"models": cards, "count": len(cards)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/models/{model_id}/card")
def model_card(model_id: str):
    try:
        return get_model_card(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model Card introuvable") from exc




@router.get("/{dataset_id}/models/experiments")
def dataset_automl_experiments(dataset_id: str):
    try:
        get_meta(dataset_id)
        return {"experiments": list_automl_experiments(dataset_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/models/experiments/{experiment_id}")
def dataset_automl_experiment(dataset_id: str, experiment_id: str):
    try:
        item = get_automl_experiment(experiment_id)
        if str((item.get("dataset") or {}).get("id") or "") not in {"", dataset_id}:
            raise HTTPException(status_code=404, detail="Expérience introuvable pour ce dataset")
        return item
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Expérience introuvable") from exc


@router.post("/models/{model_id}/predict")
def model_predict(model_id: str, request: PredictRequest):
    try:
        return predict(model_id, request.rows)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Modèle introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/models/{model_id}/diagnostics")
def model_xai_diagnostics(model_id: str):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError("La Model Card ne référence aucun dataset")
        return model_diagnostics(model_id, load_dataframe(dataset_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Modèle ou dataset de référence introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Diagnostics XAI impossibles: {exc}") from exc


@router.post("/models/{model_id}/explain")
def model_xai_local(model_id: str, request: LocalExplanationRequest):
    try:
        return local_explanation(model_id, request.row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Modèle introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Explication locale impossible: {exc}") from exc


@router.get("/models/{model_id}/xai/capabilities")
def model_xai_capabilities(model_id: str):
    try:
        return xai_capabilities(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle introuvable",
        ) from exc


@router.post("/models/{model_id}/xai/pdp")
def model_xai_pdp(model_id: str, request: PDPRequest):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError(
                "La Model Card ne référence aucun dataset"
            )
        return partial_dependence(
            model_id,
            load_dataframe(dataset_id),
            request.features,
            grid_points=request.grid_points,
            class_label=request.class_label,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle ou dataset introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/models/{model_id}/xai/shap")
def model_xai_shap(model_id: str, request: SHAPRequest):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError(
                "La Model Card ne référence aucun dataset"
            )
        return shap_explanation(
            model_id,
            load_dataframe(dataset_id),
            row=request.row,
            max_rows=request.max_rows,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle ou dataset introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/models/{model_id}/xai/counterfactuals")
def model_xai_counterfactuals(
    model_id: str,
    request: CounterfactualRequest,
):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError(
                "La Model Card ne référence aucun dataset"
            )
        return generate_counterfactuals(
            model_id,
            load_dataframe(dataset_id),
            request.row,
            desired_class=request.desired_class,
            desired_value=request.desired_value,
            direction=request.direction,
            max_changes=request.max_changes,
            max_results=request.max_results,
            immutable_features=request.immutable_features,
            actionable_features=request.actionable_features,
            feature_constraints=request.feature_constraints,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle ou dataset introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc



@router.post("/models/{model_id}/xai/audit")
def model_xai_audit(model_id: str, request: XAIAuditRequest):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError("La Model Card ne référence aucun dataset")
        return xai_audit(
            model_id,
            load_dataframe(dataset_id),
            row=request.row,
            pdp_features=request.pdp_features,
            include_shap=request.include_shap,
            persist=request.persist,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Modèle ou dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/responsible-ai/fairness")
def model_responsible_ai_fairness(model_id: str, request: FairnessRequest):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError("La Model Card ne référence aucun dataset")
        report = fairness_report(
            model_id,
            load_dataframe(dataset_id),
            protected_columns=request.protected_columns,
            positive_label=request.positive_label,
            mode=request.mode,
            min_group_size=request.min_group_size,
        )
        if request.persist_summary:
            risk = model_risk_assessment(model_id, fairness=report)
            persist_responsible_ai_summary(
                model_id, fairness=report, risk=risk
            )
        return report
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle ou dataset de référence introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/responsible-ai/gate")
def model_responsible_ai_gate(model_id: str, request: ResponsibleAIGateRequest):
    try:
        card = get_model_card(model_id)
        dataset_id = card.get("dataset", {}).get("id")
        if not dataset_id:
            raise ValueError("La Model Card ne référence aucun dataset")
        gate = responsible_ai_gate(
            model_id,
            load_dataframe(dataset_id),
            protected_columns=request.protected_columns,
            positive_label=request.positive_label,
            mode=request.mode,
            min_group_size=request.min_group_size,
            policy=request.policy,
        )
        risk = model_risk_assessment(model_id, fairness=gate["fairness"])
        gate["risk"] = risk
        if request.persist_summary:
            persist_responsible_ai_summary(
                model_id,
                fairness=gate["fairness"],
                gate=gate,
                risk=risk,
            )
        return gate
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle ou dataset de référence introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/responsible-ai/risk")
def model_responsible_ai_risk(model_id: str, request: ResponsibleAIRiskRequest):
    try:
        fairness = None
        if request.protected_columns:
            card = get_model_card(model_id)
            dataset_id = card.get("dataset", {}).get("id")
            if not dataset_id:
                raise ValueError("La Model Card ne référence aucun dataset")
            fairness = fairness_report(
                model_id,
                load_dataframe(dataset_id),
                protected_columns=request.protected_columns,
                positive_label=request.positive_label,
                mode=request.mode,
                min_group_size=request.min_group_size,
            )
        risk = model_risk_assessment(model_id, fairness=fairness)
        if request.persist_summary:
            persist_responsible_ai_summary(
                model_id, fairness=fairness, risk=risk
            )
        return {"risk": risk, "fairness": fairness}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Modèle introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/responsible-ai/drift")
def model_responsible_ai_drift(model_id: str, request: PopulationDriftRequest):
    try:
        card = get_model_card(model_id)
        reference_dataset_id = card.get("dataset", {}).get("id")
        if not reference_dataset_id:
            raise ValueError("La Model Card ne référence aucun dataset")
        get_meta(request.current_dataset_id)
        return population_drift(
            model_id,
            load_dataframe(reference_dataset_id),
            load_dataframe(request.current_dataset_id),
            protected_columns=request.protected_columns,
            positive_label=request.positive_label,
            mode=request.mode,
            min_group_size=request.min_group_size,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle ou dataset introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/ai/capabilities")
def dataset_ai_capabilities(dataset_id: str):
    try:
        meta = get_meta(dataset_id)
        return {
            "dataset": _dataset_payload(meta),
            "engine": "deterministic_orchestrator",
            "tools": tool_registry(),
            "numeric_policy": "All numerical results come from executable tools; no LLM is used as a calculator.",
            "natural_language": "implemented_core",
            "llm_provider": "optional_not_required",
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/ai/analyze/run")
def dataset_ai_analysis_run(dataset_id: str, request: AIAnalysisRequest):
    try:
        get_meta(dataset_id)
        access = current_access_context()
        if access is not None:
            authorize_dataset(dataset_id, "analysis:run", access)
        run = submit_analysis_run(
            dataset_id,
            request.model_dump(exclude={"use_cache"}),
            use_cache=request.use_cache,
        )
        return {"run": run}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Démarrage AI Analyst impossible: {exc}") from exc


@router.get("/{dataset_id}/ai/runs/{run_id}")
def dataset_ai_analysis_run_detail(dataset_id: str, run_id: str):
    try:
        run = get_analysis_run(run_id)
        if str(run.get("dataset_id")) != dataset_id:
            raise PermissionError("Cette exécution n'appartient pas au dataset demandé.")
        assert_run_access(run)
        return {"run": run}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{dataset_id}/ai/runs/{run_id}/cancel")
def dataset_ai_analysis_cancel(dataset_id: str, run_id: str):
    try:
        run = get_analysis_run(run_id)
        if str(run.get("dataset_id")) != dataset_id:
            raise PermissionError("Cette exécution n'appartient pas au dataset demandé.")
        assert_run_access(run)
        return {"run": cancel_analysis_run(run_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{dataset_id}/ai/runs/{run_id}/events")
def dataset_ai_analysis_events(dataset_id: str, run_id: str):
    try:
        run = get_analysis_run(run_id)
        if str(run.get("dataset_id")) != dataset_id:
            raise PermissionError("Cette exécution n'appartient pas au dataset demandé.")
        assert_run_access(run)
        return StreamingResponse(
            stream_analysis_events(run_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{dataset_id}/ai/analyze")
def dataset_ai_analyze(dataset_id: str, request: AIAnalysisRequest):
    started = time.perf_counter()
    try:
        meta = get_meta(dataset_id)
        context = AnalystContext(
            dataset=_dataset_payload(meta),
            question=request.question,
            target=request.target,
            date_column=request.date_column,
            variables=request.variables,
            group=request.group,
            horizon=request.horizon,
            mode=request.mode,
            semantic_model=get_semantic_model(dataset_id, load_dataframe(dataset_id)),
        )
        result = analyze_dataset(load_dataframe(dataset_id), context)
        save_analysis(result)
        try:
            access = current_access_context()
            failed_tools = [x.get("tool") for x in result.get("executions", []) if x.get("status") != "ok"]
            record_telemetry(
                event_kind="ai", name="ai_analyst", status="completed", feature="AI Analyst",
                workspace_id=access.workspace_id if access else None, organization_id=access.organization_id if access else None,
                user_id=access.user_id if access else None, latency_ms=(time.perf_counter()-started)*1000.0,
                resource_type="analysis", resource_id=result.get("session_id"),
                metadata={"dataset_id":dataset_id,"intent":result.get("intent"),"critic_status":(result.get("critic") or {}).get("status"),"failed_tools":failed_tools,"tools_executed":(result.get("provenance") or {}).get("tools_executed",[]),"llm_used_for_numeric_calculation":False},
            )
        except Exception:
            pass
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"AI Analyst impossible: {exc}") from exc


@router.get("/{dataset_id}/ai/history")
def dataset_ai_history(dataset_id: str):
    try:
        get_meta(dataset_id)
        rows = list_analyses(dataset_id)
        return {"analyses": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/ai/history/{session_id}")
def dataset_ai_history_item(dataset_id: str, session_id: str):
    try:
        get_meta(dataset_id)
        item = get_analysis(session_id)
        if item.get("provenance", {}).get("dataset_id") != dataset_id:
            raise HTTPException(status_code=404, detail="Analyse introuvable pour ce dataset")
        return item
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analyse introuvable") from exc


@router.post("/{dataset_id}/workspace/nlq")
def dataset_workspace_nlq(dataset_id: str, request: NLQRequest):
    try:
        df = load_dataframe(dataset_id)
        return run_nlq(df, request.question, request.limit, get_semantic_model(dataset_id, df), dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"NLQ impossible: {exc}") from exc


@router.get("/{dataset_id}/dashboard")
def dataset_dashboard(dataset_id: str):
    try:
        df = load_dataframe(dataset_id)
        overview = dashboard_overview(df)
        feed = generate_insights(dataset_id, df, max_insights=8, persist=False)
        overview["insights"] = feed.get("insights", [])
        overview["insight_summary"] = feed.get("summary", {})
        overview["insight_engine_version"] = feed.get("engine_version")
        return overview
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Dashboard analytique impossible: {exc}") from exc


@router.get("/{dataset_id}/insights")
def dataset_insights(dataset_id: str, limit: int = 20):
    try:
        return generate_insights(dataset_id, load_dataframe(dataset_id), max_insights=max(1, min(int(limit), 100)), persist=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403 if isinstance(exc, PermissionError) else 400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Insight Engine impossible: {exc}") from exc


@router.post("/{dataset_id}/insights/scan")
def dataset_insights_scan(dataset_id: str, body: InsightScanRequest):
    try:
        return generate_insights(dataset_id, load_dataframe(dataset_id), max_insights=body.max_insights, persist=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403 if isinstance(exc, PermissionError) else 400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Scan d'insights impossible: {exc}") from exc


@router.get("/{dataset_id}/insights/history")
def dataset_insights_history(dataset_id: str, limit: int = 50):
    try:
        get_meta(dataset_id)
        return insight_history(dataset_id, limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/visualizations/saved")
def dataset_saved_visualizations(dataset_id: str):
    try:
        get_meta(dataset_id)
        rows = list_visualizations(dataset_id)
        return {"visualizations": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/visualizations/saved")
def dataset_save_visualization(dataset_id: str, request: SaveVisualizationRequest):
    try:
        meta = get_meta(dataset_id)
        return {"visualization": save_visualization(dataset_id, int(meta.get("version", 1)), request.title, request.visualization)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/dashboards")
def dataset_dashboards(dataset_id: str):
    try:
        get_meta(dataset_id)
        rows = list_dashboards(dataset_id)
        return {"dashboards": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/dashboards")
def dataset_dashboard_save(dataset_id: str, request: DashboardSaveRequest):
    try:
        row = save_dashboard(dataset_id, name=request.name, description=request.description, dashboard_id=request.dashboard_id, filters=request.filters, widgets=request.widgets)
        return {"dashboard": row}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset ou dashboard introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/dashboards/{dashboard_id}")
def dataset_dashboard_get(dataset_id: str, dashboard_id: str):
    try:
        meta = get_meta(dataset_id)
        row = get_dashboard_definition(dashboard_id)
        if row.get("root_id") != (meta.get("root_id") or meta["id"]):
            raise FileNotFoundError(dashboard_id)
        return {"dashboard": row}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dashboard introuvable") from exc


@router.delete("/{dataset_id}/dashboards/{dashboard_id}")
def dataset_dashboard_delete(dataset_id: str, dashboard_id: str):
    try:
        delete_dashboard(dataset_id, dashboard_id)
        return {"deleted": True, "dashboard_id": dashboard_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dashboard introuvable") from exc


@router.post("/{dataset_id}/dashboards/preview")
def dataset_dashboard_preview(dataset_id: str, request: DashboardPreviewRequest):
    try:
        return preview_dashboard(dataset_id, load_dataframe(dataset_id), filters=request.filters, widgets=request.widgets)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Aperçu dashboard impossible: {exc}") from exc


@router.get("/{dataset_id}/semantic/tables")
def dataset_semantic_tables(dataset_id: str):
    try:
        get_meta(dataset_id)
        return semantic_table_catalog(dataset_id)
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/{dataset_id}/semantic/validate")
def dataset_validate_semantic_model(dataset_id: str, body: SemanticSaveRequest):
    try:
        return validate_semantic_model(dataset_id, load_dataframe(dataset_id), body.model_dump())
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/{dataset_id}/semantic/query")
def dataset_semantic_query(dataset_id: str, body: SemanticQueryRequest):
    try:
        return query_semantic_metric(
            dataset_id, load_dataframe(dataset_id), body.metric_id, body.dimensions, body.filters,
            body.limit, body.date_dimension, body.time_grain, body.comparison, body.time_calculation,
            body.rolling_window,
        )
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{dataset_id}/semantic")
def dataset_semantic_model(dataset_id: str):
    try:
        return get_semantic_model(dataset_id, load_dataframe(dataset_id))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.post("/{dataset_id}/semantic")
def dataset_save_semantic_model(dataset_id: str, body: SemanticSaveRequest):
    try:
        return save_semantic_model(dataset_id, load_dataframe(dataset_id), body.model_dump())
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.post("/{dataset_id}/semantic/evaluate")
def dataset_evaluate_metric(dataset_id: str, body: MetricEvaluateRequest):
    try:
        return evaluate_metric(dataset_id, load_dataframe(dataset_id), body.metric_id, body.dimensions, body.filters, body.limit)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.post("/{dataset_id}/semantic/pulse")
def dataset_metric_pulse(dataset_id: str, body: MetricPulseRequest):
    try:
        return metric_pulse(dataset_id, load_dataframe(dataset_id), body.metric_id, body.date_column, body.periods)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.get("/{dataset_id}/proactive/summary")
def dataset_proactive_summary(dataset_id: str):
    try:
        get_meta(dataset_id)
        return proactive_summary(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.get("/{dataset_id}/proactive/watches")
def dataset_proactive_watches(dataset_id: str):
    try:
        get_meta(dataset_id)
        rows = proactive_list_watches(dataset_id)
        return {"watches": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/proactive/watches")
def dataset_proactive_watch_save(dataset_id: str, body: ProactiveWatchRequest):
    try:
        return proactive_save_watch(dataset_id, load_dataframe(dataset_id), body.model_dump())
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/{dataset_id}/proactive/watches/auto")
def dataset_proactive_watch_auto(dataset_id: str, body: ProactiveAutoRequest):
    try:
        rows = proactive_auto_configure(dataset_id, load_dataframe(dataset_id), body.threshold_pct, body.time_grain)
        return {"watches": rows, "count": len(rows)}
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/{dataset_id}/proactive/watches/{watch_id}")
def dataset_proactive_watch_delete(dataset_id: str, watch_id: str):
    try:
        proactive_delete_watch(dataset_id, watch_id)
        return {"deleted": True, "watch_id": watch_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Surveillance introuvable") from exc


@router.post("/{dataset_id}/proactive/scan")
def dataset_proactive_scan(dataset_id: str, body: ProactiveScanRequest):
    try:
        result = proactive_scan(dataset_id, load_dataframe(dataset_id), body.watch_ids or None, body.auto_configure)
        try:
            from app.services.tenant_access import current_access_context
            from app.services.governed_actions import dispatch_event
            ctx = current_access_context()
            if ctx:
                for alert in result.get("alerts", []):
                    dispatch_event(ctx.user_id, ctx.workspace_id, event_type="proactive_alert", event_id=str(alert.get("id")), dataset_id=dataset_id,
                                   payload={"alert_id":alert.get("id"),"metric_id":alert.get("metric_id"),"metric_label":alert.get("metric_label"),"severity":alert.get("severity"),"period":alert.get("period"),"value":alert.get("value"),"previous_value":alert.get("previous_value"),"delta_pct":alert.get("delta_pct"),"evidence":alert.get("evidence")})
        except Exception:
            pass
        return result
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{dataset_id}/proactive/inbox")
def dataset_proactive_inbox(dataset_id: str, status: str = "all", limit: int = 100):
    try:
        get_meta(dataset_id)
        rows = proactive_list_alerts(dataset_id, status, limit)
        return {"alerts": rows, "count": len(rows), "summary": proactive_summary(dataset_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/proactive/inbox/{alert_id}/status")
def dataset_proactive_alert_status(dataset_id: str, alert_id: str, body: ProactiveAlertStatusRequest):
    try:
        return proactive_update_alert_status(dataset_id, alert_id, body.status)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Alerte introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/trust")
def dataset_trust_center(dataset_id: str):
    try:
        return trust_center(dataset_id, load_dataframe(dataset_id))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.post("/{dataset_id}/root-cause")
def dataset_root_cause(
    dataset_id: str,
    body: RootCauseRequest,
):
    try:
        meta = get_meta(dataset_id)
        result = root_cause_analysis(
            load_dataframe(dataset_id),
            target=body.target,
            comparison_column=body.comparison_column,
            baseline_value=body.baseline_value,
            current_value=body.current_value,
            metric=body.metric,
            dimensions=body.dimensions,
            time_grain=body.time_grain,
            min_segment_size=body.min_segment_size,
            top_n=body.top_n,
        )
        result["provenance"] = {
            "dataset_id": dataset_id,
            "dataset_version": meta.get("version"),
            "root_id": meta.get("root_id") or meta.get("id"),
            "calculation_engine": "deterministic_root_cause",
        }
        return result
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Dataset introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/models/{model_id}/optimize-scenarios")
def model_optimize_scenarios(
    model_id: str,
    body: ScenarioOptimizeRequest,
):
    try:
        return optimize_scenarios(
            model_id,
            body.base_row,
            body.controls,
            objective=body.objective,
            target_value=body.target_value,
            desired_class=body.desired_class,
            max_candidates=body.max_candidates,
            max_results=body.max_results,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Modèle introuvable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/models/{model_id}/what-if")
def model_what_if_route(model_id: str, body: WhatIfRequest):
    try:
        return model_what_if(model_id, body.base_row, body.scenarios)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.post("/models/{model_id}/sensitivity")
def model_sensitivity_route(model_id: str, body: SensitivityRequest):
    try:
        return sensitivity_curve(model_id, body.base_row, body.feature, body.values)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.get("/{dataset_id}/reports")
def dataset_reports(dataset_id: str):
    try:
        get_meta(dataset_id)
        rows = list_reports(dataset_id)
        return {"reports": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/reports")
def dataset_report_create(dataset_id: str, request: ReportCreateRequest):
    try:
        return build_report(
            dataset_id, request.title, request.sections, request.analysis_session_id,
            template=request.template, subtitle=request.subtitle, author=request.author, organization=request.organization,
            visualization_ids=request.visualization_ids or None, auto_story=request.auto_story,
            auto_visualizations=request.auto_visualizations, max_visualizations=request.max_visualizations,
            custom_blocks=request.custom_blocks or None, block_order=request.block_order or None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset ou analyse introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Création du rapport impossible: {exc}") from exc


@router.get("/{dataset_id}/reports/{report_id}")
def dataset_report(dataset_id: str, report_id: str):
    try:
        report = get_report(report_id)
        if report.get("dataset_id") != dataset_id:
            raise HTTPException(status_code=404, detail="Rapport introuvable pour ce dataset")
        return report
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Rapport introuvable") from exc


@router.get("/{dataset_id}/reports/{report_id}/validate")
def dataset_report_validate(dataset_id: str, report_id: str):
    try:
        report = get_report(report_id)
        if report.get("dataset_id") != dataset_id:
            raise HTTPException(status_code=404, detail="Rapport introuvable pour ce dataset")
        return validate_report(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Rapport introuvable") from exc


@router.get("/{dataset_id}/reports/{report_id}/export/{fmt}")
def dataset_report_export(dataset_id: str, report_id: str, fmt: str):
    try:
        report = get_report(report_id)
        if report.get("dataset_id") != dataset_id:
            raise HTTPException(status_code=404, detail="Rapport introuvable pour ce dataset")
        ctx = current_access_context()
        if ctx is not None:
            gate = publication_gate(ctx.workspace_id, dataset_id)
            if not gate.get("allowed", True):
                names = ", ".join(str(x.get("name") or x.get("contract_id")) for x in gate.get("blockers", []))
                raise HTTPException(status_code=409, detail=f"Export bloqué par le Data Reliability Gate: {names or 'contrat critique en échec'}")
        path = export_report(report_id, fmt)
        media = {"pdf":"application/pdf","docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document","html":"text/html","md":"text/markdown","markdown":"text/markdown"}.get(fmt.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media, filename=path.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Rapport introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/versions")
def dataset_versions(dataset_id: str):
    try:
        current = get_meta(dataset_id)
        versions = list_versions(dataset_id)
        lineage_ids = {m["id"] for m in get_lineage(dataset_id)}
        return {
            "current_id": dataset_id,
            "root_id": current.get("root_id", current["id"]),
            "versions": [
                {
                    "id": m["id"],
                    "version": m.get("version", 1),
                    "name": m.get("original_name"),
                    "created_at": m.get("created_at"),
                    "parent_id": m.get("parent_id"),
                    "operation": m.get("operation"),
                    "in_lineage": m["id"] in lineage_ids,
                }
                for m in versions
            ],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/transform")
def dataset_transform(dataset_id: str, request: TransformRequest):
    try:
        source = load_dataframe(dataset_id)
        transformed, operation = apply_operation(source, request.operation)
        meta = save_dataframe_version(dataset_id, transformed, operation)
        return _bundle(meta, transformed)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Transformation impossible: {exc}") from exc


@router.post("/{dataset_id}/combine")
def dataset_combine(dataset_id: str, request: CombineRequest):
    try:
        left = load_dataframe(dataset_id)
        right = load_dataframe(request.other_dataset_id)
        combined, operation = combine_dataframes(left, right, request.operation)
        operation.setdefault("params", {})["other_dataset_id"] = request.other_dataset_id
        operation["params"]["other_dataset_version"] = get_meta(request.other_dataset_id).get("version", 1)
        meta = save_dataframe_version(dataset_id, combined, operation)
        return _bundle(meta, combined)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset source ou secondaire introuvable") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Combinaison impossible: {exc}") from exc


@router.get("/{dataset_id}/pipelines")
def dataset_pipelines(dataset_id: str):
    try:
        get_meta(dataset_id)
        return {"pipelines": list_pipelines()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/pipelines")
def dataset_save_pipeline(dataset_id: str, request: PipelineSaveRequest):
    try:
        return {"pipeline": save_lineage_as_pipeline(dataset_id, request.name), "pipelines": list_pipelines()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dataset_id}/pipelines/{pipeline_id}/validate")
def dataset_validate_pipeline(dataset_id: str, pipeline_id: str, request: PipelineRunRequest | None = None):
    try:
        get_meta(dataset_id)
        return validate_pipeline(dataset_id, pipeline_id, (request.bindings if request else {}))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset ou pipeline introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Validation du pipeline impossible: {exc}") from exc


@router.post("/{dataset_id}/pipelines/{pipeline_id}/run")
def dataset_run_pipeline(dataset_id: str, pipeline_id: str, request: PipelineRunRequest | None = None):
    try:
        result = run_pipeline(dataset_id, pipeline_id, (request.bindings if request else {}))
        meta = get_meta(result["dataset_id"])
        return {**_bundle(meta), "pipeline_run": result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset ou pipeline introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Exécution du pipeline impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/regression")
def dataset_regression(dataset_id: str, request: RegressionRequest):
    try:
        return regression_analysis(load_dataframe(dataset_id), request.dependent, request.independents)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Régression impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/anova")
def dataset_anova(dataset_id: str, request: AnovaRequest):
    try:
        return anova_analysis(load_dataframe(dataset_id), request.response, request.factor1, request.factor2)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"ANOVA impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/pca")
def dataset_pca(dataset_id: str, request: PCARequest):
    try:
        return pca_analysis(load_dataframe(dataset_id), request.columns, request.scale)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"ACP impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/clustering")
def dataset_clustering(dataset_id: str, request: ClusterRequest):
    try:
        return clustering_analysis(load_dataframe(dataset_id), request.columns, request.k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Clustering impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/correlations")
def dataset_correlations(dataset_id: str, request: CorrelationRequest):
    try:
        return correlation_analysis(load_dataframe(dataset_id), request.columns, request.method)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dataset_id}/analysis/statistical-test")
def dataset_statistical_test(dataset_id: str, request: StatisticalTestRequest):
    try:
        return statistical_test(load_dataframe(dataset_id), request.test, value=request.value, group=request.group, x=request.x, y=request.y, paired=request.paired)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Test statistique impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/test-advisor")
def dataset_test_advisor(dataset_id: str, request: TestAdvisorRequest):
    try:
        return test_advisor(load_dataframe(dataset_id), value=request.value, group=request.group, x=request.x, y=request.y, paired=request.paired)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/workspace/engine")
def dataset_engine(dataset_id: str):
    try:
        return engine_info(load_dataframe(dataset_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/workspace/sql")
def dataset_sql(dataset_id: str, request: SQLRequest):
    try:
        return run_sql(load_dataframe(dataset_id), request.sql, request.limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Exécution SQL impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/forecast")
def dataset_forecast(dataset_id: str, request: ForecastRequest):
    try:
        return forecast_series(
            load_dataframe(dataset_id), request.date_column, request.target, request.horizon, request.frequency, request.method,
            request.backtest_windows, request.interval_level, request.missing_strategy, request.selection_metric,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Forecasting impossible: {exc}") from exc


@router.post("/{dataset_id}/analysis/anomalies")
def dataset_anomalies(dataset_id: str, request: AnomalyRequest):
    try:
        return detect_anomalies(load_dataframe(dataset_id), request.columns, request.method, request.contamination, request.threshold)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Détection d'anomalies impossible: {exc}") from exc


@router.post("/{dataset_id}/visualizations/recommend")
def dataset_visualization_recommend(dataset_id: str, request: VisualizationRecommendRequest):
    try:
        return {"recommendations": recommend_visualizations(load_dataframe(dataset_id), request.columns)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc


@router.post("/{dataset_id}/visualizations/build")
def dataset_visualization_build(dataset_id: str, request: VisualizationRequest):
    try:
        return build_visualization(
            load_dataframe(dataset_id), chart_type=request.chart_type, x=request.x, y=request.y,
            color=request.color, size=request.size, facet=request.facet, aggregation=request.aggregation,
            bins=request.bins, columns=request.columns, cluster_k=request.cluster_k, max_points=request.max_points,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Visualisation impossible: {exc}") from exc


@router.post("/{dataset_id}/visualizations/edit")
def dataset_visualization_edit(dataset_id: str, request: VisualizationEditRequest):
    try:
        return edit_visualization(load_dataframe(dataset_id), request.visualization, request.instruction)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Édition de visualisation impossible: {exc}") from exc


@router.post("/{dataset_id}/visualizations/compose")
def dataset_visualization_compose(dataset_id: str, request: VisualizationComposeRequest):
    try:
        return build_visualization_composition(
            load_dataframe(dataset_id), columns=request.columns, intent=request.intent, max_views=request.max_views,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Composition de visualisations impossible: {exc}") from exc
