from __future__ import annotations

from .action_runs import ActionLifecycleManager, ActionRunStore
from .critic import MultiAgentCritic
from .agents import MultiAgentCoordinator
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
    coordinator: MultiAgentCoordinator | None = None,
) -> AgentOrchestrator:
    auth = authorization or AllowAllDevelopmentAuthorization()
    specialist_coordinator = coordinator or MultiAgentCoordinator(registry)

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
        critic=MultiAgentCritic(specialist_coordinator),
        coordinator=specialist_coordinator,
        recovery=RecoveryPolicy(),
        turn_store=turn_store or AgentTurnRunStore(),
    )
