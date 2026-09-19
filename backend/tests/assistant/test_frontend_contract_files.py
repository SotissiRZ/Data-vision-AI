from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


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


def test_model_gateway_frontend_contract_exists():
    text = (ROOT / "frontend/lib/assistant/model-gateway.ts").read_text()
    assert "local_only" in text
    assert "allowExternalAi" in text
    assert "previewAssistantModelRoute" in text


def test_floating_assistant_uses_native_css_module():
    component = (
        ROOT
        / "frontend/components/assistant/FloatingDataVisionAssistant.tsx"
    ).read_text()
    css = (
        ROOT
        / "frontend/components/assistant/FloatingDataVisionAssistant.module.css"
    ).read_text()

    assert 'FloatingDataVisionAssistant.module.css' in component
    assert 'className="fixed bottom-6' not in component
    assert "position: fixed" in css
    assert "z-index: 2147483002" in css
    assert "DV" in component


def test_tts_sanitizer_removes_parenthetical_plural_markers():
    text = (ROOT / "frontend/lib/assistant/speech-text.ts").read_text()
    assert r'.replace(/\(s\)/gi, "")' in text
    component = (
        ROOT
        / "frontend/components/assistant/FloatingDataVisionAssistant.tsx"
    ).read_text()
    assert "toSpeechText(response.message)" in component


def test_ai_control_center_is_integrated():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    component = (
        ROOT
        / "frontend/components/assistant/AIProviderControlCenter.tsx"
    ).read_text()
    client = (
        ROOT
        / "frontend/lib/assistant/settings-client.ts"
    ).read_text()

    assert "'ai-settings'" in page
    assert "IA & Modèles" in page
    assert "AIProviderControlCenter" in page
    assert "Model Gateway + garde-fous" in component
    assert "/ai/assistant/settings/providers" in client
    assert "monthly_budget_usd" in component


def test_context_exposes_schema_without_rows():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    assert "datasetSchema" in page
    assert "dtype: column.dtype" in page
