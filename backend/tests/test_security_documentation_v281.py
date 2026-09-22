from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def _configure(tmp_path, monkeypatch, *, auth_mode="required", app_env="test"):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v281.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "auth_secret", "v281-test-auth-secret-with-enough-entropy")
    monkeypatch.setattr(settings, "auth_mode", auth_mode)
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "first_run_setup_mode", "local")
    monkeypatch.setattr(settings, "password_min_length", 8)
    monkeypatch.setattr(settings, "demo_account_enabled", False)
    from app.services import metadata_store
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    metadata_store.init_metadata_store()
    return settings


def _local_client():
    return TestClient(app, base_url="http://localhost")


def _origin_headers():
    return {"Origin": "http://localhost:3005"}


def test_required_auth_blocks_anonymous_dataset_notebook_and_assistant(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    client = _local_client()
    assert client.get("/api/v1/datasets/catalog/all").status_code == 401
    assert client.get("/api/v1/notebooks").status_code == 401
    assert client.get("/api/v1/ai/assistant/tools").status_code == 401


def test_local_dev_is_explicit_and_forbidden_by_production_semantics(tmp_path, monkeypatch):
    settings = _configure(tmp_path, monkeypatch, auth_mode="local_dev", app_env="test")
    client = _local_client()
    assert client.get("/api/v1/datasets/catalog/all").status_code != 401
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.get("/api/v1/datasets/catalog/all").status_code == 401


def test_local_first_run_setup_is_automatic_and_one_time(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    client = _local_client()
    status = client.get("/api/v1/auth/status", headers=_origin_headers())
    assert status.status_code == 200
    assert status.json()["authentication_required"] is True
    assert status.json()["bootstrap_required"] is True
    assert status.json()["bootstrap_available"] is True
    assert status.json()["password_min_length"] == 8

    no_session = client.post("/api/v1/auth/bootstrap", headers=_origin_headers(), json={
        "email": "owner@datavision.local", "password": "Passw0rd!",
        "display_name": "Owner", "organization_name": "Secure Org",
    })
    assert no_session.status_code == 403

    setup = client.post("/api/v1/auth/setup-session", headers=_origin_headers())
    assert setup.status_code == 200
    cookie = setup.headers.get("set-cookie", "")
    assert "dv_first_run_setup=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie

    ok = client.post("/api/v1/auth/bootstrap", headers=_origin_headers(), json={
        "email": "owner@datavision.local", "password": "Passw0rd!",
        "display_name": "Owner", "organization_name": "Secure Org",
    })
    assert ok.status_code == 200, ok.text
    token = ok.json()["access_token"]
    workspace = ok.json()["workspace_id"]

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": workspace}
    assert client.get("/api/v1/datasets/catalog/all", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/setup-session", headers=_origin_headers()).status_code == 409


def test_remote_production_browser_cannot_claim_first_owner(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, app_env="production")
    client = TestClient(app, base_url="https://datavision.example")
    headers = {"Origin": "https://datavision.example"}
    status = client.get("/api/v1/auth/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["bootstrap_required"] is True
    assert status.json()["bootstrap_available"] is False
    denied = client.post("/api/v1/auth/setup-session", headers=headers)
    assert denied.status_code == 403


def test_password_minimum_is_eight_characters(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    client = _local_client()
    assert client.post("/api/v1/auth/setup-session", headers=_origin_headers()).status_code == 200
    short = client.post("/api/v1/auth/bootstrap", headers=_origin_headers(), json={
        "email": "owner@datavision.local", "password": "1234567",
        "display_name": "Owner", "organization_name": "Secure Org",
    })
    assert short.status_code == 422


def test_scrypt_default_cost_has_explicit_memory_budget(monkeypatch):
    from app.services.auth_service import hash_password, verify_password

    settings = get_settings()
    monkeypatch.setattr(settings, "password_min_length", 8)
    monkeypatch.setattr(settings, "password_scrypt_n", 131072)
    monkeypatch.setattr(settings, "password_scrypt_r", 8)
    monkeypatch.setattr(settings, "password_scrypt_p", 1)
    monkeypatch.setattr(settings, "password_scrypt_maxmem_mb", 256)
    encoded = hash_password("DataVision8!")
    assert verify_password("DataVision8!", encoded) is True
    assert verify_password("wrong-password", encoded) is False


def test_security_documents_are_present():
    root = Path(__file__).resolve().parents[2]
    required = [
        "docs/RAPPORT_TECHNIQUE.md",
        "docs/GUIDE_UTILISATEUR.md",
        "docs/GUIDE_DEPLOIEMENT.md",
        "docs/RAPPORT_SECURITE.md",
        "docs/GUIDE_EXPLOITATION.md",
        "docs/ARCHITECTURE.md",
    ]
    for relative in required:
        assert (root / relative).is_file(), relative


def test_demo_account_is_development_only_and_does_not_block_owner_setup(tmp_path, monkeypatch):
    settings = _configure(tmp_path, monkeypatch, app_env="development")
    monkeypatch.setattr(settings, "demo_account_enabled", True)
    monkeypatch.setattr(settings, "demo_account_email", "demo@datavision.local")
    monkeypatch.setattr(settings, "demo_account_password", "DataVision8!")
    monkeypatch.setattr(settings, "demo_account_display_name", "Utilisateur Démo")
    monkeypatch.setattr(settings, "demo_account_organization", "DataVision Démo")
    client = _local_client()

    status = client.get("/api/v1/auth/status", headers=_origin_headers())
    assert status.status_code == 200
    payload = status.json()
    assert payload["bootstrap_required"] is True
    assert payload["demo_account"]["enabled"] is True
    assert payload["demo_account"]["email"] == "demo@datavision.local"
    assert payload["demo_account"]["role"] == "admin"

    login = client.post("/api/v1/auth/login", json={"email": "demo@datavision.local", "password": "DataVision8!"})
    assert login.status_code == 200, login.text
    session = login.json()
    assert session["access_token"]

    setup = client.post("/api/v1/auth/setup-session", headers=_origin_headers())
    assert setup.status_code == 200
    owner = client.post("/api/v1/auth/bootstrap", headers=_origin_headers(), json={
        "email": "owner@datavision.local", "password": "Passw0rd!",
        "display_name": "Owner", "organization_name": "Secure Org",
    })
    assert owner.status_code == 200, owner.text


def test_demo_account_is_forced_off_in_production(tmp_path, monkeypatch):
    settings = _configure(tmp_path, monkeypatch, app_env="production")
    monkeypatch.setattr(settings, "demo_account_enabled", True)
    client = TestClient(app, base_url="https://datavision.example")
    status = client.get("/api/v1/auth/status", headers={"Origin": "https://datavision.example"})
    assert status.status_code == 200
    assert status.json()["demo_account"]["enabled"] is False


def test_frontend_auth_has_accessible_password_visibility_and_demo_button():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    css = (root / "frontend/app/globals.css").read_text(encoding="utf-8")
    assert "function PasswordInput" in page
    assert "Afficher le mot de passe" in page
    assert "Masquer le mot de passe" in page
    assert "aria-pressed={visible}" in page
    assert "Se connecter avec le compte test" in page
    assert "Vous avez déjà un compte ?" in page
    assert "Pas encore de compte ?" in page
    assert ">Inscription</button>" in page
    assert "Connexion DataVision Entreprise" not in page
    assert "password-eye" in css
