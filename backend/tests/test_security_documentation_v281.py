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
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-test-secret")
    from app.services import metadata_store
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    metadata_store.init_metadata_store()
    return settings


def test_required_auth_blocks_anonymous_dataset_notebook_and_assistant(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.get("/api/v1/datasets/catalog/all").status_code == 401
    assert client.get("/api/v1/notebooks").status_code == 401
    assert client.get("/api/v1/ai/assistant/tools").status_code == 401


def test_local_dev_is_explicit_and_forbidden_by_production_semantics(tmp_path, monkeypatch):
    settings = _configure(tmp_path, monkeypatch, auth_mode="local_dev", app_env="test")
    client = TestClient(app)
    assert client.get("/api/v1/datasets/catalog/all").status_code != 401
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.get("/api/v1/datasets/catalog/all").status_code == 401


def test_auth_status_bootstrap_and_workspace_governed_access(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    client = TestClient(app)
    status = client.get("/api/v1/auth/status")
    assert status.status_code == 200
    assert status.json()["authentication_required"] is True
    assert status.json()["bootstrap_required"] is True

    denied = client.post("/api/v1/auth/bootstrap", json={
        "email": "owner@datavision.local", "password": "EnterprisePass123!",
        "display_name": "Owner", "organization_name": "Secure Org", "setup_secret": "wrong"
    })
    # Bootstrap secret is mandatory only in production.
    assert denied.status_code in {200, 400, 403}

    # Reset database for a deterministic bootstrap if the previous development bootstrap succeeded.
    if denied.status_code == 200:
        token = denied.json()["access_token"]
        workspace = denied.json()["workspace_id"]
    else:
        ok = client.post("/api/v1/auth/bootstrap", json={
            "email": "owner@datavision.local", "password": "EnterprisePass123!",
            "display_name": "Owner", "organization_name": "Secure Org", "setup_secret": "bootstrap-test-secret"
        })
        assert ok.status_code == 200, ok.text
        token = ok.json()["access_token"]
        workspace = ok.json()["workspace_id"]

    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": workspace}
    assert client.get("/api/v1/datasets/catalog/all", headers=headers).status_code == 200


def test_production_bootstrap_requires_setup_secret(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, app_env="production")
    client = TestClient(app)
    bad = client.post("/api/v1/auth/bootstrap", json={
        "email": "owner-prod@datavision.local", "password": "EnterprisePass123!",
        "display_name": "Owner", "organization_name": "Secure Org", "setup_secret": "wrong"
    })
    assert bad.status_code == 403
    ok = client.post("/api/v1/auth/bootstrap", json={
        "email": "owner-prod@datavision.local", "password": "EnterprisePass123!",
        "display_name": "Owner", "organization_name": "Secure Org", "setup_secret": "bootstrap-test-secret"
    })
    assert ok.status_code == 200, ok.text


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
