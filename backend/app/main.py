from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.datasets import router as datasets_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.9.0", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "product": settings.app_name, "version": "0.9.0"}


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
        ],
        "partial": ["audit", "shap", "fairness", "nlq"],
        "planned": [
            "multi_agent", "r_workspace", "collaboration", "enterprise_governance",
        ],
    }


app.include_router(datasets_router, prefix="/api/v1")
