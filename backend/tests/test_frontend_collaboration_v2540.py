from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")


def test_v254_frontend_exposes_realtime_teams_shares_diff_and_decisions():
    assert "createCollaborationRealtimeTicket" in PAGE
    assert "collaborationWebSocketUrl" in PAGE
    assert "new WebSocket" in PAGE
    assert "Temps réel" in PAGE
    assert "Équipes" in PAGE
    assert "Partager un artefact" in PAGE
    assert "Diff de version" in PAGE
    assert "Décisions récentes" in PAGE


def test_v254_frontend_api_uses_one_time_ws_ticket_not_jwt_query():
    assert "/collaboration/ws-ticket" in API
    assert "?ticket=" in API
    assert "?token=" not in API


def test_v254_outgoing_collaboration_events_are_selectable():
    for event in ["review_submitted","review_changes_requested","review_assigned","review_comment","review_mention","artifact_shared"]:
        assert f'value="{event}"' in PAGE


def test_v254_collaboration_styles_respect_global_typography_floor():
    assert ".collaboration-workspace-grid" in CSS
    assert ".review-realtime" in CSS
    assert "font-size:12.5px" in CSS
