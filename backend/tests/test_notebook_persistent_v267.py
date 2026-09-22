import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def _use_sqlite_metadata(tmp_path, monkeypatch):
    from app.core.config import get_settings
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _upload_dataset():
    frame = pd.DataFrame({"sales": [10.0, 20.0], "region": ["Nord", "Sud"]})
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("persistent.csv", io.BytesIO(frame.to_csv(index=False).encode()), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["dataset"]["id"]


def _create_notebook(dataset_id):
    response = client.post(
        "/api/v1/notebooks",
        json={"name": "Persistent runtime", "dataset_id": dataset_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_python_kernel_worker_preserves_namespace(tmp_path):
    dataset = tmp_path / "dataset.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(dataset, index=False)
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    out1.mkdir(); out2.mkdir()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "sandbox")
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "app.kernel_worker"],
        cwd=str(ROOT / "sandbox"),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps({
        "action": "execute",
        "code": "answer = 41",
        "dataset_path": str(dataset),
        "output_dir": str(out1),
    }) + "\n")
    process.stdin.flush()
    first = json.loads(process.stdout.readline())
    assert first["status"] == "succeeded"

    process.stdin.write(json.dumps({
        "action": "execute",
        "code": "answer + 1",
        "dataset_path": str(dataset),
        "output_dir": str(out2),
    }) + "\n")
    process.stdin.flush()
    second = json.loads(process.stdout.readline())
    assert second["status"] == "succeeded"
    assert second["result"]["value"] == 42
    assert second["execution_count"] == 2

    process.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
    process.stdin.flush()
    process.wait(timeout=5)


def test_notebook_uses_same_persistent_session(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()
    notebook = _create_notebook(dataset_id)
    py = next(c for c in notebook["cells"] if c["language"] == "python")
    second = client.post(
        f"/api/v1/notebooks/{notebook['id']}/cells",
        json={"language": "python", "source": "x + 1"},
    ).json()
    py2 = [c for c in second["cells"] if c["language"] == "python"][-1]

    seen = []
    state = {}
    def fake_execute(*, session_id, language, code, dataframe):
        seen.append(session_id)
        if "x =" in code:
            state[session_id] = 41
            value = None
        elif "x + 1" in code:
            value = state[session_id] + 1
        else:
            value = None
        return {
            "status": "succeeded", "engine": "python-persistent",
            "stdout": "", "stderr": "", "result": {"type": "int", "value": value},
            "artifacts": [], "elapsed_ms": 1.0, "error_type": None,
            "kernel_created": len(seen) == 1,
            "kernel": {"session_id": session_id, "generation": "g1", "execution_count": len(seen), "persistent": True},
        }

    monkeypatch.setattr(service, "execute_sandboxed_session", fake_execute)
    client.patch(
        f"/api/v1/notebooks/{notebook['id']}/cells/{py['id']}",
        json={"source": "x = 41"},
    )
    r1 = client.post(f"/api/v1/notebooks/{notebook['id']}/cells/{py['id']}/run")
    r2 = client.post(f"/api/v1/notebooks/{notebook['id']}/cells/{py2['id']}/run")
    assert r1.status_code == r2.status_code == 200
    assert r2.json()["result"]["value"] == 42
    assert seen[0] == seen[1]
    assert r2.json()["provenance"]["execution_boundary"] == "isolated persistent sandbox kernel"


def test_notebook_environment_lock_and_missing_packages(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    notebook = _create_notebook(_upload_dataset())
    monkeypatch.setattr(service, "sandbox_packages", lambda: {
        "python": {"pandas": "2.3.2", "numpy": "2.3.2"},
        "r": {"dplyr": "1.1.4"},
        "install_policy": "image-managed",
        "dynamic_install": False,
    })

    updated = client.put(
        f"/api/v1/notebooks/{notebook['id']}/environment",
        json={
            "python_requirements": ["pandas>=2.3", "missing-pkg"],
            "r_requirements": ["dplyr"],
        },
    )
    assert updated.status_code == 200, updated.text
    synced = client.post(f"/api/v1/notebooks/{notebook['id']}/environment/sync")
    assert synced.status_code == 200, synced.text
    payload = synced.json()
    assert payload["status"] == "missing_packages"
    assert payload["python_lock"]["pandas"] == "2.3.2"
    assert payload["r_lock"]["dplyr"] == "1.1.4"
    assert payload["missing_python"] == ["missing-pkg"]
    assert payload["dynamic_install"] is False


def test_kernel_restart_is_explicit_and_auditable(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    notebook = _create_notebook(_upload_dataset())
    monkeypatch.setattr(service, "restart_kernel_session", lambda *, session_id, language: {
        "session_id": session_id,
        "language": language,
        "generation": "restart-1",
        "execution_count": 0,
        "persistent": True,
        "created": True,
    })
    response = client.post(f"/api/v1/notebooks/{notebook['id']}/kernels/python/restart")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state_status"] == "reset"
    assert payload["generation"] == "restart-1"
