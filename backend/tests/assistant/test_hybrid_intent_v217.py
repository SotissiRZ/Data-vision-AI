from app.assistant.hybrid_intent import GatewayIntentResolver
from app.assistant.model_gateway import (
    ModelGateway,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    RoutingPolicy,
)
from app.assistant.models import AgentIntent, AssistantContext
from app.assistant.privacy import AIDataPolicy, project_context_for_model
from app.assistant.providers.mock import StaticModelProvider


def make_gateway(payload: str) -> ModelGateway:
    registry = ProviderRegistry()
    registry.register(
        StaticModelProvider(
            descriptor=ProviderDescriptor(
                id="local-test",
                kind="local",
                model="test",
                capabilities=ProviderCapabilities(
                    structured_output=True,
                ),
            ),
            response_text=payload,
        )
    )
    return ModelGateway(registry)


def test_hybrid_intent_promotes_unknown_to_visualize():
    resolver = GatewayIntentResolver(
        gateway=make_gateway(
            '{"intent":"visualize","confidence":0.94,'
            '"entities":{"x":"revenue"},"rationale":"graph request"}'
        ),
        routing_policy=RoutingPolicy(
            privacy_mode="local_only",
            allow_external_ai=False,
        ),
        data_policy=AIDataPolicy(),
    )

    resolved = resolver.resolve(
        message="Montre-moi ça sous une forme visuelle adaptée",
        context=AssistantContext(activeDatasetId="ds1"),
        current=AgentIntent(
            name="unknown",
            confidence=0.2,
        ),
    )

    assert resolved.name == "visualize"
    assert resolved.confidence == 0.94


def test_low_confidence_hybrid_intent_keeps_deterministic_unknown():
    resolver = GatewayIntentResolver(
        gateway=make_gateway(
            '{"intent":"conversation","confidence":0.40,'
            '"entities":{},"rationale":"uncertain"}'
        ),
        routing_policy=RoutingPolicy(
            privacy_mode="local_only",
            allow_external_ai=False,
        ),
        data_policy=AIDataPolicy(),
    )

    current = AgentIntent(name="unknown", confidence=0.2)
    resolved = resolver.resolve(
        message="hmm",
        context=AssistantContext(activeDatasetId="ds1"),
        current=current,
    )

    assert resolved.name == "unknown"


def test_external_projection_can_hide_column_names_but_keep_types():
    context = AssistantContext(
        activeDatasetId="ds1",
        uiState={
            "datasetSchema": [
                {"name": "salary", "dtype": "float64"},
                {"name": "country", "dtype": "object"},
            ],
            "target": "salary",
            "qualityScore": 92,
            "rows": [{"salary": 1000}],
        },
    )

    projected = project_context_for_model(
        context,
        external=True,
        policy=AIDataPolicy(
            allow_external_ai=True,
            include_column_names_external=False,
        ),
    )

    assert projected["dataset_schema"] == [
        {"name": None, "dtype": "float64"},
        {"name": None, "dtype": "object"},
    ]
    assert projected["target"] is None
    assert projected["qualityScore"] == 92
    assert "rows" not in projected
