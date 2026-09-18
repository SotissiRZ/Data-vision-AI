import time
from fastapi import APIRouter, File, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.storage import (
    save_upload, load_dataframe, get_meta, save_dataframe_version,
    get_lineage, list_versions, list_dataset_catalog,
)
from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.modeling import train_model, automl_train, predict, get_model_card, list_model_cards
from app.services.decision import decision_support
from app.services.exploration import analyze_column, preview_dataframe
from app.services.advanced_analysis import regression_analysis, anova_analysis, pca_analysis, clustering_analysis
from app.services.preparation import apply_operation, combine_dataframes
from app.services.pipelines import list_pipelines, save_lineage_as_pipeline, run_pipeline
from app.services.statistics_engine import correlation_analysis, statistical_test, test_advisor
from app.services.data_workspace import engine_info, run_sql
from app.services.visualization import build_visualization, recommend_visualizations
from app.services.forecasting import forecast_series
from app.services.anomaly_detection import detect_anomalies
from app.services.xai import model_diagnostics, local_explanation
from app.services.ai_analyst import AnalystContext, analyze_dataset, tool_registry
from app.services.analysis_history import save_analysis, list_analyses, get_analysis
from app.services.nlq_sql import run_nlq
from app.services.report_builder import build_report, list_reports, get_report, export_report
from app.services.dashboard import dashboard_overview
from app.services.saved_visualizations import save_visualization, list_visualizations
from app.services.dashboard_builder import save_dashboard, list_dashboards, get_dashboard_definition, delete_dashboard, preview_dashboard
from app.services.semantic_layer import (
    get_semantic_model, save_semantic_model, evaluate_metric, metric_pulse,
    semantic_table_catalog, validate_semantic_model, query_semantic_metric,
)
from app.services.trust_center import trust_center
from app.services.decision_lab import model_what_if, sensitivity_curve
from app.services.tenant_access import access_summary, current_access_context
from app.services.data_reliability import publication_gate
from app.services.operational_intelligence import record_telemetry
from app.services.proactive_intelligence import (
    list_watches as proactive_list_watches, save_watch as proactive_save_watch, delete_watch as proactive_delete_watch,
    auto_configure_watches as proactive_auto_configure, scan as proactive_scan, list_alerts as proactive_list_alerts,
    update_alert_status as proactive_update_alert_status, proactive_summary,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


class TrainRequest(BaseModel):
    target: str
    task: str = Field(default="auto", pattern="^(auto|classification|regression)$")
    algorithm: str = Field(default="auto", pattern="^(auto|linear_regression|ridge|logistic_regression|random_forest|extra_trees|gradient_boosting|hist_gradient_boosting)$")


class AutoMLRequest(BaseModel):
    target: str
    task: str = Field(default="auto", pattern="^(auto|classification|regression)$")
    primary_metric: str = Field(default="auto", pattern="^(auto|accuracy|balanced_accuracy|f1_weighted|roc_auc|rmse|mae|r2)$")
    cv_folds: int = Field(default=5, ge=2, le=10)
    tune: bool = True
    max_candidates: int = Field(default=5, ge=2, le=6)


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
    aggregation: str = "none"
    bins: int = Field(default=20, ge=5, le=80)


class VisualizationRecommendRequest(BaseModel):
    columns: list[str] = []


class ForecastRequest(BaseModel):
    date_column: str
    target: str
    horizon: int = Field(default=12, ge=1, le=365)
    frequency: str = Field(default="auto", pattern="^(auto|daily|weekly|monthly|quarterly|yearly)$")
    method: str = Field(default="auto", pattern="^(auto|naive|seasonal_naive|linear_trend|exponential_smoothing)$")


class AnomalyRequest(BaseModel):
    columns: list[str] = []
    method: str = Field(default="auto", pattern="^(auto|iqr|robust_z|isolation_forest)$")
    contamination: float = Field(default=0.05, ge=0.001, le=0.4)
    threshold: float = Field(default=3.5, ge=1.0, le=10.0)


class LocalExplanationRequest(BaseModel):
    row: dict




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
        meta = save_upload(file.filename or "dataset", content)
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
                bind_dataset(user["id"], workspace_id, meta["id"])
                ws = get_workspace(user["id"], workspace_id)
                record_event("dataset.upload", user_id=user["id"], organization_id=ws["organization_id"], workspace_id=workspace_id, resource_type="dataset", resource_id=meta["id"], payload={"name": meta["original_name"]})
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=401, detail=f"Contexte workspace invalide: {exc}") from exc
        return {"dataset": {"id": meta["id"], "name": meta["original_name"], "format": meta["extension"]}}
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
        return result.__dict__
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Entraînement impossible: {exc}") from exc


@router.post("/{dataset_id}/models/automl")
def dataset_automl(dataset_id: str, request: AutoMLRequest):
    try:
        meta = get_meta(dataset_id)
        return automl_train(
            load_dataframe(dataset_id), target=request.target, task=request.task,
            primary_metric=request.primary_metric, cv_folds=request.cv_folds, tune=request.tune,
            max_candidates=request.max_candidates, dataset_context=_dataset_payload(meta),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"AutoML impossible: {exc}") from exc


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"NLQ impossible: {exc}") from exc


@router.get("/{dataset_id}/dashboard")
def dataset_dashboard(dataset_id: str):
    try:
        return dashboard_overview(load_dataframe(dataset_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Dashboard analytique impossible: {exc}") from exc


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


@router.post("/{dataset_id}/pipelines/{pipeline_id}/run")
def dataset_run_pipeline(dataset_id: str, pipeline_id: str):
    try:
        result = run_pipeline(dataset_id, pipeline_id)
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
        return forecast_series(load_dataframe(dataset_id), request.date_column, request.target, request.horizon, request.frequency, request.method)
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
        return build_visualization(load_dataframe(dataset_id), chart_type=request.chart_type, x=request.x, y=request.y, color=request.color, aggregation=request.aggregation, bins=request.bins)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Visualisation impossible: {exc}") from exc
