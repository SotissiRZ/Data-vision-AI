from __future__ import annotations

from .executor import HostAuthorization
from .contracts import validate_tool_arguments
from .models import (
    AgentPlanStep,
    AgentPlanStepValidation,
    AgentPlanValidationResponse,
    AssistantAction,
    AssistantContext,
)
from .policy import evaluate_action_policy
from .tools import AssistantToolRegistry


def validate_agent_plan(
    *,
    steps: list[AgentPlanStep],
    context: AssistantContext,
    registry: AssistantToolRegistry,
    authorization: HostAuthorization,
) -> AgentPlanValidationResponse:
    results: list[AgentPlanStepValidation] = []

    for step in steps:
        spec = registry.get(step.tool)

        if spec is None:
            results.append(
                AgentPlanStepValidation(
                    id=step.id,
                    tool=step.tool,
                    status="deny",
                    reason="Outil inconnu ou non enregistré.",
                    risk=None,
                )
            )
            continue

        if spec.metadata.get("origin") == "plugin":
            plugin_workspace = spec.metadata.get("workspace_id")
            if not context.workspaceId or str(plugin_workspace) != str(context.workspaceId):
                results.append(
                    AgentPlanStepValidation(
                        id=step.id,
                        tool=step.tool,
                        status="deny",
                        reason="Tool plugin non disponible dans ce workspace.",
                        risk=spec.risk,
                    )
                )
                continue

        if spec.requires_dataset and not context.activeDatasetId:
            results.append(
                AgentPlanStepValidation(
                    id=step.id,
                    tool=step.tool,
                    status="deny",
                    reason="Dataset actif requis.",
                    risk=spec.risk,
                )
            )
            continue

        if spec.requires_model and not context.activeModelId:
            results.append(
                AgentPlanStepValidation(
                    id=step.id,
                    tool=step.tool,
                    status="deny",
                    reason="Modèle actif requis.",
                    risk=spec.risk,
                )
            )
            continue

        validated_args = dict(step.args)
        # Dynamic plugin schemas must always be validated at planning time.
        # For legacy built-in tools, keep the historical behavior for empty
        # draft steps (the executor still performs the strict contract check
        # before execution). Non-empty built-in args are validated here too.
        if spec.input_schema is not None or step.args:
            try:
                validated_args = validate_tool_arguments(
                    step.tool,
                    step.args,
                    spec.input_schema,
                )
            except Exception as exc:
                results.append(
                    AgentPlanStepValidation(
                        id=step.id,
                        tool=step.tool,
                        status="deny",
                        reason=f"Arguments invalides : {exc}",
                        risk=spec.risk,
                    )
                )
                continue

        action = AssistantAction(
            tool=step.tool,
            label=step.label,
            args=validated_args,
            risk=spec.risk,
        )
        policy = evaluate_action_policy(action, context)
        if policy.decision == "deny":
            results.append(
                AgentPlanStepValidation(
                    id=step.id,
                    tool=step.tool,
                    status="deny",
                    reason=policy.reason,
                    risk=spec.risk,
                )
            )
            continue

        allowed, auth_reason = authorization.is_allowed(tool=spec, context=context)
        if not allowed:
            results.append(
                AgentPlanStepValidation(
                    id=step.id,
                    tool=step.tool,
                    status="deny",
                    reason=f"Permission refusée : {auth_reason}",
                    risk=spec.risk,
                )
            )
            continue

        status = (
            "confirmation_required"
            if policy.decision == "confirmation_required"
            else "ready"
        )
        results.append(
            AgentPlanStepValidation(
                id=step.id,
                tool=step.tool,
                status=status,
                reason=policy.reason,
                risk=spec.risk,
            )
        )

    valid = all(item.status != "deny" for item in results)
    executable_without_confirmation = valid and all(
        item.status == "ready" for item in results
    )

    return AgentPlanValidationResponse(
        valid=valid,
        executable_without_confirmation=executable_without_confirmation,
        steps=results,
    )
