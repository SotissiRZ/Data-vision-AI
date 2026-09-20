import base64
import io
import re

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services.storage import get_meta, load_dataframe, save_dataframe_version

client = TestClient(app)


def _use_sqlite_metadata(tmp_path, monkeypatch):
    from app.core.config import get_settings
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(
        settings,
        "database_url",
        f"sqlite:///{tmp_path / 'metadata.db'}",
    )
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _upload_dataset():
    frame = pd.DataFrame(
        {
            "region": ["Nord", "Sud", "Nord"],
            "sales": [10.0, 20.0, 30.0],
            "profit": [2.0, 4.0, 9.0],
        }
    )
    response = client.post(
        "/api/v1/datasets",
        files={
            "file": (
                "workspace.csv",
                io.BytesIO(frame.to_csv(index=False).encode("utf-8")),
                "text/csv",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["dataset"]["id"]


def _create_notebook(dataset_id: str):
    response = client.post(
        "/api/v1/notebooks",
        json={"name": "Workspace v2.43", "dataset_id": dataset_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_notebooks_follow_dataset_root_and_can_rebind_version(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    v1 = _upload_dataset()
    notebook = _create_notebook(v1)

    v2_meta = save_dataframe_version(
        v1,
        load_dataframe(v1).assign(margin=lambda df: df["profit"] / df["sales"]),
        {"type": "derive", "label": "Ajout marge"},
    )
    v2 = v2_meta["id"]

    listed = client.get(f"/api/v1/notebooks?dataset_id={v2}")
    assert listed.status_code == 200, listed.text
    assert notebook["id"] in {item["id"] for item in listed.json()["items"]}

    rebound = client.post(
        f"/api/v1/notebooks/{notebook['id']}/bind",
        json={"dataset_id": v2},
    )
    assert rebound.status_code == 200, rebound.text
    payload = rebound.json()
    assert payload["dataset_id"] == v2
    assert payload["dataset_version"] == "2"
    assert payload["dataset_binding"]["root_id"] == v1
    assert payload["dataset_binding"]["version"] == 2


def test_sql_run_has_immutable_dataset_provenance(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()
    notebook = _create_notebook(dataset_id)
    sql_cell = next(cell for cell in notebook["cells"] if cell["language"] == "sql")

    run = client.post(
        f"/api/v1/notebooks/{notebook['id']}/cells/{sql_cell['id']}/run"
    )
    assert run.status_code == 200, run.text
    provenance = run.json()["provenance"]
    assert provenance["dataset_root_id"] == dataset_id
    assert provenance["dataset_version"] == "1"
    assert provenance["dataset_rows"] == 3
    assert provenance["dataset_columns"] == 3
    assert provenance["dataset_lineage_ids"] == [dataset_id]
    assert re.fullmatch(r"[0-9a-f]{64}", provenance["dataset_fingerprint_sha256"])
    assert provenance["execution_boundary"] == "read-only SQL engine"


def test_run_all_executes_reproducible_notebook(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()
    notebook = _create_notebook(dataset_id)

    def fake_execute_sandboxed(*, language, code, dataframe):
        return {
            "status": "succeeded",
            "engine": language,
            "stdout": f"{language} ok",
            "stderr": "",
            "result": {"type": "int", "value": len(dataframe)},
            "artifacts": [],
            "elapsed_ms": 4.2,
            "error_type": None,
        }

    monkeypatch.setattr(service, "execute_sandboxed", fake_execute_sandboxed)

    response = client.post(
        f"/api/v1/notebooks/{notebook['id']}/run",
        json={"continue_on_error": False},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["executed"] == 4
    assert payload["succeeded"] == 4
    assert payload["failed"] == 0
    assert payload["stopped_early"] is False
    assert {run["language"] for run in payload["runs"]} == {
        "markdown", "python", "sql", "r"
    }


def test_artifact_can_be_promoted_to_governed_dataset_version(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()
    notebook = _create_notebook(dataset_id)
    python_cell = next(cell for cell in notebook["cells"] if cell["language"] == "python")
    artifact_bytes = b"region,score\nNord,0.8\nSud,0.6\n"

    def fake_execute_sandboxed(*, language, code, dataframe):
        return {
            "status": "succeeded",
            "engine": language,
            "stdout": "saved",
            "stderr": "",
            "result": {"type": "str", "value": "scores.csv"},
            "artifacts": [
                {
                    "name": "scores.csv",
                    "size": len(artifact_bytes),
                    "extension": ".csv",
                    "content_base64": base64.b64encode(artifact_bytes).decode("ascii"),
                }
            ],
            "elapsed_ms": 5.0,
            "error_type": None,
        }

    monkeypatch.setattr(service, "execute_sandboxed", fake_execute_sandboxed)
    run = client.post(
        f"/api/v1/notebooks/{notebook['id']}/cells/{python_cell['id']}/run"
    )
    assert run.status_code == 200, run.text
    run_payload = run.json()
    assert run_payload["artifacts"][0]["name"] == "scores.csv"

    promoted = client.post(
        f"/api/v1/notebooks/{notebook['id']}/runs/{run_payload['id']}/artifacts/scores.csv/promote"
    )
    assert promoted.status_code == 200, promoted.text
    dataset = promoted.json()["dataset"]
    assert dataset["version"] == 2
    assert dataset["parent_id"] == dataset_id
    meta = get_meta(dataset["id"])
    assert meta["operation"]["type"] == "notebook_artifact"
    frame = load_dataframe(dataset["id"])
    assert frame.to_dict(orient="records") == [
        {"region": "Nord", "score": 0.8},
        {"region": "Sud", "score": 0.6},
    ]



def test_r_cell_uses_csv_sandbox_contract(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()
    notebook = _create_notebook(dataset_id)
    r_cell = next(cell for cell in notebook["cells"] if cell["language"] == "r")
    called = {}

    def fake_execute_sandboxed(*, language, code, dataframe):
        called["language"] = language
        called["rows"] = len(dataframe)
        return {
            "status": "succeeded",
            "engine": language,
            "stdout": "r ok",
            "stderr": "",
            "result": {"type": "integer", "value": 3},
            "artifacts": [],
            "elapsed_ms": 3.0,
            "error_type": None,
        }

    monkeypatch.setattr(service, "execute_sandboxed", fake_execute_sandboxed)
    response = client.post(
        f"/api/v1/notebooks/{notebook['id']}/cells/{r_cell['id']}/run"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    assert called == {"language": "r", "rows": 3}
    assert response.json()["provenance"]["execution_boundary"] == "isolated sandbox service"

def test_sql_workspace_remains_read_only(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/workspace/sql",
        json={"sql": "DELETE FROM dataset", "limit": 50},
    )
    assert response.status_code == 400
    assert "lecture seule" in response.json()["detail"]
