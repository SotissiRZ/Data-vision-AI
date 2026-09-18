from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_orchestrator_adapter_calls_turn_endpoint():
    text = (ROOT / "frontend/lib/assistant/orchestrator-adapter.ts").read_text()
    assert "runAssistantTurn" in text
    assert "continueAssistantTurn" in text
    assert "confirmAssistantAction" in text


def test_floating_component_displays_plan():
    text = (
        ROOT
        / "frontend/components/assistant/FloatingDataVisionAssistant.tsx"
    ).read_text()
    assert "Plan DataVision" in text
    assert "stepStatusIcon" in text


def test_root_uses_orchestrator_adapter():
    text = (
        ROOT
        / "frontend/components/assistant/DataVisionAssistantRoot.tsx"
    ).read_text()
    assert "createOrchestratorAssistantAdapter" in text
