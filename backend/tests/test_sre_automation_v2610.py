from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'sre261.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "backup_require_database_dump", False)
    monkeypatch.setattr(settings, "backup_object_store_provider", "disabled")
    monkeypatch.setattr(settings, "backup_replication_targets_json", "[]")
    monkeypatch.setattr(settings, "backup_replication_auto_enabled", False)
    monkeypatch.setattr(settings, "sre_dr_enabled", False)
    monkeypatch.setattr(settings, "app_env", "test")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    res = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "sre261@datavision.local",
            "password": "SrePass261!",
            "display_name": "SRE 261",
            "organization_name": "Entreprise SRE 261",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return settings, body, {"Authorization": f"Bearer {body['access_token']}"}


def test_v261_migration_and_workspace_alert_routes(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    from app.services.schema_migrations import migration_status
    assert "2.61.0-001" in migration_status()["applied"]
    ws = boot["workspace_id"]
    saved = client.put(
        f"/api/v1/workspaces/{ws}/operational/sre/routes",
        headers=headers,
        json={"name": "Ops critique", "min_severity": "high", "event_type": "sre_critical", "codes": ["queue_unavailable"]},
    )
    assert saved.status_code == 200, saved.text
    route = saved.json()["route"]
    assert route["min_severity"] == "high"
    assert route["route"]["codes"] == ["queue_unavailable"]
    listed = client.get(f"/api/v1/workspaces/{ws}/operational/sre/routes", headers=headers)
    assert listed.status_code == 200 and len(listed.json()["routes"]) == 1
    deleted = client.delete(f"/api/v1/workspaces/{ws}/operational/sre/routes/{route['id']}", headers=headers)
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True


def test_v261_routing_filters_alerts_before_governed_actions(tmp_path, monkeypatch):
    _, boot, _ = _boot(tmp_path, monkeypatch)
    from app.services import governed_actions, sre_operations
    ws = boot["workspace_id"]
    actor = boot["user"]["id"]
    sre_operations.save_sre_alert_route(ws, name="Critique Redis", min_severity="critical", event_type="sre_critical", codes=["queue_unavailable"])
    monkeypatch.setattr(sre_operations, "capture_sre_snapshot", lambda workspace_id, hours=24: {
        "workspace_id": workspace_id,
        "status": "critical",
        "alerts": [
            {"code": "queue_unavailable", "severity": "critical", "title": "Redis down", "detail": "x"},
            {"code": "backup_stale", "severity": "high", "title": "Backup old", "detail": "y"},
        ],
        "error_budget": {},
    })
    seen = []
    monkeypatch.setattr(governed_actions, "dispatch_event", lambda *args, **kwargs: seen.append(kwargs) or {"runs": [{"id": "r1"}]})
    result = sre_operations.emit_sre_alerts(actor, ws)
    assert result["routed_alert_events"] == 1
    assert result["governed_action_runs"] == 1
    assert seen[0]["event_type"] == "sre_critical"
    assert seen[0]["payload"]["code"] == "queue_unavailable"


def test_v261_multi_target_backup_replication_isolated_and_audited(tmp_path, monkeypatch):
    settings, _, _ = _boot(tmp_path, monkeypatch)
    from app.services import backup_service
    monkeypatch.setenv("DV_A_ACCESS", "AKEY")
    monkeypatch.setenv("DV_A_SECRET", "ASECRET")
    monkeypatch.setenv("DV_B_ACCESS", "BKEY")
    monkeypatch.setenv("DV_B_SECRET", "BSECRET")
    targets = [
        {"name":"zone-a","endpoint":"https://a.example.test","bucket":"backups-a","prefix":"prod","access_key_env":"DV_A_ACCESS","secret_key_env":"DV_A_SECRET"},
        {"name":"zone-b","endpoint":"https://b.example.test","bucket":"backups-b","prefix":"prod","access_key_env":"DV_B_ACCESS","secret_key_env":"DV_B_SECRET"},
    ]
    monkeypatch.setattr(settings, "backup_replication_targets_json", json.dumps(targets))
    archive = tmp_path / "backups" / "replica.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"replica")

    class Response:
        status_code = 200
        text = ""
        content = b""
        headers = {"etag": '"etag"'}

    import httpx
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: Response())
    result = backup_service.replicate_backup_to_targets(archive, backup_id="backup-261")
    assert result["status"] == "completed"
    assert {item["target"] for item in result["results"]} == {"zone-a", "zone-b"}
    rows = backup_service.list_backup_replications(backup_id="backup-261")
    assert len(rows) == 2 and all(row["status"] == "completed" for row in rows)


def test_v261_prometheus_metrics_include_recording_rule_inputs(tmp_path, monkeypatch):
    _, boot, _ = _boot(tmp_path, monkeypatch)
    from app.services.entreprise_platform import prometheus_metrics
    text = prometheus_metrics(boot["workspace_id"], hours=1)
    assert "datavision_http_availability_ratio" in text
    assert "datavision_job_success_ratio" in text
    assert "datavision_queue_depth" in text
    assert "datavision_jobs_total" in text


def test_v261_dr_orchestration_is_gated_and_non_destructive(tmp_path, monkeypatch):
    settings, boot, headers = _boot(tmp_path, monkeypatch)
    ws = boot["workspace_id"]
    denied = client.post(f"/api/v1/workspaces/{ws}/operational/dr-drills", headers=headers, json={"mode":"continuity"})
    assert denied.status_code == 403
    monkeypatch.setattr(settings, "sre_dr_enabled", True)
    from app.services import backup_service, sre_operations
    archive = tmp_path / "backups" / "dr.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"x")
    monkeypatch.setattr(backup_service, "latest_backup_archive", lambda: archive)
    monkeypatch.setattr(backup_service, "run_restore_drill", lambda path: {"id":"restore-1","status":"passed","backup_id":"b1","checks":{}})
    monkeypatch.setattr(backup_service, "replication_targets_status", lambda: {"enabled":False,"configured_targets":0,"targets":[]})
    monkeypatch.setattr(backup_service, "list_backup_replications", lambda **kwargs: [])
    monkeypatch.setattr(sre_operations, "submit_job", lambda **kwargs: {"id":"probe-1"})
    allowed = client.post(f"/api/v1/workspaces/{ws}/operational/dr-drills", headers=headers, json={"mode":"continuity"})
    assert allowed.status_code == 200, allowed.text
    drill = allowed.json()["drill"]
    assert drill["status"] == "passed"
    assert drill["checks"]["dependency_loss"]["mode"] == "non_destructive_fault_model"
    assert drill["checks"]["recovery_probe_job_id"] == "probe-1"


def test_v261_helm_packages_prometheus_rules_and_grafana_dashboard():
    root = Path(__file__).resolve().parents[2]
    values = (root / "deploy/helm/datavision/values.yaml").read_text(encoding="utf-8")
    rules = (root / "deploy/helm/datavision/templates/prometheus-rules.yaml").read_text(encoding="utf-8")
    dashboard = (root / "deploy/helm/datavision/templates/grafana-dashboard.yaml").read_text(encoding="utf-8")
    configmap = (root / "deploy/helm/datavision/templates/configmap.yaml").read_text(encoding="utf-8")
    assert "prometheusRule:" in values and "grafanaDashboard:" in values
    assert "kind: PrometheusRule" in rules and "DataVisionApiAvailabilitySLOBreach" in rules
    assert "DataVision AI — SRE & SLO" in dashboard and "grafana_dashboard" in values
    assert "BACKUP_REPLICATION_TARGETS_JSON" in configmap and "SRE_DR_ENABLED" in configmap
