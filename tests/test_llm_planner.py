from app.assistant.llm_planner import GatewayPlannerProvider
from app.assistant.model_gateway import (
    ModelGateway,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    RoutingPolicy,
)
from app.assistant.models import AgentIntent, AssistantContext
from app.assistant.privacy import AIDataPolicy
from app.assistant.providers.mock import StaticModelProvider
from app.assistant.tools import build_default_registry


def test_gateway_planner_parses_known_tools_and_drops_unknown():
    provider_json = (
        '{"steps":['
        '{"tool":"profile_dataset","label":"Profiler","args":{}},'
        '{"tool":"invented_tool","label":"Inventé","args":{}}'
        ']}'
    )

    registry = ProviderRegistry()
    registry.register(
        StaticModelProvider(
            descriptor=ProviderDescriptor(
                id="local",
                kind="local",
                model="test",
                capabilities=ProviderCapabilities(
                    structured_output=True,
                ),
            ),
            response_text=provider_json,
        )
    )

    planner = GatewayPlannerProvider(
        gateway=ModelGateway(registry),
        registry=build_default_registry(),
        routing_policy=RoutingPolicy(
            privacy_mode="local_only",
            allow_external_ai=False,
        ),
        data_policy=AIDataPolicy(),
    )

    steps = planner.plan(
        message="Analyse le dataset",
        intent=AgentIntent(
            name="analyze_dataset",
            confidence=0.9,
        ),
        context=AssistantContext(activeDatasetId="ds1"),
        attachment_ids=[],
    )

    assert len(steps) == 1
    assert steps[0].tool == "profile_dataset"
