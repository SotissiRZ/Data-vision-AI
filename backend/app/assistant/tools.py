from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ToolRisk = Literal["read", "reversible", "destructive", "external"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    category: str
    risk: ToolRisk = "read"
    required_permissions: tuple[str, ...] = ()
    requires_dataset: bool = False
    requires_model: bool = False
    deterministic: bool = True
    input_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AssistantToolRegistry:
    """
    Registry of tools the assistant is allowed to request.

    This registry does not bypass the host application's authorization layer.
    A registered tool means "the agent may propose/use this capability";
    DataVision RBAC/RLS/column-security still decides whether the current user
    can execute it.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        spec: ToolSpec,
        handler: Callable[..., Any] | None = None,
        *,
        replace: bool = False,
    ) -> None:
        if spec.name in self._specs and not replace:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec
        if handler is not None:
            self._handlers[spec.name] = handler
        elif replace:
            self._handlers.pop(spec.name, None)

    def unregister(self, name: str) -> None:
        self._specs.pop(name, None)
        self._handlers.pop(name, None)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def list(self) -> list[ToolSpec]:
        return sorted(self._specs.values(), key=lambda item: (item.category, item.name))

    def list_for_context(
        self,
        context: Any | None,
        *,
        executable_only: bool = False,
    ) -> list[ToolSpec]:
        workspace_id = getattr(context, "workspaceId", None) if context is not None else None
        visible: list[ToolSpec] = []
        for name, spec in self._specs.items():
            if executable_only and name not in self._handlers:
                continue
            if spec.metadata.get("origin") != "plugin":
                visible.append(spec)
                continue
            plugin_workspace = spec.metadata.get("workspace_id")
            if workspace_id is not None and str(plugin_workspace) == str(workspace_id):
                visible.append(spec)
        return sorted(visible, key=lambda item: (item.category, item.name))

    def bind_handler(self, name: str, handler: Callable[..., Any]) -> None:
        if name not in self._specs:
            raise KeyError(f"Unknown assistant tool: {name}")
        self._handlers[name] = handler

    def has_handler(self, name: str) -> bool:
        return name in self._handlers

    def is_executable(self, name: str) -> bool:
        """Return True only when a declared tool has a real host/plugin handler."""
        return name in self._specs and name in self._handlers

    def list_executable(self) -> list[ToolSpec]:
        """List tools that can actually execute in the current runtime."""
        return sorted(
            (spec for name, spec in self._specs.items() if name in self._handlers),
            key=lambda item: (item.category, item.name),
        )

    def execute(self, name: str, **kwargs: Any) -> Any:
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"Unknown assistant tool: {name}")
        handler = self._handlers.get(name)
        if handler is None:
            raise RuntimeError(
                f"Tool '{name}' is declared but has not been bridged to the DataVision host implementation."
            )
        return handler(**kwargs)


def build_default_registry() -> AssistantToolRegistry:
    registry = AssistantToolRegistry()

    specs = [
        ToolSpec(
            name="profile_dataset",
            description="Profiler le dataset actif avec le moteur déterministe DataVision.",
            category="data",
            risk="read",
            required_permissions=("dataset:read",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="inspect_missing_values",
            description="Inspecter les valeurs manquantes et leurs distributions.",
            category="quality",
            risk="read",
            required_permissions=("dataset:read",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="inspect_data_leakage",
            description="Vérifier les signaux de fuite de données avant modélisation.",
            category="ml",
            risk="read",
            required_permissions=("model:read", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="diagnose_analysis_failure",
            description="Diagnostiquer l'échec d'une analyse à partir des erreurs et du contexte.",
            category="analysis",
            risk="read",
            required_permissions=("analysis:read",),
        ),
        ToolSpec(
            name="diagnose_visualization",
            description="Diagnostiquer une visualisation invalide ou impossible.",
            category="visualization",
            risk="read",
            required_permissions=("dataset:read",),
        ),
        ToolSpec(
            name="create_visualization",
            description="Créer une visualisation dans le workspace.",
            category="visualization",
            risk="reversible",
            required_permissions=("visualization:create", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="apply_reversible_transform",
            description="Appliquer une transformation versionnée et réversible.",
            category="data",
            risk="reversible",
            required_permissions=("dataset:transform",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="delete_column",
            description="Supprimer une colonne dans une nouvelle version du dataset.",
            category="data",
            risk="destructive",
            required_permissions=("dataset:transform",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="generate_report",
            description="Générer un rapport à partir des résultats gouvernés.",
            category="report",
            risk="reversible",
            required_permissions=("report:create",),
        ),
        ToolSpec(
            name="export_sensitive_data",
            description="Exporter des données potentiellement sensibles.",
            category="export",
            risk="external",
            required_permissions=("dataset:export",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="inspect_uploaded_file",
            description="Inspecter les métadonnées et le contenu structuré d'un fichier chargé.",
            category="files",
            risk="read",
            required_permissions=("file:read",),
        ),
        ToolSpec(
            name="merge_datasets",
            description="Fusionner des datasets en produisant une nouvelle version traçable.",
            category="data",
            risk="reversible",
            required_permissions=("dataset:transform",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="export_dataset",
            description="Exporter le dataset actif dans un format autorisé.",
            category="export",
            risk="external",
            required_permissions=("dataset:export",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="forecast_dataset",
            description="Prévoir une série temporelle avec backtesting rolling-origin, benchmark déterministe et intervalles empiriques hors-échantillon.",
            category="ml",
            risk="read",
            required_permissions=("analysis:create", "dataset:read"),
            requires_dataset=True,
            metadata={"agent_role": "ml_agent", "engine": "forecasting_v253"},
            input_schema={
                "type": "object",
                "required": ["date_column", "target"],
                "properties": {
                    "date_column": {"type": "string"},
                    "target": {"type": "string"},
                    "horizon": {"type": "integer", "minimum": 1, "maximum": 365, "default": 12},
                    "frequency": {"type": "string", "default": "auto"},
                    "method": {"type": "string", "default": "auto"},
                    "backtest_windows": {"type": "integer", "minimum": 1, "maximum": 8, "default": 3},
                    "interval_level": {"type": "number", "minimum": 0.5, "maximum": 0.99, "default": 0.95},
                    "missing_strategy": {"type": "string", "enum": ["none", "interpolate", "ffill", "zero"], "default": "none"},
                    "selection_metric": {"type": "string", "enum": ["rmse", "mae", "smape"], "default": "rmse"},
                },
            },
        ),
        ToolSpec(
            name="detect_dataset_anomalies",
            description="Détecter des anomalies avec IQR, z-score robuste, Isolation Forest ou consensus multi-méthodes 2-sur-3.",
            category="statistics",
            risk="read",
            required_permissions=("analysis:create", "dataset:read"),
            requires_dataset=True,
            metadata={"agent_role": "statistics_agent", "engine": "anomaly_detection_v253"},
            input_schema={
                "type": "object",
                "properties": {
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "method": {"type": "string", "enum": ["auto", "iqr", "robust_z", "isolation_forest", "consensus"], "default": "auto"},
                    "contamination": {"type": "number", "minimum": 0.001, "maximum": 0.4, "default": 0.05},
                    "threshold": {"type": "number", "minimum": 1.0, "maximum": 10.0, "default": 3.5},
                },
            },
        ),
        ToolSpec(
            name="generate_dataset_insights",
            description="Générer un feed priorisé d'insights déterministes avec preuves, tendances, anomalies, segments, corrélations et changements de version.",
            category="statistics",
            risk="read",
            required_permissions=("analysis:create", "dataset:read"),
            requires_dataset=True,
            metadata={"agent_role": "statistics_agent", "engine": "insight_engine_v1"},
            input_schema={
                "type": "object",
                "properties": {
                    "max_insights": {"type": "integer", "minimum": 1, "maximum": 40, "default": 12},
                    "persist": {"type": "boolean", "default": False},
                },
            },
        ),
        ToolSpec(
            name="run_statistical_test",
            description="Exécuter un test statistique déterministe.",
            category="statistics",
            risk="read",
            required_permissions=("analysis:create", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="run_regression",
            description="Exécuter une régression via le moteur statistique DataVision.",
            category="statistics",
            risk="read",
            required_permissions=("analysis:create", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="benchmark_models",
            description="Comparer plusieurs algorithmes ML sans laisser le LLM calculer les métriques.",
            category="ml",
            risk="read",
            required_permissions=("model:read", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="run_automl",
            description="Lancer un workflow AutoML gouverné.",
            category="ml",
            risk="reversible",
            required_permissions=("model:create", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="explain_model",
            description="Expliquer un modèle existant avec le moteur XAI.",
            category="ml",
            risk="read",
            required_permissions=("model:read",),
            requires_model=True,
        ),
        ToolSpec(
            name="list_feature_sets",
            description="Lister les Feature Sets gouvernés du workspace et leurs contrats.",
            category="mlops",
            risk="read",
            required_permissions=("dataset:read",),
        ),
        ToolSpec(
            name="materialize_feature_set",
            description="Créer un snapshot immuable d'un Feature Set à partir d'un dataset gouverné.",
            category="mlops",
            risk="mutation",
            required_permissions=("dataset:write",),
            metadata={"human_confirmation_required": True},
        ),
        ToolSpec(
            name="list_model_deployments",
            description="Lister les deployments internes, stratégies champion/shadow/canary et métriques de serving.",
            category="mlops",
            risk="read",
            required_permissions=("model:read",),
        ),
        ToolSpec(
            name="score_model_deployment",
            description="Scorer des observations via un endpoint DataVision interne en respectant le Feature Contract.",
            category="mlops",
            risk="read",
            required_permissions=("model:read",),
        ),
        ToolSpec(
            name="batch_score_model",
            description="Scorer un dataset entier et créer une nouvelle version immuable avec les prédictions.",
            category="mlops",
            risk="mutation",
            required_permissions=("model:read", "dataset:write"),
            requires_model=True,
            requires_dataset=True,
            metadata={"human_confirmation_required": True},
        ),
        ToolSpec(
            name="rollback_model_deployment",
            description="Restaurer une révision précédente d'un deployment et remettre le champion précédent en production via les gates MLOps.",
            category="mlops",
            risk="destructive",
            required_permissions=("model:publish",),
            metadata={"human_confirmation_required": True},
        ),
        ToolSpec(
            name="get_model_registry_status",
            description="Lire le stage, le rôle, la version et le monitoring d’un modèle enregistré.",
            category="mlops",
            risk="read",
            required_permissions=("model:read",),
            requires_model=True,
        ),
        ToolSpec(
            name="monitor_model_health",
            description="Comparer un modèle sauvegardé à un dataset courant et calculer performance/drift.",
            category="mlops",
            risk="read",
            required_permissions=("model:read", "dataset:read"),
            requires_model=True,
            requires_dataset=True,
        ),
        ToolSpec(
            name="check_model_retraining",
            description="Évaluer la politique de réentraînement sans lancer d'entraînement ni créer de demande.",
            category="mlops",
            risk="read",
            required_permissions=("model:read",),
            requires_model=True,
        ),
        ToolSpec(
            name="request_model_retraining",
            description="Créer une demande traçable de réentraînement si la politique le recommande.",
            category="mlops",
            risk="reversible",
            required_permissions=("model:publish",),
            requires_model=True,
            metadata={"human_confirmation_required": True},
        ),
        ToolSpec(
            name="transition_model_stage",
            description="Changer le stage MLOps d’un modèle; une promotion production applique les gates de gouvernance.",
            category="mlops",
            risk="destructive",
            required_permissions=("model:publish",),
            requires_model=True,
            metadata={"human_confirmation_required": True},
        ),
        ToolSpec(
            name="evaluate_model_fairness",
            description="Auditer les performances d’un modèle par groupes explicitement sélectionnés, sans verdict universel d’équité.",
            category="responsible_ai",
            risk="read",
            required_permissions=("model:read", "dataset:read"),
            requires_model=True,
        ),
        ToolSpec(
            name="assess_model_risk",
            description="Évaluer les risques de gouvernance d’un modèle à partir de sa Model Card et d’un audit de groupe optionnel.",
            category="responsible_ai",
            risk="read",
            required_permissions=("model:read",),
            requires_model=True,
        ),
        ToolSpec(
            name="responsible_ai_publication_gate",
            description="Appliquer des seuils Responsible AI définis par l’organisation avant publication d’un modèle.",
            category="responsible_ai",
            risk="read",
            required_permissions=("model:read", "dataset:read"),
            requires_model=True,
        ),
        ToolSpec(
            name="run_root_cause_analysis",
            description="Décomposer un écart observé par segments et changements de distribution sans inférer de causalité.",
            category="decision",
            risk="read",
            required_permissions=("analysis:create", "dataset:read"),
            requires_dataset=True,
        ),
        ToolSpec(
            name="optimize_decision_scenarios",
            description="Explorer un espace borné de scénarios avec le modèle sauvegardé.",
            category="decision",
            risk="read",
            required_permissions=("model:read",),
            requires_model=True,
        ),
        ToolSpec(
            name="gis_reproject",
            description="Reprojeter une couche géospatiale vers un CRS cible.",
            category="gis",
            risk="reversible",
            required_permissions=("dataset:transform",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="gis_spatial_join",
            description="Effectuer une jointure spatiale entre deux couches.",
            category="gis",
            risk="reversible",
            required_permissions=("dataset:transform",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="gis_buffer",
            description="Créer un buffer autour d'une couche géospatiale.",
            category="gis",
            risk="reversible",
            required_permissions=("dataset:transform",),
            requires_dataset=True,
        ),
        ToolSpec(
            name="execute_notebook_cell",
            description="Exécuter une cellule existante dans le notebook sandboxé DataVision.",
            category="notebook",
            risk="reversible",
            required_permissions=("analysis:create",),
            deterministic=True,
            metadata={"human_confirmation_required": True, "sandboxed": True},
        ),
        ToolSpec(
            name="list_data_connectors",
            description="Lister les connecteurs et sources gouvernés du workspace sans exposer les secrets.",
            category="connectors",
            risk="read",
            required_permissions=("connectors:read",),
        ),
        ToolSpec(
            name="discover_data_connector",
            description="Découvrir les tables, collections et schémas d'un connecteur gouverné.",
            category="connectors",
            risk="read",
            required_permissions=("connectors:read",),
        ),
        ToolSpec(
            name="test_data_connector",
            description="Tester activement une connexion externe configurée.",
            category="connectors",
            risk="external",
            required_permissions=("connectors:manage",),
        ),
        ToolSpec(
            name="send_external_message",
            description="Envoyer un message via un connecteur externe gouverné.",
            category="actions",
            risk="external",
            required_permissions=("action:execute",),
        ),
    ]

    for spec in specs:
        registry.register(spec)

    return registry
