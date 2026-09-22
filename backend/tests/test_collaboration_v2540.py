from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch, suffix: str = "254"):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / ('collab-' + suffix + '.db')}")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    res = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": f"owner-{suffix}@datavision.local",
            "password": "EnterprisePass123!",
            "display_name": f"Owner {suffix}",
            "organization_name": f"Collaboration {suffix}",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _member(ws: str, headers: dict[str, str], suffix: str, role: str = "analyst") -> dict:
    res = client.post(
        f"/api/v1/workspaces/{ws}/members",
        headers=headers,
        json={
            "email": f"member-{suffix}@datavision.local",
            "role": role,
            "display_name": f"Member {suffix}",
            "password": "MemberPass123!Safe",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["member"]


def test_v254_workspace_teams_are_real_membership_objects(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch, "team")
    ws = boot["workspace_id"]
    member = _member(ws, headers, "team")
    created = client.post(
        f"/api/v1/workspaces/{ws}/collaboration/teams",
        headers=headers,
        json={"name": "Revenue Squad", "description": "Revue revenue", "member_user_ids": [member["id"]]},
    )
    assert created.status_code == 200, created.text
    team = created.json()["team"]
    assert team["member_count"] == 1
    assert team["members"][0]["id"] == member["id"]
    listed = client.get(f"/api/v1/workspaces/{ws}/collaboration/teams", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["teams"][0]["name"] == "Revenue Squad"


def test_v254_governed_share_is_targeted_and_revocable(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch, "share")
    ws = boot["workspace_id"]
    member = _member(ws, headers, "share", "viewer")
    shared = client.post(
        f"/api/v1/workspaces/{ws}/collaboration/shares",
        headers=headers,
        json={
            "resource_type": "report", "resource_id": "report-254", "resource_version": "v2",
            "recipient_user_id": member["id"], "permission": "view", "note": "À lire avant comité",
        },
    )
    assert shared.status_code == 200, shared.text
    share = shared.json()["share"]
    assert share["active"] is True
    assert "token" not in share and "public_url" not in share
    login = client.post("/api/v1/auth/login", json={"email":"member-share@datavision.local","password":"MemberPass123!Safe"})
    mh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    received = client.get(f"/api/v1/workspaces/{ws}/collaboration/shares?scope=received", headers=mh)
    assert received.status_code == 200, received.text
    assert received.json()["shares"][0]["resource_id"] == "report-254"
    revoked = client.post(f"/api/v1/workspaces/{ws}/collaboration/shares/{share['id']}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["share"]["active"] is False


def test_v254_review_diff_compares_persisted_snapshots(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch, "diff")
    ws = boot["workspace_id"]
    first = client.post(
        f"/api/v1/workspaces/{ws}/reviews", headers=headers,
        json={"resource_type":"report","resource_id":"report-diff","title":"Rapport v1","resource_version":"v1","snapshot":{"title":"Rapport","kpi":{"revenue":100}}},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/workspaces/{ws}/reviews", headers=headers,
        json={"resource_type":"report","resource_id":"report-diff","title":"Rapport v2","resource_version":"v2","snapshot":{"title":"Rapport","kpi":{"revenue":125},"section":"Risques"}},
    )
    rid = second.json()["review"]["id"]
    diff = client.get(f"/api/v1/workspaces/{ws}/reviews/{rid}/diff", headers=headers)
    assert diff.status_code == 200, diff.text
    body = diff.json()["diff"]
    assert body["baseline_review_id"] == first.json()["review"]["id"]
    assert body["changed"] is True and body["change_count"] >= 2
    assert any(row["path"] == "kpi.revenue" for row in body["changes"])
    assert len(body["diff_sha256"]) == 64


def test_v254_decision_ledger_is_derived_from_append_only_review_events(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch, "decision")
    ws = boot["workspace_id"]
    review = client.post(f"/api/v1/workspaces/{ws}/reviews", headers=headers, json={"resource_type":"dashboard","resource_id":"dash-254","title":"Dashboard comité"}).json()["review"]
    rid = review["id"]
    assert client.post(f"/api/v1/workspaces/{ws}/reviews/{rid}/transition", headers=headers, json={"action":"submit","note":"go"}).status_code == 200
    assert client.post(f"/api/v1/workspaces/{ws}/reviews/{rid}/transition", headers=headers, json={"action":"approve","note":"KPI vérifiés"}).status_code == 200
    ledger = client.get(f"/api/v1/workspaces/{ws}/collaboration/decisions", headers=headers)
    assert ledger.status_code == 200
    decision = ledger.json()["decisions"][0]
    assert decision["action"] == "approve"
    assert decision["resource_id"] == "dash-254"
    assert decision["payload"]["note"] == "KPI vérifiés"


def test_v254_realtime_ticket_is_short_lived_one_time_and_ws_works(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch, "ws")
    ws = boot["workspace_id"]
    ticket_res = client.post(f"/api/v1/workspaces/{ws}/collaboration/ws-ticket", headers=headers)
    assert ticket_res.status_code == 200, ticket_res.text
    ticket = ticket_res.json()["ticket"]
    assert ticket and len(ticket) > 24
    with client.websocket_connect(f"/api/v1/workspaces/{ws}/collaboration/ws?ticket={ticket}") as socket:
        first = socket.receive_json()
        assert first["type"] == "collaboration.snapshot"
        assert "summary" in first
    from app.services.collaboration import consume_realtime_ticket
    with pytest.raises(PermissionError, match="déjà utilisé"):
        consume_realtime_ticket(ticket, ws)


def test_v254_mark_all_notifications_read(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch, "notif")
    ws = boot["workspace_id"]
    member = _member(ws, headers, "notif")
    client.post(
        f"/api/v1/workspaces/{ws}/reviews", headers=headers,
        json={"resource_type":"dataset","resource_id":"ds-notif","title":"Dataset notif","reviewer_user_id":member["id"]},
    )
    login = client.post("/api/v1/auth/login", json={"email":"member-notif@datavision.local","password":"MemberPass123!Safe"})
    mh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    before = client.get(f"/api/v1/workspaces/{ws}/collaboration/notifications", headers=mh).json()["notifications"]
    assert any(not x["is_read"] for x in before)
    marked = client.post(f"/api/v1/workspaces/{ws}/collaboration/notifications/read-all", headers=mh)
    assert marked.status_code == 200 and marked.json()["marked_read"] >= 1
    after = client.get(f"/api/v1/workspaces/{ws}/collaboration/notifications", headers=mh).json()["notifications"]
    assert all(x["is_read"] for x in after)


def test_v254_collaboration_events_are_governed_action_sources():
    from app.services.governed_actions import ALLOWED_EVENT_TYPES
    expected = {"review_assigned","review_submitted","review_changes_requested","review_comment","review_mention","artifact_shared"}
    assert expected.issubset(ALLOWED_EVENT_TYPES)
