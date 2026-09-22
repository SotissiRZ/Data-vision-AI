from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[2]


def _load_doctor():
    path = ROOT / "scripts/config_doctor.py"
    spec = importlib.util.spec_from_file_location("config_doctor_v280", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_version_and_rc_policy_are_frozen():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "2.81.6"
    policy = json.loads((ROOT / "policies/release_candidate.json").read_text(encoding="utf-8"))
    assert policy["product_version"] == "2.81.6"
    assert policy["stage"] == "release_candidate"
    assert policy["feature_freeze"] is True
    assert policy["external_signoff_status"] == "pending"


def test_latest_migration_is_rc_freeze_marker(tmp_path, monkeypatch):
    from app.services import metadata_store
    from app.services.schema_migrations import migration_status, ordered_migrations

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v280.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    metadata_store.init_metadata_store()
    assert ordered_migrations()[-1].version == "2.81.0-001"
    status = migration_status()
    assert status["current"] == "2.81.0-001"
    assert status["ready"] is True


def test_windows_entrypoints_use_version_file_and_no_stale_version_labels():
    for rel in ("install-windows.ps1", "preflight-windows.ps1", "rebuild-windows.ps1", "start-datavision.ps1", "upgrade-windows.ps1"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "VERSION" in text
        assert "v2.39.0" not in text
        assert '$expectedVersion = "2.54.0"' not in text


def test_upgrade_preserves_volumes_and_runs_backup_then_migration():
    text = (ROOT / "upgrade-windows.ps1").read_text(encoding="utf-8")
    assert "--profile ops run --rm backup" in text
    assert "--profile ops run --rm migrate" in text
    assert "health/ready" in text
    assert "down -v" not in text


def test_config_doctor_accepts_example_for_development_and_rejects_placeholders_in_production(tmp_path):
    doctor = _load_doctor()
    source = ROOT / ".env.example"
    env_path = tmp_path / ".env"
    env_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    dev = doctor.inspect(ROOT, env_path, "development")
    assert dev["status"] == "pass"
    assert not any("bootstrap" in error for error in dev["errors"])
    prod = doctor.inspect(ROOT, env_path, "production")
    assert prod["status"] == "fail"
    assert "production_secret_not_set:AUTH_SECRET" in prod["errors"]
    assert "production_secret_not_set:SECRET_KMS_KEY" in prod["errors"]
    assert "production_demo_account_must_be_disabled" in prod["errors"]


def test_release_workflow_runs_recent_gates_and_rc_e2e():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for gate in (
        "quality_remediation_acceptance.py", "storytelling_acceptance.py", "model_gateway_acceptance.py",
        "i18n_accessibility_acceptance.py", "cloud_cdc_acceptance.py", "workspace_environment_acceptance.py",
        "performance_slo_acceptance.py", "cdc_gap_closure_acceptance.py", "release_candidate_acceptance.py",
        "release_installation_acceptance.py",
    ):
        assert gate in text
    assert "test:e2e:accessibility" in text
    assert "test:e2e:release-candidate" in text


def test_reproducible_release_and_verifier_remain_mandatory():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    release = (ROOT / "scripts/release.py").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts/verify_release.py").read_text(encoding="utf-8")
    assert "python scripts/release.py --output dist" in workflow
    assert "python scripts/verify_release.py" in workflow
    assert "FIXED_ZIP_TIME" in release
    assert "_safe_member" in verifier
    assert "SHA256 invalide" in verifier


def test_external_uat_boundary_is_preserved():
    prod = json.loads((ROOT / "compliance/PRODUCTION_ACCEPTANCE.json").read_text(encoding="utf-8"))
    assert prod["acceptance"] == "conditional"
    assert prod["target_signoff"] == "pending"
    policy = json.loads((ROOT / "policies/release_candidate.json").read_text(encoding="utf-8"))
    assert set(policy["required_external_signoff"]) == {"target_infrastructure", "uat"}
