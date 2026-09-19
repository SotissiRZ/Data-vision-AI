from __future__ import annotations

from .action_runs import ActionLifecycleManager, ActionRunStore
from .critic import DeterministicCritic
from .executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor, HostAuthorization
from .memory import SessionMemoryStore
from .orchestrator import AgentOrchestrator
from .planner_runtime import DeterministicPlanner, PlannerProvider
from .recovery import RecoveryPolicy
from .tools import AssistantToolRegistry
from .turn_runs import AgentTurnRunStore


def build_orchestrator(
    *,
    registry: AssistantToolRegistry,
    authorization: HostAuthorization | None = None,
    planner: PlannerProvider | None = None,
    action_lifecycle: ActionLifecycleManager | None = None,
    turn_store: AgentTurnRunStore | None = None,
    memory: SessionMemoryStore | None = None,
) -> AgentOrchestrator:
    auth = authorization or AllowAllDevelopmentAuthorization()

    if action_lifecycle is None:
        executor = GovernedToolExecutor(registry, auth)
        action_lifecycle = ActionLifecycleManager(
            executor=executor,
            store=ActionRunStore(),
        )

    return AgentOrchestrator(
        registry=registry,
        authorization=auth,
        action_lifecycle=action_lifecycle,
        memory=memory or SessionMemoryStore(),
        planner=planner or DeterministicPlanner(),
        critic=DeterministicCritic(),
        recovery=RecoveryPolicy(),
        turn_store=turn_store or AgentTurnRunStore(),
    )
