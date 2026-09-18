from fastapi import APIRouter, File, HTTPException, UploadFile
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
    }


@router.post("")
async def upload_dataset(file: UploadFile = File(...)):
    try:
        content = await file.read()
        meta = save_upload(file.filename or "dataset", content)
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
        )
        result = analyze_dataset(load_dataframe(dataset_id), context)
        save_analysis(result)
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
        return run_nlq(load_dataframe(dataset_id), request.question, request.limit)
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
        return preview_dashboard(load_dataframe(dataset_id), filters=request.filters, widgets=request.widgets)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Aperçu dashboard impossible: {exc}") from exc


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
