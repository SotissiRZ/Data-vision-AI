from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'sre260.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "backup_require_database_dump", False)
    monkeypatch.setattr(settings, "backup_object_store_provider", "disabled")
    monkeypatch.setattr(settings, "sre_chaos_enabled", False)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    res = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "sre260@datavision.local",
            "password": "SrePass260!",
            "display_name": "SRE 260",
            "organization_name": "Entreprise SRE",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return settings, body, {"Authorization": f"Bearer {body['access_token']}"}


def test_v260_schema_and_restore_drill_verify_file_hashes(tmp_path, monkeypatch):
    settings, _, _ = _boot(tmp_path, monkeypatch)
    from app.services.backup_service import create_backup, inspect_backup, run_restore_drill
    from app.services.schema_migrations import migration_status

    sample = tmp_path / "uploads" / "sre.txt"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("restore-drill", encoding="utf-8")
    created = create_backup(label="sre")
    inspected = inspect_backup(Path(created["archive"]))
    assert inspected["manifest"]["format"] == "datavision-backup-v2"
    current_version = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    assert inspected["manifest"]["product_version"] == current_version
    assert inspected["manifest"]["files"][0]["sha256"]
    drill = run_restore_drill(Path(created["archive"]))
    assert drill["status"] == "passed"
    assert drill["checks"]["hash_manifest"] == "passed"
    assert "2.60.0-001" in migration_status()["applied"]


def test_v260_sre_status_exposes_error_budget_backup_drill_and_alerts(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    from app.services.backup_service import create_backup, run_restore_drill

    created = create_backup(label="sre")
    run_restore_drill(Path(created["archive"]))
    ws = boot["workspace_id"]
    response = client.get(f"/api/v1/workspaces/{ws}/operational/sre?hours=24", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error_budget"]["target_pct"] >= 99.0
    assert body["backup"]["status"] == "completed"
    assert body["restore_drill"]["status"] == "passed"
    assert body["object_store"]["provider"] == "disabled"
    assert body["autoscaling"]["queue_name"] == "datavision:jobs"


def test_v260_s3_signature_upload_uses_checksum_metadata(tmp_path, monkeypatch):
    settings, _, _ = _boot(tmp_path, monkeypatch)
    from app.services import backup_service

    monkeypatch.setattr(settings, "backup_object_store_provider", "s3_compatible")
    monkeypatch.setattr(settings, "backup_object_store_endpoint", "https://minio.example.test")
    monkeypatch.setattr(settings, "backup_object_store_bucket", "dv-backups")
    monkeypatch.setattr(settings, "backup_object_store_prefix", "prod")
    monkeypatch.setattr(settings, "backup_object_store_region", "us-east-1")
    monkeypatch.setattr(settings, "backup_object_store_access_key", "ACCESS")
    monkeypatch.setattr(settings, "backup_object_store_secret_key", "SECRET")
    monkeypatch.setattr(settings, "backup_object_store_verify_tls", True)

    archive = tmp_path / "backups" / "sample.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"backup-bytes")
    seen = {}

    class Response:
        status_code = 200
        text = ""
        content = b""
        headers = {"etag": '"abc123"'}

    def fake_request(method, url, *, content, headers, timeout, verify):
        seen.update(method=method, url=url, content=content, headers=headers, verify=verify)
        return Response()

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)
    result = backup_service.upload_backup_to_object_store(archive)
    assert result["uri"] == "s3://dv-backups/prod/sample.tar.gz"
    assert seen["method"] == "PUT"
    assert "AWS4-HMAC-SHA256" in seen["headers"]["authorization"]
    assert seen["headers"]["x-amz-meta-sha256"] == result["sha256"]


def test_v260_controlled_chaos_is_off_by_default_and_bounded(tmp_path, monkeypatch):
    settings, boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    denied = client.post(f"/api/v1/workspaces/{ws}/operational/chaos", headers=headers, json={"scenario": "queue_backlog", "intensity": 3})
    assert denied.status_code == 403, denied.text

    monkeypatch.setattr(settings, "sre_chaos_enabled", True)
    monkeypatch.setattr(settings, "sre_chaos_max_probe_jobs", 2)
    from app.services import sre_operations

    submitted = []
    monkeypatch.setattr(sre_operations, "submit_job", lambda **kw: submitted.append(kw) or {"id": f"probe-{len(submitted)}"})
    allowed = client.post(f"/api/v1/workspaces/{ws}/operational/chaos", headers=headers, json={"scenario": "queue_backlog", "intensity": 10})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["drill"]["count"] == 2
    assert len(submitted) == 2
    assert all(item["job_type"] == "sre_probe" and item["max_retries"] == 0 for item in submitted)


def test_v260_helm_adds_keda_restore_drill_and_object_store_configuration():
    root = Path(__file__).resolve().parents[2]
    values = (root / "deploy/helm/datavision/values.yaml").read_text(encoding="utf-8")
    keda = (root / "deploy/helm/datavision/templates/keda-worker.yaml").read_text(encoding="utf-8")
    backup = (root / "deploy/helm/datavision/templates/backup-cronjob.yaml").read_text(encoding="utf-8")
    config = (root / "deploy/helm/datavision/templates/configmap.yaml").read_text(encoding="utf-8")
    assert "mode: cpu # cpu | keda_redis" in values
    assert "kind: ScaledObject" in keda and "type: redis" in keda and "datavision:jobs" in values
    assert "restore-drill" in backup and "drill-latest" in backup
    assert "BACKUP_OBJECT_STORE_PROVIDER" in config and "SRE_AUTO_ALERTS_ENABLED" in config


def test_v260_frontend_exposes_sre_cockpit_and_actions():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    css = (root / "frontend/app/globals.css").read_text(encoding="utf-8")
    assert "Posture SRE" in page and "Budget d’erreur restant" in page
    assert "getSREStatus" in api and "/operational/sre" in api
    assert ".sre-operations-grid" in css
