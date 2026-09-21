from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'v262.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "schema_auto_migrate", True)
    monkeypatch.setattr(settings, "backup_require_database_dump", False)
    monkeypatch.setattr(settings, "backup_replication_targets_json", "[]")
    monkeypatch.setattr(settings, "multi_cluster_sites_json", "[]")
    monkeypatch.setattr(settings, "multi_cluster_failover_enabled", False)
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    res = client.post("/api/v1/auth/bootstrap", json={
        "email":"ops262@datavision.local", "password":"OpsPass262!", "display_name":"Ops 262", "organization_name":"Entreprise Ops 262"
    })
    assert res.status_code == 200, res.text
    body=res.json(); return settings, body, {"Authorization":f"Bearer {body['access_token']}"}


def test_v262_traceparent_is_propagated_and_queryable(tmp_path, monkeypatch):
    _, boot, headers = _boot(tmp_path, monkeypatch)
    ws=boot["workspace_id"]
    trace_id="1"*32; parent="2"*16
    res=client.get(f"/api/v1/workspaces/{ws}/operational/overview", headers={**headers,"traceparent":f"00-{trace_id}-{parent}-01","x-request-id":"req-262"})
    assert res.status_code == 200, res.text
    assert res.headers["x-trace-id"] == trace_id
    assert res.headers["x-request-id"] == "req-262"
    assert res.headers["traceparent"].startswith(f"00-{trace_id}-")
    traced=client.get(f"/api/v1/workspaces/{ws}/operational/traces/{trace_id}", headers=headers)
    assert traced.status_code == 200, traced.text
    assert any(e.get("metadata",{}).get("trace_id") == trace_id for e in traced.json()["events"])


def test_v262_cross_region_replication_is_verified(tmp_path, monkeypatch):
    settings, _, _ = _boot(tmp_path, monkeypatch)
    from app.services import backup_service
    monkeypatch.setenv("Z_ACCESS","A"); monkeypatch.setenv("Z_SECRET","B")
    monkeypatch.setattr(settings, "backup_replication_targets_json", json.dumps([{
        "name":"eu-west", "endpoint":"https://s3.example.test", "bucket":"dv", "prefix":"prod", "region":"eu-west-1",
        "access_key_env":"Z_ACCESS", "secret_key_env":"Z_SECRET"
    }]))
    archive=tmp_path/"backups"/"verified.tar.gz"; archive.parent.mkdir(parents=True,exist_ok=True); archive.write_bytes(b"verified-backup")
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    class Response:
        status_code=200; text=""; content=b""
        def __init__(self, method): self.headers={"etag":"\"etag\""} if method=="PUT" else {"x-amz-meta-sha256":digest,"content-length":str(archive.stat().st_size)}
    import httpx
    monkeypatch.setattr(httpx,"request",lambda method,*args,**kwargs: Response(method))
    out=backup_service.replicate_backup_to_targets(archive, backup_id="b262")
    assert out["status"] == "completed"
    assert out["results"][0]["verification"]["status"] == "verified"
    rows=backup_service.list_backup_replications(backup_id="b262")
    assert rows[0]["verification_status"] == "verified" and rows[0]["verification"]["sha256"] == digest


def test_v262_failover_requires_two_phase_confirmation(tmp_path, monkeypatch):
    settings, boot, headers = _boot(tmp_path, monkeypatch)
    ws=boot["workspace_id"]
    monkeypatch.setattr(settings,"multi_cluster_sites_json",json.dumps([
        {"id":"cluster-a","region":"eu-west-1","role":"primary","backup_target":"zone-a"},
        {"id":"cluster-b","region":"eu-central-1","role":"standby","backup_target":"zone-b"},
    ]))
    monkeypatch.setattr(settings,"multi_cluster_failover_enabled",True)
    monkeypatch.setattr(settings,"multi_cluster_require_verified_backup",False)
    monkeypatch.setattr(settings,"multi_cluster_failover_executor","control_plane_only")
    plan=client.post(f"/api/v1/workspaces/{ws}/operational/failovers/plan",headers=headers,json={"target_cluster_id":"cluster-b","reason":"regional maintenance"})
    assert plan.status_code == 200, plan.text
    item=plan.json()["plan"]
    denied=client.post(f"/api/v1/workspaces/{ws}/operational/failovers/{item['id']}/confirm",headers=headers,json={"confirmation_token":"x"*24})
    assert denied.status_code == 403
    ok=client.post(f"/api/v1/workspaces/{ws}/operational/failovers/{item['id']}/confirm",headers=headers,json={"confirmation_token":item["confirmation_token"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["failover"]["traffic_switched"] is False
    topology=client.get(f"/api/v1/workspaces/{ws}/operational/clusters",headers=headers).json()
    assert topology["active_cluster_id"] == "cluster-b"


def test_v262_failover_can_require_fresh_verified_replication(tmp_path, monkeypatch):
    settings, boot, _ = _boot(tmp_path, monkeypatch)
    from app.services import metadata_store, multi_cluster
    ws=boot["workspace_id"]
    monkeypatch.setattr(settings,"multi_cluster_sites_json",json.dumps([
        {"id":"a","role":"primary","backup_target":"zone-a"},{"id":"b","role":"standby","backup_target":"zone-b"}
    ])); monkeypatch.setattr(settings,"multi_cluster_failover_enabled",True); monkeypatch.setattr(settings,"multi_cluster_require_verified_backup",True)
    try:
        multi_cluster.create_failover_plan(boot["user"]["id"],ws,target_cluster_id="b",reason="test")
        assert False, "verified backup should be required"
    except RuntimeError:
        pass
    metadata_store.execute("INSERT INTO backup_replications(id,backup_id,target_name,status,object_uri,object_key,sha256,error,started_at,completed_at,verification_status,verified_at,verification_json) VALUES(:id,:b,:t,'completed','s3://x','x','abc',NULL,:at,:at,'verified',:at,'{}')", {"id":"r1","b":"backup1","t":"zone-b","at":datetime.now(timezone.utc).isoformat()})
    out=multi_cluster.create_failover_plan(boot["user"]["id"],ws,target_cluster_id="b",reason="test")
    assert out["preflight"]["verified_backup_fresh"] is True


def test_v262_helm_packages_alertmanager_and_trace_export():
    root=Path(__file__).resolve().parents[2]
    values=(root/"deploy/helm/datavision/values.yaml").read_text(encoding="utf-8")
    am=(root/"deploy/helm/datavision/templates/alertmanager-config.yaml").read_text(encoding="utf-8")
    otel=(root/"deploy/helm/datavision/templates/otel.yaml").read_text(encoding="utf-8")
    assert "alertmanagerConfig:" in values and "secretName:" in values
    assert "kind: AlertmanagerConfig" in am and "slackConfigs:" in am and "webhookConfigs:" in am and "emailConfigs:" in am
    assert "traces:" in otel and "otlphttp/trace-backend" in otel


def test_v262_executable_runbooks_and_migration_are_shipped():
    root=Path(__file__).resolve().parents[2]
    runbook=(root/"backend/app/ops/runbook.py").read_text(encoding="utf-8")
    migrations=(root/"backend/app/services/schema_migrations.py").read_text(encoding="utf-8")
    assert "failover-plan" in runbook and "failover-confirm" in runbook and "verify-replications" in runbook
    assert 'version="2.62.0-001"' in migrations and "cluster_failover_events" in migrations and "verification_status" in migrations
