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

    def list_for_context(self, context: Any | None) -> list[ToolSpec]:
        workspace_id = getattr(context, "workspaceId", None) if context is not None else None
        visible: list[ToolSpec] = []
        for spec in self._specs.values():
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
