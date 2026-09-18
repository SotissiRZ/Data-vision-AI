from app.assistant.action_runs import ActionLifecycleManager, ActionRunStore
from app.assistant.executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from app.assistant.models import (
    AgentIntent,
    AgentPlanStep,
    AgentTurnRequest,
    AssistantContext,
)
from app.assistant.planner_runtime import PlannerProvider
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import AssistantToolRegistry, ToolSpec
from app.assistant.turn_runs import AgentTurnRunStore


class ConfirmationPlanner:
    def plan(self, **kwargs):
        return [
            AgentPlanStep(
                tool="dangerous_step",
                label="Étape sensible",
                args={},
            ),
            AgentPlanStep(
                tool="safe_after",
                label="Étape suivante",
                args={},
            ),
        ]


def build_confirmation_runtime(counter):
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="dangerous_step",
            description="danger",
            category="test",
            risk="destructive",
        ),
        lambda **kwargs: counter.__setitem__("dangerous", counter["dangerous"] + 1) or {"ok": True},
    )
    registry.register(
        ToolSpec(
            name="safe_after",
            description="safe",
            category="test",
            risk="read",
        ),
        lambda **kwargs: counter.__setitem__("safe", counter["safe"] + 1) or {"ok": True},
    )

    auth = AllowAllDevelopmentAuthorization()
    executor = GovernedToolExecutor(registry, auth)
    lifecycle = ActionLifecycleManager(executor=executor, store=ActionRunStore())

    orchestrator = build_orchestrator(
        registry=registry,
        authorization=auth,
        planner=ConfirmationPlanner(),
        action_lifecycle=lifecycle,
        turn_store=AgentTurnRunStore(),
    )
    return orchestrator, lifecycle


def test_downstream_step_does_not_run_before_confirmation():
    counter = {"dangerous": 0, "safe": 0}
    orchestrator, lifecycle = build_confirmation_runtime(counter)

    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )

    assert response.status == "waiting_confirmation"
    assert counter == {"dangerous": 0, "safe": 0}
    assert response.steps[0].status == "waiting_confirmation"
    assert response.steps[1].status == "ready"


def test_confirm_then_resume_runs_in_order():
    counter = {"dangerous": 0, "safe": 0}
    orchestrator, lifecycle = build_confirmation_runtime(counter)

    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    turn_run_id = response.metadata["turn_run_id"]
    action_run_id = response.pending_action_run_ids[0]

    confirmed = lifecycle.confirm(action_run_id, True)
    assert confirmed.status == "ready"

    resumed = orchestrator.continue_turn(
        turn_run_id,
        confirmed_action_run_id=action_run_id,
    )

    assert resumed.status == "completed"
    assert counter == {"dangerous": 1, "safe": 1}
    assert [s.status for s in resumed.steps] == ["succeeded", "succeeded"]


def test_refusal_cancels_remaining_plan():
    counter = {"dangerous": 0, "safe": 0}
    orchestrator, lifecycle = build_confirmation_runtime(counter)

    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    turn_run_id = response.metadata["turn_run_id"]
    action_run_id = response.pending_action_run_ids[0]

    lifecycle.confirm(action_run_id, False)
    resumed = orchestrator.continue_turn(
        turn_run_id,
        confirmed_action_run_id=action_run_id,
    )

    assert resumed.status == "partial"
    assert counter == {"dangerous": 0, "safe": 0}
