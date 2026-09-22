from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _fresh_store(tmp_path, monkeypatch):
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'auth2815.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "self_registration_enabled", True)
    monkeypatch.setattr(settings, "demo_account_enabled", False)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    metadata_store.init_metadata_store()


def test_standard_signup_creates_isolated_owner_workspace_and_logs_in(tmp_path, monkeypatch):
    _fresh_store(tmp_path, monkeypatch)
    payload = {
        "email": "new.user@datavision.local",
        "password": "DataVision8!",
        "display_name": "Nouvel Utilisateur",
        "organization_name": "Acme Analytics",
    }
    created = client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["user"]["email"] == payload["email"]
    assert body["access_token"]
    assert body["workspace_id"]

    session = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert session.status_code == 200, session.text
    me = session.json()
    assert me["organizations"][0]["role"] == "owner"
    assert me["workspaces"][0]["role"] == "owner"

    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200, login.text


def test_duplicate_signup_and_disabled_registration_are_rejected(tmp_path, monkeypatch):
    _fresh_store(tmp_path, monkeypatch)
    payload = {"email":"same@datavision.local","password":"DataVision8!","display_name":"Same","organization_name":"Same Org"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 200
    duplicate = client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 400
    assert "existe déjà" in duplicate.text

    settings = get_settings()
    monkeypatch.setattr(settings, "self_registration_enabled", False)
    denied = client.post("/api/v1/auth/register", json={**payload, "email":"other@datavision.local"})
    assert denied.status_code == 403


def test_auth_gate_has_standard_login_signup_switch():
    source = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/lib/api.ts").read_text(encoding="utf-8")
    css = (ROOT / "frontend/app/globals.css").read_text(encoding="utf-8")
    for needle in ("Connexion", "Inscription", "Créer votre compte", "Pas encore de compte ?", "Vous avez déjà un compte ?"):
        assert needle in source
    assert "registerEnterprise" in source
    assert "`${API}/auth/register`" in api
    assert ".auth-mode-tabs" in css
