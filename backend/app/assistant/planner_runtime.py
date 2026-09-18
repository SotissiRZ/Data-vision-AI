from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import AgentIntent, AgentPlanStep, AssistantContext


class PlannerProvider(Protocol):
    """
    Contract for a future LLM-backed planner.

    A provider returns tool plans only. The plan still passes through the
    deterministic Plan Validator and Tool Registry before execution.
    """

    def plan(
        self,
        *,
        message: str,
        intent: AgentIntent,
        context: AssistantContext,
        attachment_ids: list[str],
    ) -> list[AgentPlanStep]:
        ...


@dataclass
class DeterministicPlanner:
    """
    Safe local fallback.

    It creates conservative plans from recognized intents. It deliberately
    avoids inventing column names or statistical choices that are not present
    in the user's request/context.
    """

    def plan(
        self,
        *,
        message: str,
        intent: AgentIntent,
        context: AssistantContext,
        attachment_ids: list[str],
    ) -> list[AgentPlanStep]:
        name = intent.name

        if name == "analyze_dataset":
            return [
                AgentPlanStep(
                    tool="profile_dataset",
                    label="Profiler le dataset",
                    reason="Comprendre structure, types et distributions.",
                    args={},
                ),
                AgentPlanStep(
                    tool="inspect_missing_values",
                    label="Évaluer les valeurs manquantes",
                    reason="Vérifier la qualité avant analyse.",
                    args={},
                ),
            ]

        if name == "data_quality":
            return [
                AgentPlanStep(
                    tool="inspect_missing_values",
                    label="Diagnostiquer les valeurs manquantes",
                    args={},
                ),
            ]

        if name == "visualize":
            # A chart cannot be invented safely without variables.
            selected = context.selectedEntity
            if selected and selected.type in {"column", "variable"} and selected.id:
                return [
                    AgentPlanStep(
                        tool="create_visualization",
                        label=f"Visualiser {selected.label or selected.id}",
                        args={
                            "chart_type": "histogram",
                            "x": selected.id,
                        },
                    )
                ]
            return []

        if name == "predict_target":
            target = intent.entities.get("target")
            task = intent.entities.get("ml_task")
            if not target or not task:
                return []
            return [
                AgentPlanStep(
                    tool="inspect_data_leakage",
                    label="Contrôler les fuites de données",
                    args={"target": target},
                ),
                AgentPlanStep(
                    tool="run_automl",
                    label=f"Comparer des modèles pour {target}",
                    args={
                        "task": task,
                        "target": target,
                        "explain": True,
                    },
                ),
            ]

        if name == "explain_model":
            if not context.activeModelId:
                return []
            return [
                AgentPlanStep(
                    tool="explain_model",
                    label="Expliquer le modèle",
                    args={"method": "feature_importance"},
                )
            ]

        if name == "report":
            return [
                AgentPlanStep(
                    tool="generate_report",
                    label="Générer le rapport",
                    args={
                        "title": "Rapport DataVision",
                        "format": "pdf",
                        "include_methodology": True,
                        "include_provenance": True,
                        "include_visualizations": True,
                    },
                )
            ]

        if name == "file_analysis" and attachment_ids:
            return [
                AgentPlanStep(
                    tool="inspect_uploaded_file",
                    label="Inspecter le fichier",
                    args={
                        "file_id": attachment_ids[0],
                        "parse_tables": True,
                    },
                )
            ]

        # compare_groups and GIS require explicit variables/layers; the local
        # fallback refuses to guess them.
        return []
