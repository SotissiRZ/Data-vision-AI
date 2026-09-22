from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _use_store(tmp_path: Path, monkeypatch):
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v279.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "backup_object_store_auto_upload", False)
    monkeypatch.setattr(settings, "backup_replication_auto_enabled", False)
    monkeypatch.setattr(settings, "backup_retention_count", 20)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _load_signoff_module():
    path = ROOT / "scripts/production_signoff.py"
    spec = importlib.util.spec_from_file_location("production_signoff_v279", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_backend_security_headers_and_https_hsts():
    response = client.get("/health", headers={"x-forwarded-proto": "https"})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in response.headers["permissions-policy"]
    assert response.headers["strict-transport-security"].startswith("max-age=31536000")


def test_frontend_security_headers_are_declared():
    text = (ROOT / "frontend/next.config.mjs").read_text(encoding="utf-8")
    for needle in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy", "Strict-Transport-Security"):
        assert needle in text


def test_migrations_are_release_ordered_and_idempotent(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services.metadata_store import get_engine, init_metadata_store
    from app.services.schema_migrations import apply_pending_migrations, migration_status, ordered_migrations

    versions = [m.version for m in ordered_migrations()]
    assert versions == sorted(versions, key=lambda value: tuple(int(x) for x in value.replace("-", ".").split(".")))
    assert versions.index("2.68.0-001") < versions.index("2.76.0-001")
    assert "2.79.0-001" in versions
    assert versions[-1] == "2.80.0-001"
    init_metadata_store()
    status = migration_status()
    assert status["ready"] is True
    assert status["current"] == "2.80.0-001"
    with get_engine().begin() as conn:
        assert apply_pending_migrations(conn) == []


def test_backup_manifest_and_restore_drill_roundtrip(tmp_path, monkeypatch):
    _use_store(tmp_path, monkeypatch)
    from app.services.metadata_store import init_metadata_store
    from app.services.backup_service import create_backup, inspect_backup, run_restore_drill

    init_metadata_store()
    payload = tmp_path / "datasets" / "rc" / "evidence.txt"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text("release-candidate-evidence", encoding="utf-8")
    backup = create_backup(label="v279-rc")
    inspected = inspect_backup(Path(backup["archive"]))
    assert inspected["manifest"]["product_version"] == "2.80.0"
    assert inspected["manifest"]["schema_migration"] == "2.80.0-001"
    drill = run_restore_drill(Path(backup["archive"]))
    assert drill["status"] == "passed"
    assert drill["checks"]["safe_extract"] == "passed"
    assert drill["checks"]["hash_manifest"] == "passed"


def test_strict_signoff_rejects_waivers_and_tampered_attachments(tmp_path):
    module = _load_signoff_module()
    attachment = tmp_path / "load.json"
    attachment.write_text('{"ok":true}', encoding="utf-8")
    base = {
        "schema": module.EVIDENCE_SCHEMA,
        "product_version": module.project_version(),
        "kind": "load",
        "status": "waived",
        "recorded_at": module.utc_now(),
        "source": "target-runner",
        "actor": "release-manager",
        "details": "test",
        "attachments": [{"path": str(attachment), "sha256": module.sha256_file(attachment), "size": attachment.stat().st_size}],
    }
    base["evidence_sha256"] = module.sha256_json(base)
    ok, errors = module._verify_evidence_payload("load", base, allow_waivers=False)
    assert ok is False
    assert any("waiver" in error for error in errors)

    base["status"] = "pass"
    material = dict(base); material.pop("evidence_sha256", None)
    base["evidence_sha256"] = module.sha256_json(material)
    attachment.write_text('{"ok":false}', encoding="utf-8")
    ok, errors = module._verify_evidence_payload("load", base, allow_waivers=False)
    assert ok is False
    assert any("attachment" in error for error in errors)


def test_ci_runs_all_recent_acceptance_gates_and_rc_e2e():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for gate in (
        "quality_remediation_acceptance.py", "storytelling_acceptance.py", "model_gateway_acceptance.py",
        "i18n_accessibility_acceptance.py", "cloud_cdc_acceptance.py", "workspace_environment_acceptance.py",
        "performance_slo_acceptance.py", "cdc_gap_closure_acceptance.py", "release_candidate_acceptance.py",
    ):
        assert gate in ci
    assert "test:e2e:accessibility" in ci
    assert "test:e2e:release-candidate" in ci


def test_release_candidate_e2e_contract_exists():
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["test:e2e:release-candidate"] == "playwright test --grep @release-candidate"
    spec = (ROOT / "frontend/e2e/release-candidate.spec.ts").read_text(encoding="utf-8")
    assert "@release-candidate" in spec
    assert "x-request-id" in spec
    assert "Assistant DataVision AI" in spec


def test_external_signoff_boundary_is_still_explicit():
    acceptance = json.loads((ROOT / "compliance/PRODUCTION_ACCEPTANCE.json").read_text(encoding="utf-8"))
    assert acceptance["acceptance"] == "conditional"
    assert acceptance["target_signoff"] == "pending"
    assert "uat" in acceptance["required_target_evidence"]
    cdc = json.loads((ROOT / "compliance/CDC_COVERAGE_MATRIX.json").read_text(encoding="utf-8"))
    remaining = {item["section"]: item["status"] for item in cdc["requirements"] if item["status"] != "implemented"}
    assert remaining == {2: "partial", 71: "partial", 74: "partial", 75: "partial"}
