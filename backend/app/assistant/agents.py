from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AgentRole, AgentTurnStep, AssistantContext, CriticFinding
from .tools import AssistantToolRegistry, ToolSpec


@dataclass(frozen=True)
class SpecialistProfile:
    role: AgentRole
    label: str
    mission: str
    categories: tuple[str, ...]


PROFILES: tuple[SpecialistProfile, ...] = (
    SpecialistProfile(
        role="data_agent",
        label="Data Agent",
        mission="Comprendre, connecter, profiler, préparer et versionner les données sans inventer de résultats.",
        categories=("data", "quality", "files", "connectors", "notebook", "analysis"),
    ),
    SpecialistProfile(
        role="statistics_agent",
        label="Statistics Agent",
        mission="Choisir et exécuter des analyses statistiques déterministes, puis exposer hypothèses et limites.",
        categories=("statistics",),
    ),
    SpecialistProfile(
        role="ml_agent",
        label="ML Agent",
        mission="Piloter modélisation, MLOps, explicabilité, Responsible AI et scénarios prédictifs via les moteurs DataVision.",
        categories=("ml", "mlops", "responsible_ai", "decision"),
    ),
    SpecialistProfile(
        role="visualization_agent",
        label="Visualization Agent",
        mission="Construire et diagnostiquer les visualisations et analyses géospatiales à partir de données vérifiées.",
        categories=("visualization", "gis"),
    ),
    SpecialistProfile(
        role="report_agent",
        label="Report Agent",
        mission="Composer, exporter et communiquer les résultats gouvernés avec provenance et méthodologie.",
        categories=("report", "export", "actions"),
    ),
    SpecialistProfile(
        role="critic_agent",
        label="Critic Agent",
        mission="Contrôler le routage, les traces d'exécution, les échecs et les résultats vides sans recalculer les métriques.",
        categories=(),
    ),
)

PROFILE_BY_ROLE = {profile.role: profile for profile in PROFILES}
CATEGORY_TO_ROLE: dict[str, AgentRole] = {
    category: profile.role
    for profile in PROFILES
    if profile.role != "critic_agent"
    for category in profile.categories
}

# Categories that contain tools with materially different analytical ownership.
TOOL_ROLE_OVERRIDES: dict[str, AgentRole] = {
    "run_root_cause_analysis": "statistics_agent",
    "optimize_decision_scenarios": "ml_agent",
}


def role_for_spec(spec: ToolSpec) -> AgentRole:
    explicit = spec.metadata.get("agent_role")
    if explicit in PROFILE_BY_ROLE and explicit != "critic_agent":
        return explicit
    if spec.name in TOOL_ROLE_OVERRIDES:
        return TOOL_ROLE_OVERRIDES[spec.name]
    return CATEGORY_TO_ROLE.get(spec.category, "data_agent")


@dataclass
class MultiAgentCoordinator:
    registry: AssistantToolRegistry

    def role_for_tool(self, tool_name: str) -> AgentRole | None:
        spec = self.registry.get(tool_name)
        if spec is None:
            return None
        return role_for_spec(spec)

    def preflight(self, step: AgentTurnStep, context: AssistantContext) -> list[str]:
        """Validate deterministic delegation before the host tool is invoked."""
        spec = self.registry.get(step.tool)
        if spec is None:
            return ["unknown_tool"]
        expected = role_for_spec(spec)
        findings: list[str] = []
        if step.agent_role != expected:
            findings.append(f"agent_mismatch:{step.agent_role or 'none'}->{expected}")
        if not self.registry.has_handler(step.tool):
            findings.append("missing_host_handler")
        if spec.requires_dataset and not context.activeDatasetId:
            findings.append("missing_dataset_context")
        if spec.requires_model and not context.activeModelId:
            findings.append("missing_model_context")
        return findings

    def review_execution(self, steps: list[AgentTurnStep]) -> list[CriticFinding]:
        findings: list[CriticFinding] = []
        for step in steps:
            spec = self.registry.get(step.tool)
            if spec is None:
                findings.append(
                    CriticFinding(
                        severity="critical",
                        code="UNKNOWN_TOOL_DELEGATION",
                        message=f"L'étape « {step.label} » référence un outil inconnu.",
                        step_id=step.id,
                    )
                )
                continue
            expected = role_for_spec(spec)
            if step.agent_role != expected:
                findings.append(
                    CriticFinding(
                        severity="critical",
                        code="SPECIALIST_ROUTING_MISMATCH",
                        message=(
                            f"L'outil {step.tool} doit être exécuté par {expected}, "
                            f"pas par {step.agent_role or 'aucun agent'} ."
                        ),
                        step_id=step.id,
                    )
                )
            if step.status == "succeeded" and step.specialist_checks and any(
                check.startswith("failed:") for check in step.specialist_checks
            ):
                findings.append(
                    CriticFinding(
                        severity="critical",
                        code="SPECIALIST_RESULT_REJECTED",
                        message=f"Le spécialiste a rejeté le résultat de « {step.label} ».",
                        step_id=step.id,
                    )
                )
        return findings

    def validate_result(self, step: AgentTurnStep, result: Any) -> list[str]:
        checks = ["passed:routing", "passed:host_execution"]
        if result is None:
            checks.append("failed:empty_result")
        else:
            checks.append("passed:non_empty_result")
        return checks

    def topology(self, *, executable_only: bool = True) -> list[dict[str, Any]]:
        tools = self.registry.list_executable() if executable_only else self.registry.list()
        owned: dict[AgentRole, list[str]] = {profile.role: [] for profile in PROFILES}
        for spec in tools:
            owned[role_for_spec(spec)].append(spec.name)
        return [
            {
                "role": profile.role,
                "label": profile.label,
                "mission": profile.mission,
                "categories": list(profile.categories),
                "tools": sorted(owned[profile.role]),
                "tool_count": len(owned[profile.role]),
                "execution_mode": "review" if profile.role == "critic_agent" else "tool_calling",
            }
            for profile in PROFILES
        ]

    def trace(self, steps: list[AgentTurnStep]) -> list[dict[str, Any]]:
        return [
            {
                "step_id": step.id,
                "tool": step.tool,
                "agent_role": step.agent_role,
                "status": step.status,
                "specialist_checks": list(step.specialist_checks),
            }
            for step in steps
        ]
