from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v264.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "admission_verify_images_enabled", True)
    monkeypatch.setattr(settings, "runtime_security_seccomp_runtime_default", True)
    monkeypatch.setattr(settings, "runtime_security_run_as_non_root", True)
    monkeypatch.setattr(settings, "runtime_security_read_only_root_filesystem", True)
    monkeypatch.setattr(settings, "runtime_security_drop_all_capabilities", True)
    monkeypatch.setattr(settings, "runtime_security_disallow_privilege_escalation", True)
    monkeypatch.setattr(settings, "runtime_detection_enabled", True)
    monkeypatch.setattr(settings, "continuous_compliance_enabled", True)
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    res = client.post("/api/v1/auth/bootstrap", json={
        "email": "sec264@datavision.local", "password": "SecPass264!", "display_name": "Sec 264", "organization_name": "Entreprise Sec 264"
    })
    assert res.status_code == 200, res.text
    body = res.json()
    return settings, body, {"Authorization": f"Bearer {body['access_token']}"}


def test_v264_continuous_compliance_scan_and_drift(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    clean = client.post(f"/api/v1/workspaces/{ws}/compliance/scan", headers=headers, json={"source": "test"})
    assert clean.status_code == 200, clean.text
    assert clean.json()["status"] == "pass" and clean.json()["drift_count"] == 0

    drift = client.post(f"/api/v1/workspaces/{ws}/compliance/scan", headers=headers, json={
        "source": "cluster-agent",
        "observed": {
            "admission_signature_verification": False,
            "runtime_default_seccomp": True,
            "run_as_non_root": True,
            "read_only_root_filesystem": True,
            "drop_all_capabilities": True,
            "allow_privilege_escalation": False,
            "runtime_detection_enabled": True,
            "continuous_compliance_enabled": True,
        },
    })
    assert drift.status_code == 200, drift.text
    assert drift.json()["status"] == "fail" and drift.json()["drift_count"] == 1
    status = client.get(f"/api/v1/workspaces/{ws}/compliance/status", headers=headers)
    assert status.status_code == 200 and status.json()["latest"]["source"] == "cluster-agent"


def test_v264_runtime_event_and_evidence_pack(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    event = client.post(f"/api/v1/workspaces/{ws}/runtime-security/events", headers=headers, json={
        "source": "falco", "severity": "high", "rule": "DataVision Shell Spawned In Application Container", "details": {"pod": "api-0"}
    })
    assert event.status_code == 200, event.text
    listed = client.get(f"/api/v1/workspaces/{ws}/runtime-security/events?min_severity=medium", headers=headers)
    assert listed.status_code == 200 and listed.json()["events"][0]["severity"] == "high"
    pack = client.post(f"/api/v1/workspaces/{ws}/compliance/evidence-pack", headers=headers)
    assert pack.status_code == 200, pack.text
    body = pack.json()
    assert body["format"] == "datavision-compliance-evidence-v1"
    assert len(body["sha256"]) == 64 and body["runtime_security_events"]
    assert Path(tmp_path / "compliance_evidence").exists()


def test_v264_migration_cli_and_assets_are_shipped():
    root = Path(__file__).resolve().parents[2]
    migrations = (root / "backend/app/services/schema_migrations.py").read_text(encoding="utf-8")
    cli = (root / "backend/app/ops/compliance.py").read_text(encoding="utf-8")
    admission = (root / "deploy/helm/datavision/templates/admission-policy.yaml").read_text(encoding="utf-8")
    falco = (root / "deploy/helm/datavision/templates/falco-rules.yaml").read_text(encoding="utf-8")
    cron = (root / "deploy/helm/datavision/templates/compliance-cronjob.yaml").read_text(encoding="utf-8")
    assert 'version="2.64.0-001"' in migrations and "continuous_compliance_runs" in migrations and "runtime_security_events" in migrations
    assert "scan" in cli and "evidence" in cli and "--all" in cli
    assert "verifyImages" in admission and "keyless" in admission and "validationFailureAction: Enforce" in admission
    assert "DataVision Shell Spawned" in falco and "Sensitive Path Write" in falco
    assert "concurrencyPolicy: Forbid" in cron and "app.ops.compliance" in cron


def test_v264_workloads_are_hardened_and_policy_as_code_enforces_it():
    root = Path(__file__).resolve().parents[2]
    policy = (root / "policies/kubernetes/datavision.rego").read_text(encoding="utf-8")
    for rel in ["api.yaml", "web.yaml", "worker.yaml", "sandbox.yaml"]:
        text = (root / "deploy/helm/datavision/templates" / rel).read_text(encoding="utf-8")
        assert "runAsNonRoot" in text and "allowPrivilegeEscalation" in text and "seccompProfile" in text
        assert 'drop:' in text and 'ALL' in text
    assert "RuntimeDefault" in policy and "allowPrivilegeEscalation" in policy and "drop ALL capabilities" in policy
