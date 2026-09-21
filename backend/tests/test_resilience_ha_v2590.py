from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _sqlite(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'resilience259.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "backup_retention_count", 5)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    metadata_store.init_metadata_store()
    return settings


def test_v259_schema_migrations_are_versioned_and_readiness_aware(tmp_path, monkeypatch):
    _sqlite(tmp_path, monkeypatch)
    from app.services.metadata_store import fetch_one
    from app.services.schema_migrations import migration_status

    status = migration_status()
    assert status["ready"] is True
    assert "2.59.0-001" in status["applied"]
    row = fetch_one("SELECT name FROM schema_migrations WHERE version=:v", {"v": "2.59.0-001"})
    assert row and row["name"] == "resilience_operations"
    startup = client.get("/health/startup")
    assert startup.status_code == 200
    assert startup.json()["schema_migrations"]["ready"] is True


def test_v259_backup_is_manifested_hashed_and_restorable(tmp_path, monkeypatch):
    _sqlite(tmp_path, monkeypatch)
    from app.services.backup_service import create_backup, inspect_backup, restore_backup

    sample = tmp_path / "uploads" / "sample.txt"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("before", encoding="utf-8")
    created = create_backup(label="test")
    archive = Path(created["archive"])
    assert archive.is_file() and len(created["sha256"]) == 64
    inspected = inspect_backup(archive)
    assert inspected["manifest"]["format"] in {"datavision-backup-v1", "datavision-backup-v2"}
    current_version = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    assert inspected["manifest"]["product_version"] == current_version

    sample.write_text("after", encoding="utf-8")
    try:
        restore_backup(archive)
        raise AssertionError("restore must require explicit confirmation")
    except PermissionError:
        pass
    restored = restore_backup(archive, confirm=True)
    assert restored["status"] == "restored"
    assert sample.read_text(encoding="utf-8") == "before"


def test_v259_vault_transit_rotation_advances_key_version(tmp_path, monkeypatch):
    _sqlite(tmp_path, monkeypatch)
    from app.core.config import get_settings
    from app.services import secret_crypto

    settings = get_settings()
    monkeypatch.setattr(settings, "secret_kms_provider", "vault_transit")
    monkeypatch.setattr(settings, "vault_addr", "https://vault.example.internal")
    monkeypatch.setattr(settings, "vault_token", "token")
    monkeypatch.setattr(settings, "vault_transit_mount", "transit")
    monkeypatch.setattr(settings, "vault_transit_key", "datavision")
    versions = iter([3, 4])

    class Response:
        def __init__(self, payload=None): self.payload = payload or {}
        def raise_for_status(self): return None
        def json(self): return self.payload

    def fake_get(url, *, headers, timeout):
        return Response({"data": {"name": "datavision", "latest_version": next(versions), "min_decryption_version": 1, "min_encryption_version": 0}})

    def fake_post(url, *, headers, json, timeout):
        assert url.endswith("/v1/transit/keys/datavision/rotate")
        return Response()

    monkeypatch.setattr(secret_crypto.httpx, "get", fake_get)
    monkeypatch.setattr(secret_crypto.httpx, "post", fake_post)
    result = secret_crypto.rotate_kms_key(actor_user_id="user-1", organization_id="org-1")
    assert result["previous_version"] == 3
    assert result["new_version"] == 4
    assert result["rotated"] is True


def test_v259_helm_contains_ha_controls_migration_and_backup_jobs():
    root = Path(__file__).resolve().parents[2]
    values = (root / "deploy/helm/datavision/values.yaml").read_text(encoding="utf-8")
    api = (root / "deploy/helm/datavision/templates/api.yaml").read_text(encoding="utf-8")
    hpa = (root / "deploy/helm/datavision/templates/hpa.yaml").read_text(encoding="utf-8")
    pdb = (root / "deploy/helm/datavision/templates/pdb.yaml").read_text(encoding="utf-8")
    migration = (root / "deploy/helm/datavision/templates/migration-job.yaml").read_text(encoding="utf-8")
    backup = (root / "deploy/helm/datavision/templates/backup-cronjob.yaml").read_text(encoding="utf-8")
    assert "autoscaling:" in values and "PodDisruptionBudget" in pdb
    assert "HorizontalPodAutoscaler" in hpa and "autoscaling/v2" in hpa
    assert "/health/startup" in api and "maxUnavailable: 0" in api
    assert "pre-install,pre-upgrade" in migration and "app.ops.migrate" in migration
    assert "kind: CronJob" in backup and "app.ops.backup" in backup and "concurrencyPolicy: Forbid" in backup


def test_v259_operational_cli_and_runbooks_are_shipped():
    root = Path(__file__).resolve().parents[2]
    assert (root / "backend/app/ops/migrate.py").is_file()
    assert (root / "backend/app/ops/backup.py").is_file()
    runbook = (root / "docs/RUNBOOK_DISASTER_RECOVERY.md").read_text(encoding="utf-8")
    assert "RTO" in runbook and "RPO" in runbook and "app.ops.backup restore" in runbook and "--confirm" in runbook
