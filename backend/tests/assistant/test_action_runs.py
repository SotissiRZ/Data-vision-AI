from app.assistant.action_runs import ActionLifecycleManager, ActionRunStore
from app.assistant.executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from app.assistant.models import AssistantAction, AssistantContext
from app.assistant.tools import AssistantToolRegistry, ToolSpec


def build_manager(risk="read", result=None):
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="tool",
            description="test",
            category="test",
            risk=risk,
            requires_dataset=True,
        ),
        lambda **kwargs: result if result is not None else {"ok": True},
    )
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    return ActionLifecycleManager(executor=executor, store=ActionRunStore())


def test_read_action_lifecycle():
    manager = build_manager()
    run = manager.propose(
        action=AssistantAction(tool="tool", label="Lire", risk="read"),
        context=AssistantContext(activeDatasetId="ds_1"),
        session_id="s1",
    )
    assert run.status == "ready"

    run = manager.execute(run.id)
    assert run.status == "succeeded"


def test_destructive_requires_confirmation():
    manager = build_manager(risk="destructive")
    run = manager.propose(
        action=AssistantAction(tool="tool", label="Supprimer", risk="read"),
        context=AssistantContext(activeDatasetId="ds_1"),
        session_id="s1",
    )
    assert run.status == "waiting_confirmation"

    run = manager.confirm(run.id, True)
    assert run.status == "ready"

    run = manager.execute(run.id)
    assert run.status == "succeeded"


def test_user_can_refuse_action():
    manager = build_manager(risk="external")
    run = manager.propose(
        action=AssistantAction(tool="tool", label="Envoyer", risk="read"),
        context=AssistantContext(activeDatasetId="ds_1"),
        session_id="s1",
    )
    run = manager.confirm(run.id, False)
    assert run.status == "cancelled"


def test_reversible_action_captures_rollback_token():
    manager = build_manager(
        risk="reversible",
        result={"ok": True, "rollback_token": "v_before"},
    )
    run = manager.propose(
        action=AssistantAction(tool="tool", label="Transformer", risk="read"),
        context=AssistantContext(activeDatasetId="ds_1"),
        session_id="s1",
    )
    run = manager.execute(run.id)
    assert run.status == "succeeded"
    assert run.rollback_token == "v_before"
