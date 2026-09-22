from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v263.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "secret_auto_rotation_enabled", True)
    monkeypatch.setattr(settings, "release_rollback_enabled", True)
    monkeypatch.setattr(settings, "release_rollback_executor", "plan_only")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    res = client.post("/api/v1/auth/bootstrap", json={
        "email": "sec263@datavision.local", "password": "SecPass263!Safe", "display_name": "Sec 263", "organization_name": "Entreprise Sec 263"
    })
    assert res.status_code == 200, res.text
    body = res.json()
    return settings, body, {"Authorization": f"Bearer {body['access_token']}"}


def test_v263_generated_secret_rotation_is_explicit_and_audited(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    from app.services import metadata_store
    ws = boot["workspace_id"]
    created = client.post(f"/api/v1/workspaces/{ws}/secrets", headers=headers, json={
        "name": "managed-webhook", "provider": "local_encrypted", "value": "initial-secret",
        "reference": {"rotation": {"mode": "generated", "days": 1}},
    })
    assert created.status_code == 200, created.text
    sid = created.json()["secret"]["id"]
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    metadata_store.execute("UPDATE secret_vault_versions SET created_at=:old WHERE secret_id=:sid", {"old": old, "sid": sid})
    status = client.get(f"/api/v1/workspaces/{ws}/secrets/rotation/status", headers=headers)
    assert status.status_code == 200 and status.json()["due_count"] == 1
    plan = client.post(f"/api/v1/workspaces/{ws}/secrets/rotation/run", headers=headers, json={"confirm": False})
    assert plan.status_code == 200 and plan.json()["results"][0]["status"] == "planned"
    run = client.post(f"/api/v1/workspaces/{ws}/secrets/rotation/run", headers=headers, json={"confirm": True})
    assert run.status_code == 200 and run.json()["results"][0]["status"] == "rotated"
    events = client.get(f"/api/v1/workspaces/{ws}/secrets/rotation/events", headers=headers).json()["events"]
    assert events and events[0]["status"] == "rotated" and events[0]["new_version"] == 2


def test_v263_external_secrets_are_never_auto_rotated(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    res = client.post(f"/api/v1/workspaces/{ws}/secrets", headers=headers, json={
        "name": "external-env", "provider": "env", "reference": {"variable": "EXTERNAL_API_TOKEN", "rotation": {"mode": "generated", "days": 1}}
    })
    assert res.status_code == 200, res.text
    status = client.get(f"/api/v1/workspaces/{ws}/secrets/rotation/status", headers=headers).json()
    item = next(x for x in status["secrets"] if x["name"] == "external-env")
    assert item["eligible_for_automatic_rotation"] is False and item["due"] is False


def test_v263_release_rollback_requires_two_phase_confirmation(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    org = boot["organization_id"]
    plan = client.post(f"/api/v1/organizations/{org}/release/rollback/plan", headers=headers, json={
        "target_version": "2.62.0", "reason": "controlled rollback test", "artifact_sha256": "a" * 64
    })
    assert plan.status_code == 200, plan.text
    p = plan.json()
    denied = client.post(f"/api/v1/organizations/{org}/release/rollback/confirm", headers=headers, json={"plan_id": p["plan_id"], "confirmation_token": "x" * 32})
    assert denied.status_code == 403
    ok = client.post(f"/api/v1/organizations/{org}/release/rollback/confirm", headers=headers, json={"plan_id": p["plan_id"], "confirmation_token": p["confirmation_token"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "confirmed_manual" and ok.json()["result"]["executed"] is False


def test_v263_rollback_drill_is_non_destructive(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    org = boot["organization_id"]
    res = client.post(f"/api/v1/organizations/{org}/release/rollback/drill", headers=headers, json={"target_version": "2.62.0", "artifact_sha256": "b" * 64})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "passed" and body["executed"] is False and all(body["checks"].values())


def test_v263_supply_chain_assets_are_shipped():
    root = Path(__file__).resolve().parents[2]
    rego = (root / "policies/kubernetes/datavision.rego").read_text(encoding="utf-8")
    release = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    cron = (root / "deploy/helm/datavision/templates/secret-rotation-cronjob.yaml").read_text(encoding="utf-8")
    assert "deny[msg]" in rego and ":latest" in rego and "CHANGE_ME" in rego
    assert "cosign sign --yes" in release and "cosign sign-blob" in release and "provenance: mode=max" in release
    assert "rotate-secrets" in cron and "concurrencyPolicy: Forbid" in cron


def test_v263_migration_and_runbook_are_shipped():
    root = Path(__file__).resolve().parents[2]
    migrations = (root / "backend/app/services/schema_migrations.py").read_text(encoding="utf-8")
    runbook = (root / "backend/app/ops/security.py").read_text(encoding="utf-8")
    assert 'version="2.63.0-001"' in migrations and "secret_rotation_events" in migrations and "release_rollback_events" in migrations
    assert "rotate-secrets" in runbook and "rollback-plan" in runbook and "rollback-confirm" in runbook and "rollback-drill" in runbook
