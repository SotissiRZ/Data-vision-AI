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
            x = intent.entities.get("x") or intent.entities.get("column")
            y = intent.entities.get("y")
            selected = context.selectedEntity

            if not x and selected and selected.type in {"column", "variable"}:
                x = selected.id

            if x and y:
                return [
                    AgentPlanStep(
                        tool="create_visualization",
                        label=f"Comparer {x} et {y}",
                        args={
                            "chart_type": "scatter",
                            "x": x,
                            "y": y,
                        },
                    )
                ]

            if x:
                return [
                    AgentPlanStep(
                        tool="create_visualization",
                        label=f"Visualiser {x}",
                        args={
                            "chart_type": "histogram",
                            "x": x,
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


        if name == "fairness_analysis":
            if not context.activeModelId:
                return []
            protected = intent.entities.get("protected_columns")
            selected = context.selectedEntity
            if not protected and selected and selected.type in {"column", "variable"} and selected.id:
                protected = [selected.id]
            if not isinstance(protected, list) or not protected:
                return []
            return [
                AgentPlanStep(
                    tool="evaluate_model_fairness",
                    label="Auditer les performances par groupe",
                    args={
                        "protected_columns": protected[:3],
                        "positive_label": intent.entities.get("positive_label"),
                        "mode": intent.entities.get("mode", "both"),
                        "min_group_size": intent.entities.get("min_group_size", 20),
                    },
                )
            ]

        if name == "model_risk":
            if not context.activeModelId:
                return []
            protected = intent.entities.get("protected_columns")
            selected = context.selectedEntity
            if not protected and selected and selected.type in {"column", "variable"} and selected.id:
                protected = [selected.id]
            return [
                AgentPlanStep(
                    tool="assess_model_risk",
                    label="Évaluer le risque de gouvernance du modèle",
                    args={
                        "protected_columns": protected[:3] if isinstance(protected, list) else None,
                        "positive_label": intent.entities.get("positive_label"),
                    },
                )
            ]

        if name == "root_cause_analysis":
            target = intent.entities.get("target")
            comparison = (
                intent.entities.get("comparison_column")
                or intent.entities.get("group")
                or intent.entities.get("date_column")
            )
            if not target or not comparison:
                return []
            return [
                AgentPlanStep(
                    tool="run_root_cause_analysis",
                    label=f"Décomposer l'écart de {target}",
                    args={
                        "target": target,
                        "comparison_column": comparison,
                        "metric": intent.entities.get("metric", "mean"),
                        "baseline_value": intent.entities.get("baseline_value"),
                        "current_value": intent.entities.get("current_value"),
                        "dimensions": intent.entities.get("dimensions"),
                    },
                )
            ]

        if name == "optimize_scenarios":
            if not context.activeModelId:
                return []
            controls = intent.entities.get("controls")
            base_row = intent.entities.get("base_row")
            if not isinstance(controls, dict) or not isinstance(base_row, dict):
                return []
            return [
                AgentPlanStep(
                    tool="optimize_decision_scenarios",
                    label="Optimiser les scénarios de décision",
                    args={
                        "base_row": base_row,
                        "controls": controls,
                        "objective": intent.entities.get("objective", "maximize"),
                        "target_value": intent.entities.get("target_value"),
                        "desired_class": intent.entities.get("desired_class"),
                    },
                )
            ]
        if name == "model_registry":
            if not context.activeModelId:
                return []
            requested_stage = intent.entities.get("target_stage")
            if requested_stage in {"draft", "staging", "production", "retired"}:
                return [
                    AgentPlanStep(
                        tool="transition_model_stage",
                        label=f"Passer le modèle en {requested_stage}",
                        args={
                            "target_stage": requested_stage,
                            "note": intent.entities.get("note", ""),
                        },
                    )
                ]
            return [
                AgentPlanStep(
                    tool="get_model_registry_status",
                    label="Lire le statut MLOps du modèle",
                    args={},
                )
            ]

        if name == "monitor_model":
            if not context.activeModelId or not context.activeDatasetId:
                return []
            return [
                AgentPlanStep(
                    tool="monitor_model_health",
                    label="Surveiller la santé du modèle",
                    args={"current_dataset_id": context.activeDatasetId},
                )
            ]

        if name == "retraining_check":
            if not context.activeModelId:
                return []
            return [
                AgentPlanStep(
                    tool="check_model_retraining",
                    label="Évaluer la nécessité d'un réentraînement",
                    args={"create_request": False},
                )
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
