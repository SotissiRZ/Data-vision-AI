import io
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_profile_quality(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    csv = b"age,group,target\n20,A,0\n21,A,0\n, B,1\n40,B,1\n40,B,1\n"
    r = client.post("/api/v1/datasets", files={"file": ("sample.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200
    dataset_id = r.json()["dataset"]["id"]
    p = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    q = client.get(f"/api/v1/datasets/{dataset_id}/quality")
    assert p.status_code == 200
    assert p.json()["rows"] == 5
    assert q.status_code == 200
    assert q.json()["issues_count"] >= 1
