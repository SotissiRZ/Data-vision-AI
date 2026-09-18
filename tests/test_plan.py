from app.assistant.executor import AllowAllDevelopmentAuthorization
from app.assistant.models import AgentPlanStep, AssistantContext
from app.assistant.plan import validate_agent_plan
from app.assistant.tools import build_default_registry


def test_unknown_tool_denied():
    result = validate_agent_plan(
        steps=[AgentPlanStep(tool="invented_tool", label="Faire quelque chose")],
        context=AssistantContext(activeDatasetId="ds_1"),
        registry=build_default_registry(),
        authorization=AllowAllDevelopmentAuthorization(),
    )
    assert result.valid is False
    assert result.steps[0].status == "deny"


def test_read_plan_ready():
    result = validate_agent_plan(
        steps=[AgentPlanStep(tool="profile_dataset", label="Profiler")],
        context=AssistantContext(activeDatasetId="ds_1"),
        registry=build_default_registry(),
        authorization=AllowAllDevelopmentAuthorization(),
    )
    assert result.valid is True
    assert result.executable_without_confirmation is True
    assert result.steps[0].status == "ready"


def test_external_export_requires_confirmation():
    result = validate_agent_plan(
        steps=[AgentPlanStep(tool="export_dataset", label="Exporter")],
        context=AssistantContext(activeDatasetId="ds_1"),
        registry=build_default_registry(),
        authorization=AllowAllDevelopmentAuthorization(),
    )
    assert result.valid is True
    assert result.executable_without_confirmation is False
    assert result.steps[0].status == "confirmation_required"


def test_dataset_tool_denied_without_dataset():
    result = validate_agent_plan(
        steps=[AgentPlanStep(tool="profile_dataset", label="Profiler")],
        context=AssistantContext(),
        registry=build_default_registry(),
        authorization=AllowAllDevelopmentAuthorization(),
    )
    assert result.valid is False
    assert result.steps[0].status == "deny"
