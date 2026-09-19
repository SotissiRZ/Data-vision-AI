from __future__ import annotations

from .ai_settings import (
    build_model_gateway_for_scope,
    get_ai_settings,
    routing_policy_for_settings,
    scope_for_context,
)
from .hybrid_intent import GatewayIntentResolver
from .models import AgentIntent, AssistantContext
from .privacy import AIDataPolicy


class SettingsAwareIntentResolver:
    def resolve(
        self,
        *,
        message: str,
        context: AssistantContext,
        current: AgentIntent,
    ) -> AgentIntent:
        if current.name != "unknown":
            return current

        try:
            scope_type, scope_id, actor_id = scope_for_context(
                context.workspaceId
            )
            settings = get_ai_settings(scope_type, scope_id)
            if settings.planner_mode != "gateway":
                return current

            gateway = build_model_gateway_for_scope(
                scope_type,
                scope_id,
                actor_id=actor_id,
            )
            routing = routing_policy_for_settings(
                settings,
                task="planner",
            )
            policy = AIDataPolicy(
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
            return GatewayIntentResolver(
                gateway=gateway,
                routing_policy=routing,
                data_policy=policy,
            ).resolve(
                message=message,
                context=context,
                current=current,
            )
        except Exception:
            # Understanding enhancement is best-effort. It must never make the
            # deterministic path unavailable.
            return current
