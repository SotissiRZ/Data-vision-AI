from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AssistantContext


@dataclass(frozen=True)
class AIDataPolicy:
    allow_external_ai: bool = False
    include_column_names_external: bool = True
    include_sample_values_external: bool = False
    include_row_data_external: bool = False
    max_recent_events_external: int = 5


def project_context_for_model(
    context: AssistantContext,
    *,
    external: bool,
    policy: AIDataPolicy,
) -> dict[str, Any]:
    """
    Project only governed semantic context to a model.

    Raw rows and arbitrary uiState are deliberately excluded.
    Dataset schema may be included without sample values.
    """
    projected: dict[str, Any] = {
        "workspace_id": context.workspaceId,
        "route": context.route,
        "screen": context.screen,
        "active_dataset_id": context.activeDatasetId,
        "active_dataset_version_id": context.activeDatasetVersionId,
        "active_model_id": context.activeModelId,
        "active_chart_id": context.activeChartId,
        "active_report_id": context.activeReportId,
    }

    if context.selectedEntity:
        selected = {
            "type": context.selectedEntity.type,
            "id": context.selectedEntity.id,
            "label": context.selectedEntity.label,
        }
        if external and not policy.include_column_names_external:
            if selected["type"] in {"column", "variable"}:
                selected["id"] = None
                selected["label"] = None
        projected["selected_entity"] = selected

    dataset_schema = (
        context.uiState.get("datasetSchema")
        if context.uiState
        else None
    )
    if isinstance(dataset_schema, list):
        safe_schema = []
        for item in dataset_schema[:250]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            dtype = item.get("dtype")
            if external and not policy.include_column_names_external:
                name = None
            safe_schema.append(
                {
                    "name": name,
                    "dtype": dtype,
                }
            )
        projected["dataset_schema"] = safe_schema

    if context.uiState:
        safe_scalar_keys = (
            "areaKey",
            "areaLabel",
            "workspaceRole",
            "datasetName",
            "datasetVersion",
            "datasetCreatedAt",
            "rowCount",
            "columnCount",
            "duplicateCount",
            "missingCells",
            "qualityScore",
            "qualityIssuesCount",
            "numericColumnCount",
            "categoricalColumnCount",
            "accessMode",
            "accessGoverned",
            "accessRole",
            "accessPolicyCount",
            "target",
            "algorithm",
            "modelTask",
            "modelAlgorithm",
            "modelPrimaryMetric",
            "modelFeatureCount",
            "trustScore",
            "trustGrade",
        )
        name_like_keys = {"datasetName", "target"}
        for key in safe_scalar_keys:
            value = context.uiState.get(key)
            if value is None:
                continue
            if (
                external
                and key in name_like_keys
                and not policy.include_column_names_external
            ):
                projected[key] = None
            else:
                projected[key] = value

        temporal = context.uiState.get("temporalCoverage")
        if isinstance(temporal, dict):
            primary = temporal.get("primary")
            if isinstance(primary, dict):
                projected["temporal_coverage"] = {
                    "detected": bool(temporal.get("detected")),
                    "primary": {
                        "column": (
                            None
                            if external and not policy.include_column_names_external
                            else primary.get("column")
                        ),
                        "start": primary.get("start"),
                        "end": primary.get("end"),
                        "kind": primary.get("kind"),
                        "confidence": primary.get("confidence"),
                    },
                }

    max_events = len(context.recentEvents)
    if external:
        max_events = min(
            max_events,
            policy.max_recent_events_external,
        )

    projected["recent_events"] = [
        {
            "type": event.type,
            "severity": event.severity,
        }
        for event in context.recentEvents[-max_events:]
    ]

    return projected
