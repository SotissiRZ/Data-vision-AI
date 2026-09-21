from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'hardening258.db'}")
    monkeypatch.setattr(settings, "otel_internal_metrics_token", "otel-test-token")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    res = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "owner258@datavision.local",
            "password": "HardeningPass123!",
            "display_name": "Owner 258",
            "organization_name": "Entreprise 258",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def test_v258_scim_groups_manage_membership_and_role_mapping(tmp_path, monkeypatch):
    from app.services.metadata_store import fetch_one

    boot, headers = _boot(tmp_path, monkeypatch)
    org, ws = boot["organization_id"], boot["workspace_id"]
    token = client.post(
        f"/api/v1/organizations/{org}/scim/tokens",
        headers=headers,
        json={"workspace_id": ws, "name": "SCIM 258", "default_role": "viewer"},
    )
    assert token.status_code == 200, token.text
    scim_headers = {"Authorization": f"Bearer {token.json()['token']}"}

    user = client.post(
        "/api/v1/scim/v2/Users",
        headers=scim_headers,
        json={"userName": "group.user@example.com", "displayName": "Group User", "active": True},
    )
    assert user.status_code == 201, user.text
    user_id = user.json()["id"]

    group = client.post(
        "/api/v1/scim/v2/Groups",
        headers=scim_headers,
        json={
            "externalId": "idp-group-1",
            "displayName": "Data Scientists",
            "members": [{"value": user_id}],
            "urn:datavision:params:scim:schemas:extension:2.0:Group": {"role": "data_scientist"},
        },
    )
    assert group.status_code == 201, group.text
    body = group.json()
    assert body["displayName"] == "Data Scientists"
    assert body["members"][0]["value"] == user_id
    assert body["urn:datavision:params:scim:schemas:extension:2.0:Group"]["role"] == "data_scientist"
    membership = fetch_one(
        "SELECT role FROM workspace_members WHERE workspace_id=:ws AND user_id=:user",
        {"ws": ws, "user": user_id},
    )
    assert membership["role"] == "data_scientist"

    listed = client.get("/api/v1/scim/v2/Groups", headers=scim_headers)
    assert listed.status_code == 200 and listed.json()["totalResults"] == 1

    patched = client.patch(
        f"/api/v1/scim/v2/Groups/{body['id']}",
        headers=scim_headers,
        json={"Operations": [{"op": "Remove", "path": "members", "value": [{"value": user_id}]}]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["members"] == []

    deleted = client.delete(f"/api/v1/scim/v2/Groups/{body['id']}", headers=scim_headers)
    assert deleted.status_code == 204, deleted.text


def test_v258_session_policy_trusted_device_and_active_session_cap(tmp_path, monkeypatch):
    from app.services.metadata_store import fetch_one

    boot, headers = _boot(tmp_path, monkeypatch)
    org = boot["organization_id"]

    # Create a regular browser session, then approve that exact device before enforcing managed devices.
    login = client.post(
        "/api/v1/auth/login",
        headers={"User-Agent": "DataVision-Test-Browser/1.0"},
        json={"email": "owner258@datavision.local", "password": "HardeningPass123!"},
    )
    assert login.status_code == 200, login.text
    trusted_session_id = login.json()["session_id"]
    approved = client.post(
        f"/api/v1/organizations/{org}/security/trusted-devices",
        headers=headers,
        json={"session_id": trusted_session_id, "label": "Portable géré"},
    )
    assert approved.status_code == 200, approved.text

    policy = client.put(
        f"/api/v1/organizations/{org}/security/session-policy",
        headers=headers,
        json={
            "idle_timeout_minutes": 30,
            "max_session_hours": 12,
            "max_active_sessions": 2,
            "trusted_device_days": 30,
            "require_managed_device": True,
        },
    )
    assert policy.status_code == 200, policy.text
    assert policy.json()["require_managed_device"] is True

    # Same browser fingerprint is accepted; another browser is blocked.
    same = client.post(
        "/api/v1/auth/login",
        headers={"User-Agent": "DataVision-Test-Browser/1.0"},
        json={"email": "owner258@datavision.local", "password": "HardeningPass123!"},
    )
    assert same.status_code == 200, same.text
    other = client.post(
        "/api/v1/auth/login",
        headers={"User-Agent": "Unknown-Browser/9.9"},
        json={"email": "owner258@datavision.local", "password": "HardeningPass123!"},
    )
    assert other.status_code == 403, other.text

    # With a cap of 2, the oldest active session is revoked as new compliant sessions are created.
    first = fetch_one("SELECT revoked_at FROM auth_sessions WHERE id=:id", {"id": boot["session_id"]})
    assert first["revoked_at"] is not None


def test_v258_session_idle_timeout_is_enforced_on_authenticated_requests(tmp_path, monkeypatch):
    from app.services.metadata_store import execute

    boot, headers = _boot(tmp_path, monkeypatch)
    org = boot["organization_id"]
    changed = client.put(
        f"/api/v1/organizations/{org}/security/session-policy",
        headers=headers,
        json={
            "idle_timeout_minutes": 5,
            "max_session_hours": 12,
            "max_active_sessions": 10,
            "trusted_device_days": 30,
            "require_managed_device": False,
        },
    )
    assert changed.status_code == 200, changed.text
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    execute("UPDATE auth_sessions SET last_seen_at=:old WHERE id=:id", {"old": old, "id": boot["session_id"]})
    expired = client.get("/api/v1/auth/sessions", headers=headers)
    assert expired.status_code == 401, expired.text


def test_v258_vault_transit_kms_roundtrip_uses_external_ciphertext(monkeypatch):
    from app.core.config import get_settings
    from app.services import secret_crypto

    settings = get_settings()
    monkeypatch.setattr(settings, "secret_kms_provider", "vault_transit")
    monkeypatch.setattr(settings, "vault_addr", "https://vault.example.internal")
    monkeypatch.setattr(settings, "vault_token", "test-token")
    monkeypatch.setattr(settings, "vault_transit_mount", "transit")
    monkeypatch.setattr(settings, "vault_transit_key", "datavision")
    monkeypatch.setattr(settings, "vault_transit_hsm_backed", True)

    class Response:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    def fake_post(url, *, headers, json, timeout):
        assert headers["X-Vault-Token"] == "test-token"
        if "/encrypt/" in url:
            plain = base64.b64decode(json["plaintext"]).decode()
            assert plain == "super-secret"
            return Response({"data": {"ciphertext": "vault:v1:opaque-ciphertext"}})
        assert json["ciphertext"] == "vault:v1:opaque-ciphertext"
        return Response({"data": {"plaintext": base64.b64encode(b"super-secret").decode()}})

    monkeypatch.setattr(secret_crypto.httpx, "post", fake_post)
    encrypted = secret_crypto.encrypt_secret("super-secret", aad="workspace:test")
    assert encrypted.startswith("dvkms2:vault_transit:")
    assert "super-secret" not in encrypted
    assert secret_crypto.decrypt_secret(encrypted, aad="workspace:test") == "super-secret"
    status = secret_crypto.kms_status()
    assert status["external_kms"] is True
    assert status["hsm_backed"] is True
    assert status["production_ready"] is True


def test_v258_internal_metrics_are_token_protected_for_otel(tmp_path, monkeypatch):
    _boot(tmp_path, monkeypatch)
    denied = client.get("/api/v1/metrics/internal")
    assert denied.status_code == 401
    allowed = client.get(
        "/api/v1/metrics/internal",
        headers={"Authorization": "Bearer otel-test-token"},
    )
    assert allowed.status_code == 200, allowed.text
    assert "datavision_up 1" in allowed.text


def test_v258_packaging_contains_otel_and_helm_chart():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    otel = (root / "infra/otel-collector-config.yaml").read_text(encoding="utf-8")
    chart = (root / "deploy/helm/datavision/Chart.yaml").read_text(encoding="utf-8")
    values = (root / "deploy/helm/datavision/values.yaml").read_text(encoding="utf-8")
    sandbox = (root / "deploy/helm/datavision/templates/sandbox.yaml").read_text(encoding="utf-8")
    pvc = (root / "deploy/helm/datavision/templates/pvc.yaml").read_text(encoding="utf-8")
    helpers = (root / "deploy/helm/datavision/templates/_helpers.tpl").read_text(encoding="utf-8")
    assert "otel/opentelemetry-collector-contrib:0.161.0" in compose
    assert "prometheus:" in otel and "otlp:" in otel
    current_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert f'appVersion: "{current_version}"' in chart
    assert f'tag: "{current_version}"' in values
    assert "ReadWriteMany" in values and "persistence.accessModes" in pvc
    assert 'existingSecret: ""' in values and 'define "datavision.secretName"' in helpers
    assert "readOnlyRootFilesystem: true" in sandbox
    assert 'capabilities: {drop: ["ALL"]}' in sandbox
