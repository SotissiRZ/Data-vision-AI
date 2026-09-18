from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ProfileDatasetArgs(BaseModel):
    include_distributions: bool = True
    sample_rows: int = Field(default=5000, ge=100, le=100000)


class InspectMissingValuesArgs(BaseModel):
    columns: list[str] | None = None
    include_patterns: bool = True


class ApplyTransformArgs(BaseModel):
    operation: Literal[
        "filter",
        "rename",
        "cast",
        "impute",
        "drop_duplicates",
        "normalize",
        "standardize",
        "encode",
        "outlier_treatment",
        "feature_engineering",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    create_new_version: bool = True


class MergeDatasetsArgs(BaseModel):
    right_dataset_id: str
    how: Literal["inner", "left", "right", "outer"] = "inner"
    left_on: list[str]
    right_on: list[str]
    suffixes: tuple[str, str] = ("_x", "_y")

    @model_validator(mode="after")
    def validate_keys(self):
        if len(self.left_on) != len(self.right_on):
            raise ValueError("left_on et right_on doivent avoir le même nombre de clés.")
        return self


class DeleteColumnArgs(BaseModel):
    columns: list[str] = Field(min_length=1)
    create_new_version: bool = True


class StatisticalTestArgs(BaseModel):
    test: Literal[
        "t_test",
        "welch",
        "mann_whitney",
        "wilcoxon",
        "chi_square",
        "fisher",
        "anova",
        "kruskal_wallis",
        "pearson",
        "spearman",
        "normality",
        "homoscedasticity",
    ]
    outcome: str | None = None
    group: str | None = None
    variables: list[str] = Field(default_factory=list)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    alternative: Literal["two-sided", "less", "greater"] = "two-sided"


class RegressionArgs(BaseModel):
    kind: Literal["linear", "multiple_linear", "logistic", "regularized"]
    target: str
    features: list[str] = Field(min_length=1)
    regularization: Literal["none", "l1", "l2", "elasticnet"] = "none"


class CreateVisualizationArgs(BaseModel):
    chart_type: Literal[
        "bar",
        "line",
        "area",
        "scatter",
        "histogram",
        "boxplot",
        "violin",
        "heatmap",
        "correlation_matrix",
        "density",
        "bubble",
        "treemap",
        "sankey",
        "map",
        "time_series",
        "pca",
        "cluster",
    ]
    x: str | None = None
    y: str | None = None
    color: str | None = None
    size: str | None = None
    facet: str | None = None
    aggregation: str | None = None
    title: str | None = None


class AutoMLArgs(BaseModel):
    task: Literal["classification", "regression", "clustering", "forecasting"]
    target: str | None = None
    features: list[str] | None = None
    metric: str | None = None
    validation: Literal["holdout", "cross_validation", "time_split"] = "cross_validation"
    max_models: int = Field(default=8, ge=1, le=50)
    explain: bool = True

    @model_validator(mode="after")
    def target_required(self):
        if self.task in {"classification", "regression", "forecasting"} and not self.target:
            raise ValueError("Une cible est requise pour cette tâche AutoML.")
        return self


class ExplainModelArgs(BaseModel):
    method: Literal[
        "feature_importance",
        "shap_global",
        "shap_local",
        "partial_dependence",
        "permutation_importance",
        "confusion_matrix",
        "calibration",
        "counterfactual",
    ]
    row_id: str | int | None = None
    feature: str | None = None


class ReprojectLayerArgs(BaseModel):
    layer_id: str
    target_crs: str


class SpatialJoinArgs(BaseModel):
    left_layer_id: str
    right_layer_id: str
    predicate: Literal[
        "intersects",
        "within",
        "contains",
        "touches",
        "crosses",
        "overlaps",
        "nearest",
    ] = "intersects"
    how: Literal["left", "inner"] = "left"


class BufferLayerArgs(BaseModel):
    layer_id: str
    distance: float = Field(gt=0)
    unit: Literal["meters", "kilometers", "feet", "miles"] = "meters"
    dissolve: bool = False


class GenerateReportArgs(BaseModel):
    title: str
    format: Literal["pdf", "docx", "html", "markdown", "pptx"] = "pdf"
    include_methodology: bool = True
    include_provenance: bool = True
    include_visualizations: bool = True


class InspectUploadedFileArgs(BaseModel):
    file_id: str
    parse_tables: bool = True
    max_pages: int | None = Field(default=None, ge=1, le=500)


class ExportDatasetArgs(BaseModel):
    format: Literal["csv", "xlsx", "parquet", "json", "geojson"]
    columns: list[str] | None = None
    include_metadata: bool = True


class SendExternalMessageArgs(BaseModel):
    connector_id: str
    destination: str
    subject: str | None = None
    message: str


TOOL_CONTRACTS: dict[str, type[BaseModel]] = {
    "profile_dataset": ProfileDatasetArgs,
    "inspect_missing_values": InspectMissingValuesArgs,
    "apply_reversible_transform": ApplyTransformArgs,
    "merge_datasets": MergeDatasetsArgs,
    "delete_column": DeleteColumnArgs,
    "run_statistical_test": StatisticalTestArgs,
    "run_regression": RegressionArgs,
    "create_visualization": CreateVisualizationArgs,
    "run_automl": AutoMLArgs,
    "explain_model": ExplainModelArgs,
    "gis_reproject": ReprojectLayerArgs,
    "gis_spatial_join": SpatialJoinArgs,
    "gis_buffer": BufferLayerArgs,
    "generate_report": GenerateReportArgs,
    "inspect_uploaded_file": InspectUploadedFileArgs,
    "export_dataset": ExportDatasetArgs,
    "send_external_message": SendExternalMessageArgs,
}


def validate_tool_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    model = TOOL_CONTRACTS.get(tool_name)
    if model is None:
        return dict(args)
    value = model.model_validate(args)
    return value.model_dump(mode="json")


def tool_json_schema(tool_name: str) -> dict[str, Any] | None:
    model = TOOL_CONTRACTS.get(tool_name)
    return model.model_json_schema() if model is not None else None
