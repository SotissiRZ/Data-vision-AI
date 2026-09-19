from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_preferences_api_routes_exist():
    routes = (ROOT / "backend/app/api/routes/enterprise.py").read_text()
    assert '@router.get("/auth/preferences")' in routes
    assert '@router.put("/auth/preferences")' in routes
    assert "UserPreferencesRequest" in routes


def test_frontend_has_keyboard_zoom_and_profile_sync():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()

    assert "getEnterprisePreferences" in page
    assert "saveEnterprisePreferences" in page
    assert "e.key==='+'||e.key==='='" in page
    assert "e.key==='-'" in page
    assert "e.key==='0'" in page
    assert "displayToolsRef.current.contains" in page
    assert "pointerdown" in page
    assert "getEnterprisePreferences" in api
    assert "saveEnterprisePreferences" in api


def test_assistant_coalesces_redundant_proactive_observation_calls():
    assistant = (
        ROOT / "frontend/components/assistant/FloatingDataVisionAssistant.tsx"
    ).read_text()
    assert "pendingObservationRef" in assistant
    assert "lastObservationKeyRef" in assistant
    assert "now - lastObservationAtRef.current < 1500" in assistant
    assert "}, 280);" in assistant
