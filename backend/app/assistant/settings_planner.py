from __future__ import annotations

from dataclasses import dataclass, field

from .ai_settings import (
    build_model_gateway_for_scope,
    get_ai_settings,
    routing_policy_for_settings,
    scope_for_context,
)
from .llm_planner import GatewayPlannerProvider
from .models import AgentIntent, AgentPlanStep, AssistantContext
from .planner_runtime import DeterministicPlanner, PlannerProvider
from .privacy import AIDataPolicy
from .tools import AssistantToolRegistry


@dataclass
class SettingsAwarePlanner(PlannerProvider):
    registry: AssistantToolRegistry
    deterministic: DeterministicPlanner = field(default_factory=DeterministicPlanner)

    def plan(
        self,
        *,
        message: str,
        intent: AgentIntent,
        context: AssistantContext,
        attachment_ids: list[str],
    ) -> list[AgentPlanStep]:
        scope_type, scope_id, actor_id = scope_for_context(context.workspaceId)
        settings = get_ai_settings(scope_type, scope_id)

        if settings.planner_mode != "gateway":
            return self.deterministic.plan(
                message=message,
                intent=intent,
                context=context,
                attachment_ids=attachment_ids,
            )

        try:
            gateway = build_model_gateway_for_scope(
                scope_type,
                scope_id,
                actor_id=actor_id,
            )
            routing = routing_policy_for_settings(
                settings,
                task="planner",
            )
            data_policy = AIDataPolicy(
                allow_external_ai=settings.allow_external_ai,
                include_column_names_external=(
                    settings.external_data_policy.include_column_names
                ),
                include_sample_values_external=False,
                include_row_data_external=False,
                max_recent_events_external=(
                    settings.external_data_policy.max_recent_events
                ),
            )
            planner = GatewayPlannerProvider(
                gateway=gateway,
                registry=self.registry,
                routing_policy=routing,
                data_policy=data_policy,
            )
            return planner.plan(
                message=message,
                intent=intent,
                context=context,
                attachment_ids=attachment_ids,
            )
        except Exception:
            if not settings.fallback_to_deterministic:
                raise
            return self.deterministic.plan(
                message=message,
                intent=intent,
                context=context,
                attachment_ids=attachment_ids,
            )
