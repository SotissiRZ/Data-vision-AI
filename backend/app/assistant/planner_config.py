from __future__ import annotations

import os

from .llm_planner import GatewayPlannerProvider
from .model_gateway import NoEligibleProvider, RoutingPolicy
from .model_gateway_config import build_model_gateway_from_env
from .planner_runtime import DeterministicPlanner, PlannerProvider
from .privacy import AIDataPolicy
from .tools import AssistantToolRegistry


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_planner_from_env(registry: AssistantToolRegistry) -> PlannerProvider:
    mode = os.getenv("DATAVISION_AI_PLANNER_MODE", "deterministic").strip().lower()

    if mode != "gateway":
        return DeterministicPlanner()

    gateway = build_model_gateway_from_env()

    privacy_mode = os.getenv(
        "DATAVISION_AI_PRIVACY_MODE",
        "local_only",
    ).strip()

    allow_external = env_bool(
        "DATAVISION_AI_ALLOW_EXTERNAL",
        default=False,
    )

    routing = RoutingPolicy(
        privacy_mode=privacy_mode,  # validated by dataclass consumers / tests
        allow_external_ai=allow_external,
        require_structured_output=True,
        preferred_provider_id=os.getenv("DATAVISION_AI_PREFERRED_PROVIDER") or None,
    )

    data_policy = AIDataPolicy(
        allow_external_ai=allow_external,
        include_column_names_external=env_bool(
            "DATAVISION_AI_EXTERNAL_COLUMN_NAMES",
            default=True,
        ),
        include_sample_values_external=False,
        include_row_data_external=False,
        max_recent_events_external=int(
            os.getenv("DATAVISION_AI_EXTERNAL_MAX_EVENTS", "5")
        ),
    )

    # Fail closed if gateway mode was explicitly requested but no eligible
    # provider is configured. Do not silently send data elsewhere.
    probe_planner = GatewayPlannerProvider(
        gateway=gateway,
        registry=registry,
        routing_policy=routing,
        data_policy=data_policy,
    )

    # Force provider eligibility check now.
    from .model_gateway import ModelRequest
    gateway.select_provider(
        request=ModelRequest(
            task="planner",
            system="",
            user="",
            response_schema={"type": "object"},
        ),
        policy=routing,
    )

    return probe_planner
