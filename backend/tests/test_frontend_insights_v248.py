from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")


def test_v248_frontend_exposes_insight_engine_view_and_navigation():
    assert "Insight Engine" in PAGE
    assert "view==='insights'" in PAGE
    assert "defaultView:'insights'" in PAGE
    assert "priority_score" in PAGE
    assert "Preuve & traçabilité" in PAGE


def test_v248_frontend_uses_real_insight_endpoints():
    assert "/insights?limit=" in API
    assert "/insights/scan" in API
    assert "/insights/history" in API
    assert "scanInsights" in PAGE
    assert "getInsightHistory" in PAGE


def test_v248_home_dashboard_is_wired_to_insight_feed():
    assert "d.insights" in PAGE or "d?.insights" in PAGE
