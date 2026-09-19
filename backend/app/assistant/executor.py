from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import AssistantAction, AssistantContext
from .contracts import validate_tool_arguments
from .policy import evaluate_action_policy
from .tools import AssistantToolRegistry, ToolSpec


class HostAuthorization(Protocol):
    def is_allowed(
        self,
        *,
        tool: ToolSpec,
        context: AssistantContext,
    ) -> tuple[bool, str]:
        ...


class AllowAllDevelopmentAuthorization:
    """
    Development-only authorization adapter.

    Production DataVision must bridge this interface to its existing
    RBAC/RLS/column-security service.
    """

    def is_allowed(
        self,
        *,
        tool: ToolSpec,
        context: AssistantContext,
    ) -> tuple[bool, str]:
        return True, "development adapter"


@dataclass
class ExecutionDecision:
    status: str
    reason: str
    tool: ToolSpec | None = None
    result: Any = None


class GovernedToolExecutor:
    def __init__(
        self,
        registry: AssistantToolRegistry,
        authorization: HostAuthorization,
    ) -> None:
        self.registry = registry
        self.authorization = authorization

    def prepare(
        self,
        action: AssistantAction,
        context: AssistantContext,
    ) -> ExecutionDecision:
        spec = self.registry.get(action.tool)
        if spec is None:
            return ExecutionDecision(
                status="deny",
                reason=f"Outil non enregistré : {action.tool}",
            )

        if spec.metadata.get("origin") == "plugin":
            plugin_workspace = spec.metadata.get("workspace_id")
            if not context.workspaceId or str(plugin_workspace) != str(context.workspaceId):
                return ExecutionDecision(
                    status="deny",
                    reason="Tool plugin non disponible dans ce workspace.",
                    tool=spec,
                )

        if spec.requires_dataset and not context.activeDatasetId:
            return ExecutionDecision(
                status="deny",
                reason="Cette action nécessite un dataset actif.",
                tool=spec,
            )

        if spec.requires_model and not context.activeModelId:
            return ExecutionDecision(
                status="deny",
                reason="Cette action nécessite un modèle actif.",
                tool=spec,
            )

        # Validate arguments against the deterministic tool contract before
        # policy and authorization.
        try:
            validated_args = validate_tool_arguments(action.tool, action.args, spec.input_schema)
        except Exception as exc:
            return ExecutionDecision(
                status="deny",
                reason=f"Arguments invalides pour {action.tool}: {exc}",
                tool=spec,
            )

        # Canonicalize risk from the trusted registry and normalized args.
        canonical_action = action.model_copy(
            update={"risk": spec.risk, "args": validated_args}
        )
        policy = evaluate_action_policy(canonical_action, context)

        if policy.decision == "deny":
            return ExecutionDecision(status="deny", reason=policy.reason, tool=spec)

        allowed, auth_reason = self.authorization.is_allowed(tool=spec, context=context)
        if not allowed:
            return ExecutionDecision(
                status="deny",
                reason=f"Permission DataVision refusée : {auth_reason}",
                tool=spec,
            )

        if policy.decision == "confirmation_required":
            return ExecutionDecision(
                status="confirmation_required",
                reason=policy.reason,
                tool=spec,
            )

        return ExecutionDecision(
            status="ready",
            reason="Action autorisée et prête à être exécutée.",
            tool=spec,
        )

    def execute(
        self,
        action: AssistantAction,
        context: AssistantContext,
        *,
        confirmed: bool = False,
    ) -> ExecutionDecision:
        decision = self.prepare(action, context)

        if decision.status == "confirmation_required" and not confirmed:
            return decision

        if decision.status not in {"ready", "confirmation_required"}:
            return decision

        spec = self.registry.get(action.tool)
        validated_args = validate_tool_arguments(
            action.tool,
            action.args,
            spec.input_schema if spec is not None else None,
        )
        result = self.registry.execute(
            action.tool,
            context=context,
            **validated_args,
        )
        return ExecutionDecision(
            status="executed",
            reason="Action exécutée via le Tool Registry.",
            tool=decision.tool,
            result=result,
        )
