from app.assistant.executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from app.assistant.models import AssistantAction, AssistantContext
from app.assistant.tools import AssistantToolRegistry, ToolSpec


def test_dataset_requirement_blocks_without_dataset():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="profile_dataset",
            description="x",
            category="data",
            requires_dataset=True,
        ),
        lambda **kwargs: {"ok": True},
    )
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.prepare(
        AssistantAction(tool="profile_dataset", label="Profiler"),
        AssistantContext(),
    )
    assert decision.status == "deny"


def test_destructive_needs_confirmation():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="delete_column",
            description="x",
            category="data",
            risk="destructive",
            requires_dataset=True,
        ),
        lambda **kwargs: {"ok": True},
    )
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.prepare(
        AssistantAction(tool="delete_column", label="Supprimer", risk="destructive", args={"columns": ["obsolete_col"]}),
        AssistantContext(activeDatasetId="ds_1"),
    )
    assert decision.status == "confirmation_required"


def test_read_tool_executes_when_bridged():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="profile_dataset",
            description="x",
            category="data",
            requires_dataset=True,
        ),
        lambda **kwargs: {"rows": 10},
    )
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.execute(
        AssistantAction(tool="profile_dataset", label="Profiler"),
        AssistantContext(activeDatasetId="ds_1"),
    )
    assert decision.status == "executed"
    assert decision.result == {"rows": 10}


def test_agent_cannot_downgrade_registered_tool_risk():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="dangerous_custom_tool",
            description="x",
            category="data",
            risk="destructive",
            requires_dataset=True,
        ),
        lambda **kwargs: {"ok": True},
    )
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.prepare(
        AssistantAction(
            tool="dangerous_custom_tool",
            label="Action risquée",
            risk="read",  # untrusted agent payload tries to downgrade risk
        ),
        AssistantContext(activeDatasetId="ds_1"),
    )
    assert decision.status == "confirmation_required"
