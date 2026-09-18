from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowTemplate:
    id: str
    title: str
    description: str
    steps: tuple[str, ...]


WORKFLOWS: dict[str, WorkflowTemplate] = {
    "analyze_dataset": WorkflowTemplate(
        id="analyze_dataset",
        title="Analyse générale d'un dataset",
        description="Profilage, qualité, exploration, visualisation et synthèse.",
        steps=(
            "profile_dataset",
            "inspect_missing_values",
            "create_visualization",
            "generate_report",
        ),
    ),
    "compare_groups": WorkflowTemplate(
        id="compare_groups",
        title="Comparer des groupes",
        description="Diagnostic des variables puis test statistique adapté.",
        steps=(
            "profile_dataset",
            "run_statistical_test",
            "create_visualization",
        ),
    ),
    "predict_target": WorkflowTemplate(
        id="predict_target",
        title="Prédire une cible",
        description="Contrôles de fuite, AutoML, explicabilité et rapport.",
        steps=(
            "inspect_data_leakage",
            "run_automl",
            "explain_model",
            "generate_report",
        ),
    ),
    "geospatial_analysis": WorkflowTemplate(
        id="geospatial_analysis",
        title="Analyse géospatiale",
        description="Contrôle/reprojection et opérations spatiales.",
        steps=(
            "gis_reproject",
            "gis_spatial_join",
            "create_visualization",
        ),
    ),
}


def list_workflows() -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "steps": list(item.steps),
        }
        for item in WORKFLOWS.values()
    ]
