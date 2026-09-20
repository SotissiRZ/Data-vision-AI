from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_contract_exposes_agent_role_and_specialist_checks():
    source = (ROOT / "frontend/lib/assistant/orchestrator.ts").read_text(encoding="utf-8")
    assert "export type AgentRole" in source
    assert "agent_role?: AgentRole" in source
    assert "specialist_checks?: string[]" in source
    assert "reviewed_by?: AgentRole" in source


def test_floating_assistant_displays_specialist_owner():
    source = (ROOT / "frontend/components/assistant/FloatingDataVisionAssistant.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/components/assistant/FloatingDataVisionAssistant.module.css").read_text(encoding="utf-8")
    assert "agentLabel(step.agent_role)" in source
    assert 'data_agent: "Data Agent"' in source
    assert 'critic_agent: "Critic Agent"' in source
    assert ".planAgent" in css


def test_backend_exposes_multi_agent_topology_endpoint():
    source = (ROOT / "backend/app/assistant/router.py").read_text(encoding="utf-8")
    assert '@router.get("/agents")' in source
    assert 'multi_agent_coordinator.topology(executable_only=True)' in source
