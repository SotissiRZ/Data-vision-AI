from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_assistant_is_globally_mounted_and_floating():
    layout = read("frontend/app/layout.tsx")
    root = read("frontend/components/assistant/DataVisionAssistantRoot.tsx")
    css = read("frontend/components/assistant/FloatingDataVisionAssistant.module.css")
    assert "<DataVisionAssistantRoot />" in layout
    assert "FloatingDataVisionAssistant" in root
    assert "position: fixed" in css


def test_turns_and_actions_use_live_context_snapshot():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    assert component.count("assistantEventBus.getContext()") >= 4
    assert "context: liveContext" in component
    assert "adapter.executeAction(action, liveContext)" in component
    assert "adapter.rejectAction(action, liveContext)" in component


def test_assistant_applies_host_effects_after_execution():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    effects = read("frontend/lib/assistant/effects.ts")
    page = read("frontend/app/page.tsx")
    assert "applyAssistantHostEffects(response, liveContext)" in component
    for tool in ("apply_reversible_transform", "merge_datasets", "delete_column"):
        assert tool in effects
    assert 'new CustomEvent("datavision:assistant-navigate"' in effects
    assert "assistantEventBus.setContext" in effects
    assert "refreshDataset" in page
    assert "activateDataset(detail.datasetId,nextView)" in page


def test_files_voice_and_governed_confirmation_are_connected():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    adapter = read("frontend/lib/assistant/orchestrator-adapter.ts")
    assert "adapter.uploadFiles" in component
    assert "BrowserVoiceController" in component
    assert "voice.listen" in component
    assert "voice.speak" in component
    assert "confirmAssistantAction" in adapter
    assert "continueAssistantTurn" in adapter


def test_adapter_uses_orchestrator_not_legacy_chat_endpoint():
    adapter = read("frontend/lib/assistant/orchestrator-adapter.ts")
    assert "runAssistantTurn" in adapter
    assert "autoExecuteSafeSteps: true" in adapter
    assert "turnRunId" in adapter
    assert "actionRunId" in adapter
