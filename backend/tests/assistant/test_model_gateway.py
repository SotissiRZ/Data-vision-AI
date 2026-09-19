import pytest

from app.assistant.model_gateway import (
    ModelGateway,
    ModelRequest,
    NoEligibleProvider,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    RoutingPolicy,
)
from app.assistant.providers.mock import StaticModelProvider


def provider(pid, kind, priority, structured=True):
    return StaticModelProvider(
        descriptor=ProviderDescriptor(
            id=pid,
            kind=kind,
            model="test-model",
            priority=priority,
            capabilities=ProviderCapabilities(
                structured_output=structured,
            ),
        ),
        response_text='{"steps":[]}',
    )


def planner_request():
    return ModelRequest(
        task="planner",
        system="",
        user="",
        response_schema={"type": "object"},
    )


def test_local_only_selects_local():
    registry = ProviderRegistry()
    registry.register(provider("cloud", "openai_compatible", 1))
    registry.register(provider("local", "local", 50))
    gateway = ModelGateway(registry)

    selected = gateway.select_provider(
        request=planner_request(),
        policy=RoutingPolicy(
            privacy_mode="local_only",
            allow_external_ai=False,
        ),
    )
    assert selected.descriptor.id == "local"


def test_external_provider_blocked_without_consent():
    registry = ProviderRegistry()
    registry.register(provider("cloud", "openai_compatible", 1))
    gateway = ModelGateway(registry)

    with pytest.raises(NoEligibleProvider):
        gateway.select_provider(
            request=planner_request(),
            policy=RoutingPolicy(
                privacy_mode="allow_external",
                allow_external_ai=False,
            ),
        )


def test_prefer_local_prioritizes_local():
    registry = ProviderRegistry()
    registry.register(provider("cloud", "openai_compatible", 1))
    registry.register(provider("local", "local", 100))
    gateway = ModelGateway(registry)

    selected = gateway.select_provider(
        request=planner_request(),
        policy=RoutingPolicy(
            privacy_mode="prefer_local",
            allow_external_ai=True,
        ),
    )
    assert selected.descriptor.id == "local"


def test_structured_output_requirement_filters_provider():
    registry = ProviderRegistry()
    registry.register(
        provider("local-nojson", "local", 1, structured=False)
    )
    gateway = ModelGateway(registry)

    with pytest.raises(NoEligibleProvider):
        gateway.select_provider(
            request=planner_request(),
            policy=RoutingPolicy(
                privacy_mode="local_only",
                allow_external_ai=False,
                require_structured_output=True,
            ),
        )
