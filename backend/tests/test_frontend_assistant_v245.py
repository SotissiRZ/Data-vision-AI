from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_proactive_controls_are_user_governed():
    source = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    assert "snoozedAlertsRef" in source
    assert "5 * 60 * 1000" in source
    assert "voiceAlertMode" in source
    assert "datavision.assistant.voice.proactive_mode" in source
    assert "Masquer" in source


def test_generated_assistant_files_are_downloadable():
    source = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    adapter = read("frontend/lib/assistant/orchestrator-adapter.ts")
    contract = read("frontend/lib/assistant/orchestrator.ts")
    assert "file.downloadPath" in source
    assert "attachmentLink" in source
    assert "download_path" in adapter
    assert "attachments?: AgentTurnAttachment[]" in contract


def test_uploaded_files_are_distinguished_from_generated_files():
    source = read("frontend/lib/assistant/orchestrator-adapter.ts")
    assert 'kind: "uploaded"' in source
    assert 'kind: item.kind ?? "generated"' in source


def test_direct_backend_fallback_uses_api_v1():
    source = read("frontend/components/assistant/DataVisionAssistantRoot.tsx")
    assert 'http://localhost:8005/api/v1' in source
