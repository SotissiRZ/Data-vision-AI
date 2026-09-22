from pathlib import Path

from app.assistant.models import AssistantContext, AssistantEvent, SelectedEntity
from app.assistant.privacy import AIDataPolicy, project_context_for_model


ROOT = Path(__file__).resolve().parents[3]


def test_context_panel_is_scrollable_and_exposes_complete_snapshot():
    component = (
        ROOT / "frontend/components/assistant/FloatingDataVisionAssistant.tsx"
    ).read_text(encoding="utf-8")
    css = (
        ROOT / "frontend/components/assistant/FloatingDataVisionAssistant.module.css"
    ).read_text(encoding="utf-8")

    assert "Contexte technique complet" in component
    assert "technicalContextSnapshot" in component
    assert "Schéma du dataset" in component
    assert "Activité récente" in component
    assert "Gouvernance & accès" in component
    assert "Analyse & modèle" in component
    assert "availableFieldCount" in component
    assert "overflow-y: auto" in css
    assert ".contextSection" in css
    assert ".contextRaw" in css


def test_host_context_contains_richer_project_dataset_and_model_facts():
    page = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    for key in [
        "areaLabel",
        "workspaceName",
        "workspaceRole",
        "operationState",
        "accessMode",
        "accessGoverned",
        "accessPolicyCount",
        "modelTask",
        "modelAlgorithm",
        "modelPrimaryMetric",
        "modelFeatureCount",
        "trustScore",
        "trustGrade",
    ]:
        assert key in page
    assert "metadata:" in page
    assert "selectedColumnProfile?.dtype" in page


def test_safe_semantic_projection_includes_richer_context_without_raw_ui_state():
    context = AssistantContext(
        workspaceId="ws-1",
        screen="model",
        activeDatasetId="ds-1",
        activeDatasetVersionId="3",
        activeModelId="model-7",
        selectedEntity=SelectedEntity(
            type="column",
            id="revenue",
            label="Revenue",
            metadata={"dtype": "float64", "missing": 0},
        ),
        uiState={
            "areaLabel": "Modéliser",
            "workspaceRole": "analyst",
            "datasetName": "Financial Sample.xlsx",
            "rowCount": 700,
            "columnCount": 8,
            "duplicateCount": 2,
            "missingCells": 4,
            "qualityScore": 80,
            "qualityIssuesCount": 3,
            "numericColumnCount": 5,
            "categoricalColumnCount": 3,
            "accessMode": "enterprise",
            "accessGoverned": True,
            "accessRole": "analyst",
            "accessPolicyCount": 2,
            "target": "Profit",
            "algorithm": "auto",
            "modelTask": "regression",
            "modelAlgorithm": "xgboost",
            "modelPrimaryMetric": "rmse",
            "modelFeatureCount": 7,
            "trustScore": 91,
            "trustGrade": "A",
            "temporalCoverage": {
                "detected": True,
                "primary": {
                    "column": "Date",
                    "start": "2024-01-01",
                    "end": "2024-12-31",
                    "kind": "date",
                    "confidence": 0.98,
                },
            },
            "rows": [{"secret": "must-never-leak"}],
        },
        recentEvents=[AssistantEvent(type="dataset.loaded")],
    )

    projected = project_context_for_model(
        context,
        external=False,
        policy=AIDataPolicy(),
    )

    assert projected["datasetName"] == "Financial Sample.xlsx"
    assert projected["rowCount"] == 700
    assert projected["duplicateCount"] == 2
    assert projected["modelTask"] == "regression"
    assert projected["accessPolicyCount"] == 2
    assert projected["temporal_coverage"]["primary"]["column"] == "Date"
    assert "rows" not in projected
    assert "uiState" not in projected


def test_external_projection_still_respects_column_name_privacy():
    context = AssistantContext(
        activeDatasetId="ds-1",
        uiState={
            "datasetName": "Sensitive Dataset",
            "target": "Salary",
            "temporalCoverage": {
                "detected": True,
                "primary": {"column": "HireDate", "start": "2024-01-01", "end": "2024-12-31"},
            },
        },
    )
    projected = project_context_for_model(
        context,
        external=True,
        policy=AIDataPolicy(
            allow_external_ai=True,
            include_column_names_external=False,
        ),
    )

    assert projected["datasetName"] is None
    assert projected["target"] is None
    assert projected["temporal_coverage"]["primary"]["column"] is None


def test_generated_artifacts_update_active_chart_and_report_context():
    effects = (ROOT / "frontend/lib/assistant/effects.ts").read_text(encoding="utf-8")
    assert "activeChartId" in effects
    assert "activeReportId" in effects
    assert "assistant.chart.changed" in effects
    assert "assistant.report.changed" in effects
