from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v265.db'}")
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
        "email": "reg265@datavision.local", "password": "RegPass265!", "display_name": "Reg 265", "organization_name": "Entreprise Reg 265"
    })
    assert res.status_code == 200, res.text
    body = res.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _drift_scan(ws: str, headers: dict[str, str]):
    response = client.post(f"/api/v1/workspaces/{ws}/compliance/scan", headers=headers, json={
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
    assert response.status_code == 200, response.text


def test_v265_catalog_posture_and_framework_mapping(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch); ws = boot["workspace_id"]
    _drift_scan(ws, headers)
    catalog = client.get(f"/api/v1/workspaces/{ws}/regulatory/catalog", headers=headers)
    assert catalog.status_code == 200, catalog.text
    body = catalog.json()
    assert body["catalog_version"] == "2026.09-v1"
    assert body["certification_claim"] is False
    assert {x["id"] for x in body["frameworks"]} >= {"nist-csf-2.0", "iso27001-2022", "soc2-security"}
    posture = client.get(f"/api/v1/workspaces/{ws}/regulatory/posture?framework_id=nist-csf-2.0", headers=headers)
    assert posture.status_code == 200, posture.text
    p = posture.json()
    assert p["summary"]["fail"] == 1 and p["summary"]["compliant_percent"] < 100
    assert next(x for x in p["controls"] if x["id"] == "DV-ADM-001")["status"] == "fail"


def test_v265_exception_is_governed_and_never_counts_as_strict_pass(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch); ws = boot["workspace_id"]
    _drift_scan(ws, headers)
    created = client.post(f"/api/v1/workspaces/{ws}/regulatory/exceptions", headers=headers, json={
        "control_id": "DV-ADM-001",
        "reason": "Migration de l'admission controller en cours avec surveillance compensatoire.",
        "compensating_controls": ["Digests immuables", "Scan CI bloquant"],
        "owner": "Platform Security",
        "expires_at": "2027-01-15T12:00:00+00:00",
    })
    assert created.status_code == 200, created.text
    exception = created.json(); assert exception["status"] == "pending" and exception["active"] is False
    approved = client.post(f"/api/v1/workspaces/{ws}/regulatory/exceptions/{exception['id']}/decision", headers=headers, json={"decision": "approved", "note": "Exception temporaire approuvée."})
    assert approved.status_code == 200, approved.text
    assert approved.json()["active"] is True
    posture = client.get(f"/api/v1/workspaces/{ws}/regulatory/posture", headers=headers).json()
    control = next(x for x in posture["controls"] if x["id"] == "DV-ADM-001")
    assert control["status"] == "fail" and control["effective_status"] == "excepted"
    assert posture["summary"]["excepted"] == 1
    assert posture["summary"]["compliant_percent"] < posture["summary"]["managed_percent"]


def test_v265_posture_history_and_remediation_are_deterministic(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch); ws = boot["workspace_id"]
    _drift_scan(ws, headers)
    snap = client.post(f"/api/v1/workspaces/{ws}/regulatory/posture/snapshot", headers=headers)
    assert snap.status_code == 200, snap.text
    assert len(snap.json()["sha256"]) == 64
    history = client.get(f"/api/v1/workspaces/{ws}/regulatory/posture/history", headers=headers).json()["history"]
    assert history and history[0]["score"] < 100
    remediation = client.get(f"/api/v1/workspaces/{ws}/regulatory/remediation", headers=headers).json()
    action = next(x for x in remediation["actions"] if x["control_id"] == "DV-ADM-001")
    assert action["priority"] == "high" and action["automation_mode"] == "proposal_only" and action["requires_human_approval"] is True


def test_v265_regulatory_evidence_pack_is_downloadable_and_verifiable(tmp_path, monkeypatch):
    boot, headers = _boot(tmp_path, monkeypatch); ws = boot["workspace_id"]
    _drift_scan(ws, headers)
    pack = client.post(f"/api/v1/workspaces/{ws}/regulatory/evidence-pack?framework_id=iso27001-2022", headers=headers)
    assert pack.status_code == 200, pack.text
    item = pack.json(); assert item["format"] == "datavision-regulatory-evidence-v2" and len(item["sha256"]) == 64
    download = client.get(f"/api/v1/workspaces/{ws}/regulatory/evidence-packs/{item['id']}/download", headers=headers)
    assert download.status_code == 200 and download.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "catalog.json", "posture.json", "history.json", "exceptions.json", "remediation.json", "controls.csv"} <= names
        assert b'"certification_claim": false' in archive.read("manifest.json")
    assert Path(tmp_path / "regulatory_evidence").exists()


def test_v265_assets_ui_and_migration_are_shipped():
    root = Path(__file__).resolve().parents[2]
    migration = (root / "backend/app/services/schema_migrations.py").read_text(encoding="utf-8")
    service = (root / "backend/app/services/regulatory_compliance.py").read_text(encoding="utf-8")
    routes = (root / "backend/app/api/routes/enterprise.py").read_text(encoding="utf-8")
    ui = (root / "frontend/components/RegulatoryCompliancePanel.tsx").read_text(encoding="utf-8")
    assert 'version="2.65.0-001"' in migration and "compliance_exceptions" in migration and "regulatory_posture_snapshots" in migration
    assert "certification_claim" in service and "automation_mode" in service and "datavision-regulatory-evidence-v2" in service
    assert "/regulatory/posture" in routes and "/regulatory/exceptions" in routes and "/regulatory/evidence-pack" in routes
    assert "Conformité stricte" in ui and "Exceptions gouvernées" in ui and "Télécharger" in ui
