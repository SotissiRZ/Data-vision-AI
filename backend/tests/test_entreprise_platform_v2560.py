from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'entreprise256.db'}")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    res = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "owner256@datavision.local",
            "password": "EntreprisePass123!",
            "display_name": "Owner 256",
            "organization_name": "Entreprise 256",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return body, headers


def test_v256_scim_token_is_hashed_and_user_lifecycle_is_workspace_scoped(tmp_path, monkeypatch):
    from app.services.metadata_store import fetch_one

    boot, headers = _boot(tmp_path, monkeypatch)
    org, ws = boot["organization_id"], boot["workspace_id"]
    created = client.post(
        f"/api/v1/organizations/{org}/scim/tokens",
        headers=headers,
        json={"workspace_id": ws, "name": "Entra ID SCIM", "default_role": "analyst"},
    )
    assert created.status_code == 200, created.text
    token_body = created.json()
    raw = token_body["token"]
    assert raw.startswith("dvscim_")
    stored = fetch_one("SELECT token_hash,token_prefix FROM organization_scim_tokens WHERE id=:id", {"id": token_body["id"]})
    assert stored["token_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert raw != stored["token_hash"] and raw not in str(stored)

    scim_headers = {"Authorization": f"Bearer {raw}"}
    provisioned = client.post(
        "/api/v1/scim/v2/Users",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "externalId": "entra-user-42",
            "userName": "analyst256@example.com",
            "displayName": "Analyste SCIM",
            "active": True,
            "roles": [{"value": "analyst"}],
        },
    )
    assert provisioned.status_code == 201, provisioned.text
    user = provisioned.json()
    assert user["userName"] == "analyst256@example.com"
    assert user["roles"][0]["value"] == "analyst"
    assert user["urn:datavision:params:scim:schemas:extension:2.0:User"]["workspaceId"] == ws

    patched = client.patch(
        f"/api/v1/scim/v2/Users/{user['id']}",
        headers=scim_headers,
        json={"Operations": [{"op": "Replace", "path": "roles", "value": [{"value": "viewer"}]}]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["roles"][0]["value"] == "viewer"

    listed = client.get("/api/v1/scim/v2/Users", headers=scim_headers)
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == user["id"] for item in listed.json()["Resources"])

    removed = client.delete(f"/api/v1/scim/v2/Users/{user['id']}", headers=scim_headers)
    assert removed.status_code == 204, removed.text
    fetched = client.get(f"/api/v1/scim/v2/Users/{user['id']}", headers=scim_headers)
    assert fetched.status_code == 200
    assert fetched.json()["active"] is False


def test_v256_oidc_discovery_routes_by_allowed_email_domain(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    payload = {
        "name": "SSO Exemple",
        "issuer": "https://login.example.com",
        "client_id": "datavision-client",
        "client_secret": "not-a-real-secret",
        "authorization_endpoint": "https://login.example.com/authorize",
        "token_endpoint": "https://login.example.com/token",
        "jwks_uri": "https://login.example.com/jwks",
        "allowed_domains": ["example.com"],
        "default_role": "viewer",
        "enabled": True,
    }
    made = client.post(f"/api/v1/workspaces/{ws}/identity/oidc", headers=headers, json=payload)
    assert made.status_code == 200, made.text

    yes = client.get("/api/v1/auth/oidc/discover?email=user@example.com")
    no = client.get("/api/v1/auth/oidc/discover?email=user@other.test")
    assert yes.status_code == 200 and no.status_code == 200
    assert [p["name"] for p in yes.json()["providers"]] == ["SSO Exemple"]
    assert no.json()["providers"] == []


def test_v256_private_ai_enforcement_and_prometheus_export(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]

    before = client.get(f"/api/v1/workspaces/{ws}/entreprise/private-ai", headers=headers)
    assert before.status_code == 200, before.text
    enforced = client.post(f"/api/v1/workspaces/{ws}/entreprise/private-ai/enforce", headers=headers)
    assert enforced.status_code == 200, enforced.text
    body = enforced.json()
    assert body["strict_private_ai"] is True
    assert body["privacy_mode"] == "local_only"
    assert body["allow_external_ai"] is False
    assert body["raw_rows_external_allowed"] is False

    metrics = client.get(f"/api/v1/workspaces/{ws}/metrics/prometheus", headers=headers)
    assert metrics.status_code == 200, metrics.text
    assert "text/plain" in metrics.headers["content-type"]
    assert "datavision_http_requests_total" in metrics.text
    assert f'workspace_id="{ws}"' in metrics.text


def test_v256_readiness_reports_entreprise_and_onprem_posture(tmp_path, monkeypatch):
    from app.services import entreprise_platform

    boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    monkeypatch.setattr(entreprise_platform, "antivirus_status", lambda: {"mode": "required", "available": True})
    monkeypatch.setattr(entreprise_platform, "kms_status", lambda: {"dedicated_key": True, "key_id": "test-key"})

    out = client.get(f"/api/v1/workspaces/{ws}/entreprise/readiness", headers=headers)
    assert out.status_code == 200, out.text
    body = out.json()
    current_version = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    assert body["version"] == current_version
    assert body["edition"] == "Entreprise"
    assert body["deployment"]["profile"] == "onprem"
    assert body["deployment"]["external_egress_policy"] == "explicit_opt_in"
    ids = {c["id"] for c in body["checks"]}
    assert {"tenant_isolation", "sso", "mfa", "scim", "private_ai", "kms", "antivirus", "observability"}.issubset(ids)
