from __future__ import annotations

from dataclasses import dataclass

from app.assistant.agents import MultiAgentCoordinator, role_for_spec
from app.assistant.critic import MultiAgentCritic
from app.assistant.models import AgentIntent, AgentPlanStep, AgentTurnRequest, AgentTurnStep, AssistantContext
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import AssistantToolRegistry, ToolSpec


def _registry() -> AssistantToolRegistry:
    registry = AssistantToolRegistry()
    specs = [
        ToolSpec(name="data_probe", description="profile", category="data", requires_dataset=True),
        ToolSpec(name="stats_probe", description="stats", category="statistics", requires_dataset=True),
        ToolSpec(name="ml_probe", description="ml", category="ml", requires_dataset=True),
        ToolSpec(name="viz_probe", description="viz", category="visualization", requires_dataset=True),
        ToolSpec(name="report_probe", description="report", category="report"),
    ]
    for spec in specs:
        registry.register(spec, handler=lambda **kwargs: {"ok": True, "args": kwargs})
    return registry


def test_default_specialist_ownership_is_deterministic():
    registry = _registry()
    coordinator = MultiAgentCoordinator(registry)
    assert coordinator.role_for_tool("data_probe") == "data_agent"
    assert coordinator.role_for_tool("stats_probe") == "statistics_agent"
    assert coordinator.role_for_tool("ml_probe") == "ml_agent"
    assert coordinator.role_for_tool("viz_probe") == "visualization_agent"
    assert coordinator.role_for_tool("report_probe") == "report_agent"


def test_topology_exposes_all_six_cdc_agents():
    topology = MultiAgentCoordinator(_registry()).topology()
    assert [item["role"] for item in topology] == [
        "data_agent",
        "statistics_agent",
        "ml_agent",
        "visualization_agent",
        "report_agent",
        "critic_agent",
    ]
    assert topology[-1]["execution_mode"] == "review"


def test_specialist_preflight_rejects_wrong_owner():
    registry = _registry()
    coordinator = MultiAgentCoordinator(registry)
    step = AgentTurnStep(
        tool="stats_probe",
        label="Test",
        agent_role="data_agent",
    )
    findings = coordinator.preflight(step, AssistantContext(activeDatasetId="ds-1"))
    assert any(item.startswith("agent_mismatch") for item in findings)


def test_critic_agent_detects_routing_mismatch():
    registry = _registry()
    coordinator = MultiAgentCoordinator(registry)
    critic = MultiAgentCritic(coordinator)
    report = critic.review([
        AgentTurnStep(
            tool="viz_probe",
            label="Graphique",
            agent_role="data_agent",
            status="succeeded",
            result={"ok": True},
        )
    ])
    assert report.status == "fail"
    assert report.reviewed_by == "critic_agent"
    assert any(item.code == "SPECIALIST_ROUTING_MISMATCH" for item in report.findings)


@dataclass
class StaticMultiAgentPlanner:
    def plan(self, **kwargs):
        return [
            AgentPlanStep(tool="data_probe", label="Profiler"),
            AgentPlanStep(tool="stats_probe", label="Tester"),
            AgentPlanStep(tool="ml_probe", label="Modéliser"),
            AgentPlanStep(tool="viz_probe", label="Visualiser"),
            AgentPlanStep(tool="report_probe", label="Rapporter"),
        ]


def test_one_turn_handoffs_across_five_specialists_and_critic():
    registry = _registry()
    orchestrator = build_orchestrator(registry=registry, planner=StaticMultiAgentPlanner())
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s-v246",
            message="Analyse complète",
            context=AssistantContext(activeDatasetId="ds-1"),
        )
    )
    assert response.status == "completed"
    assert [step.agent_role for step in response.steps] == [
        "data_agent",
        "statistics_agent",
        "ml_agent",
        "visualization_agent",
        "report_agent",
    ]
    assert all(step.specialist_checks == ["passed:routing", "passed:host_execution", "passed:non_empty_result"] for step in response.steps)
    assert response.critic is not None
    assert response.critic.status == "pass"
    assert response.critic.reviewed_by == "critic_agent"
    assert response.critic.checked_step_count == 5
    assert response.metadata["multi_agent"] is True
    assert [item["agent_role"] for item in response.metadata["agent_trace"]] == [
        "data_agent",
        "statistics_agent",
        "ml_agent",
        "visualization_agent",
        "report_agent",
    ]


def test_result_validation_rejects_empty_specialist_output():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(name="data_probe", description="profile", category="data", requires_dataset=True),
        handler=lambda **kwargs: None,
    )

    @dataclass
    class Planner:
        def plan(self, **kwargs):
            return [AgentPlanStep(tool="data_probe", label="Profiler")]

    response = build_orchestrator(registry=registry, planner=Planner()).run_turn(
        AgentTurnRequest(
            session_id="empty-v246",
            message="Analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds-1"),
        )
    )
    assert response.status == "failed"
    assert response.steps[0].agent_role == "data_agent"
    assert "failed:empty_result" in response.steps[0].specialist_checks


def test_tool_metadata_can_override_default_specialist():
    spec = ToolSpec(
        name="plugin_stat",
        description="plugin",
        category="custom",
        metadata={"agent_role": "statistics_agent"},
    )
    assert role_for_spec(spec) == "statistics_agent"
