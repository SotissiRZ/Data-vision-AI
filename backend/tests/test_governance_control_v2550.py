from __future__ import annotations

from io import BytesIO
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _boot(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services import metadata_store
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'gov255.db'}")
    metadata_store._ENGINES.clear(); metadata_store._SELECTED_BACKENDS.clear()
    res = client.post('/api/v1/auth/bootstrap', json={
        'email':'owner255@datavision.local','password':'EnterprisePass123!',
        'display_name':'Owner 255','organization_name':'Governance 255'
    })
    assert res.status_code == 200, res.text
    body=res.json(); headers={'Authorization':f"Bearer {body['access_token']}"}
    return body, headers


def _dataset(ws, headers):
    csv=b"region,revenue,cost\nNorth,100,40\nSouth,120,50\nNorth,140,60\n"
    res=client.post('/api/v1/datasets', headers={**headers,'X-Workspace-ID':ws}, files={'file':('gov.csv',BytesIO(csv),'text/csv')})
    assert res.status_code == 200, res.text
    ds=res.json()['dataset']['id']
    # upload in governed mode may already bind; binding is idempotent
    bind=client.post(f'/api/v1/workspaces/{ws}/datasets',headers=headers,json={'dataset_id':ds})
    assert bind.status_code == 200, bind.text
    return ds


def test_v255_control_plane_aggregates_existing_governance_engines(tmp_path, monkeypatch):
    boot,headers=_boot(tmp_path,monkeypatch); ws=boot['workspace_id']; ds=_dataset(ws,headers)
    policy=client.post(f'/api/v1/workspaces/{ws}/policies',headers=headers,json={
        'dataset_id':ds,'name':'Viewer North','allowed_columns':['region','revenue'],
        'row_filters':[{'column':'region','operator':'eq','value':'North'}],'applies_to_role':'viewer'
    })
    assert policy.status_code == 200, policy.text
    out=client.get(f'/api/v1/workspaces/{ws}/governance/control-plane?dataset_id={ds}',headers=headers)
    assert out.status_code == 200, out.text
    body=out.json()
    assert body['workspace']['id']==ws
    assert body['dataset']['dataset_id']==ds
    assert len(body['audit_digest_sha256'])==64
    ids={c['id'] for c in body['controls']}
    assert {'identity_rbac','access_policies','audit_trail','lineage','ai_governance','publication_gate','trust'}.issubset(ids)
    viewer=next(r for r in body['dataset']['role_matrix'] if r['role']=='viewer')
    assert viewer['allowed_column_count']==2 and viewer['row_filter_count']==1 and viewer['restricted'] is True
    assert body['ai']['settings']['external_data_policy']['include_row_data'] is False


def test_v255_governance_snapshot_is_hashed_persistent_and_audited(tmp_path, monkeypatch):
    boot,headers=_boot(tmp_path,monkeypatch); ws=boot['workspace_id']; ds=_dataset(ws,headers)
    snap=client.post(f'/api/v1/workspaces/{ws}/governance/snapshots',headers=headers,json={'dataset_id':ds})
    assert snap.status_code == 200, snap.text
    item=snap.json()['snapshot']
    assert len(item['sha256'])==64 and item['payload']['dataset']['dataset_id']==ds
    listed=client.get(f'/api/v1/workspaces/{ws}/governance/snapshots',headers=headers)
    assert listed.status_code == 200
    assert listed.json()['snapshots'][0]['sha256']==item['sha256']
    audit=client.get(f'/api/v1/audit?workspace_id={ws}',headers=headers).json()['events']
    assert any(e['event_type']=='governance.snapshot.capture' for e in audit)


def test_v255_control_plane_fails_closed_for_unbound_dataset(tmp_path, monkeypatch):
    boot,headers=_boot(tmp_path,monkeypatch); ws=boot['workspace_id']
    out=client.get(f'/api/v1/workspaces/{ws}/governance/control-plane?dataset_id=not-bound',headers=headers)
    assert out.status_code in {403,404}
