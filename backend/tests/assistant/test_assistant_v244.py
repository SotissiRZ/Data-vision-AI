from app.assistant.executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from app.assistant.host_bridge import DataVisionHostBridges, bind_registry_to_host
from app.assistant.llm_planner import GatewayPlannerProvider
from app.assistant.model_gateway import (
    ModelGateway,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    RoutingPolicy,
)
from app.assistant.models import AgentIntent, AgentPlanStep, AgentTurnRequest, AssistantAction, AssistantContext
from app.assistant.plan import validate_agent_plan
from app.assistant.privacy import AIDataPolicy
from app.assistant.providers.mock import StaticModelProvider
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import AssistantToolRegistry, ToolSpec, build_default_registry


class FakeDataBridge:
    def profile_dataset(self, *, context, **kwargs):
        return {"dataset_id": context.activeDatasetId, "rows": 12, "columns_count": 3, "duplicates": 0}

    def inspect_missing_values(self, *, context, **kwargs):
        return {"dataset_id": context.activeDatasetId, "rows": 12, "columns": []}

    def apply_reversible_transform(self, *, context, **kwargs):
        return {"dataset_id": "ds_v2", "parent_dataset_id": context.activeDatasetId, "version": 2, "rollback_token": context.activeDatasetId}

    def merge_datasets(self, *, context, **kwargs):
        return {"dataset_id": "ds_merge", "version": 2, "rollback_token": context.activeDatasetId}

    def delete_column(self, *, context, **kwargs):
        return {"dataset_id": "ds_v2", "version": 2, "rollback_token": context.activeDatasetId}


def test_executable_catalog_excludes_unbridged_features():
    registry = build_default_registry()
    bind_registry_to_host(registry, DataVisionHostBridges(data=FakeDataBridge()))
    names = {item.name for item in registry.list_for_context(None, executable_only=True)}
    assert "profile_dataset" in names
    assert "apply_reversible_transform" in names
    assert "gis_reproject" not in names
    assert "send_external_message" not in names


def test_unbridged_tool_is_denied_before_execution():
    registry = build_default_registry()
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.prepare(
        AssistantAction(tool="gis_reproject", label="Reprojeter"),
        AssistantContext(activeDatasetId="ds1"),
    )
    assert decision.status == "deny"
    assert "indisponible" in decision.reason


def test_plan_validator_rejects_unbridged_tool():
    registry = build_default_registry()
    result = validate_agent_plan(
        steps=[AgentPlanStep(tool="gis_reproject", label="Reprojeter")],
        context=AssistantContext(activeDatasetId="ds1"),
        registry=registry,
        authorization=AllowAllDevelopmentAuthorization(),
    )
    assert result.valid is False
    assert result.steps[0].status == "deny"


def test_deterministic_turn_executes_real_bound_tools():
    registry = build_default_registry()
    bind_registry_to_host(registry, DataVisionHostBridges(data=FakeDataBridge()))
    orchestrator = build_orchestrator(registry=registry)
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="v244",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1", screen="quality"),
        )
    )
    assert response.status == "completed"
    assert [step.tool for step in response.steps] == ["profile_dataset", "inspect_missing_values"]
    assert all(step.status == "succeeded" for step in response.steps)
    assert "12 lignes" in response.message


def test_gateway_planner_drops_declared_but_unbound_tool():
    provider_registry = ProviderRegistry()
    provider_registry.register(
        StaticModelProvider(
            descriptor=ProviderDescriptor(
                id="local",
                kind="local",
                model="test",
                capabilities=ProviderCapabilities(structured_output=True),
            ),
            response_text=(
                '{"steps":['
                '{"tool":"profile_dataset","label":"Profiler","args":{}},'
                '{"tool":"gis_reproject","label":"GIS","args":{}}'
                ']}'
            ),
        )
    )
    tools = build_default_registry()
    tools.bind_handler("profile_dataset", lambda **kwargs: {"rows": 1})
    planner = GatewayPlannerProvider(
        gateway=ModelGateway(provider_registry),
        registry=tools,
        routing_policy=RoutingPolicy(privacy_mode="local_only", allow_external_ai=False),
        data_policy=AIDataPolicy(),
    )
    steps = planner.plan(
        message="Analyse",
        intent=AgentIntent(name="analyze_dataset", confidence=1.0),
        context=AssistantContext(activeDatasetId="ds1"),
        attachment_ids=[],
    )
    assert [step.tool for step in steps] == ["profile_dataset"]


def test_reversible_action_keeps_confirmation_policy_when_bound():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="mutate",
            description="mutation",
            category="data",
            risk="reversible",
            metadata={"human_confirmation_required": True},
        ),
        handler=lambda **kwargs: {"ok": True},
    )
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.prepare(
        AssistantAction(tool="mutate", label="Modifier"),
        AssistantContext(),
    )
    assert decision.status == "confirmation_required"
