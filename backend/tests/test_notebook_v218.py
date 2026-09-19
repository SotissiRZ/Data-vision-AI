import io
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

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
                "notebook.csv",
                io.BytesIO(frame.to_csv(index=False).encode("utf-8")),
                "text/csv",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["dataset"]["id"]


def test_notebook_create_and_sql_execution(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()

    created = client.post(
        "/api/v1/notebooks",
        json={
            "name": "Notebook test",
            "dataset_id": dataset_id,
        },
    )
    assert created.status_code == 200, created.text
    notebook = created.json()
    assert notebook["dataset_id"] == dataset_id
    assert {cell["language"] for cell in notebook["cells"]} == {
        "markdown",
        "python",
        "sql",
        "r",
    }

    sql_cell = next(
        cell for cell in notebook["cells"]
        if cell["language"] == "sql"
    )
    updated = client.patch(
        f"/api/v1/notebooks/{notebook['id']}/cells/{sql_cell['id']}",
        json={
            "source": (
                "SELECT region, SUM(sales) AS total_sales "
                "FROM dataset GROUP BY region ORDER BY region"
            )
        },
    )
    assert updated.status_code == 200, updated.text

    run = client.post(
        f"/api/v1/notebooks/{notebook['id']}/cells/{sql_cell['id']}/run"
    )
    assert run.status_code == 200, run.text
    payload = run.json()
    assert payload["status"] == "succeeded"
    assert payload["result"]["type"] == "dataframe"
    assert payload["result"]["columns"] == ["region", "total_sales"]
    assert payload["provenance"]["dataset_id"] == dataset_id
    assert payload["provenance"]["execution_boundary"] == "read-only SQL engine"


def test_python_cell_uses_sandbox_contract(tmp_path, monkeypatch):
    import app.services.notebook_service as service

    _use_sqlite_metadata(tmp_path, monkeypatch)
    dataset_id = _upload_dataset()

    created = client.post(
        "/api/v1/notebooks",
        json={"name": "Python sandbox", "dataset_id": dataset_id},
    )
    assert created.status_code == 200
    notebook = created.json()
    python_cell = next(
        cell for cell in notebook["cells"]
        if cell["language"] == "python"
    )

    called = {}

    def fake_execute_sandboxed(*, language, code, dataframe):
        called["language"] = language
        called["code"] = code
        called["rows"] = len(dataframe)
        return {
            "status": "succeeded",
            "engine": "python",
            "stdout": "sandbox ok",
            "stderr": "",
            "result": {
                "type": "dataframe",
                "columns": ["sales"],
                "rows": [{"sales": 10.0}],
                "shape": [1, 1],
                "truncated": False,
            },
            "artifacts": [],
            "elapsed_ms": 12.5,
            "error_type": None,
        }

    monkeypatch.setattr(service, "execute_sandboxed", fake_execute_sandboxed)

    run = client.post(
        f"/api/v1/notebooks/{notebook['id']}/cells/{python_cell['id']}/run"
    )
    assert run.status_code == 200, run.text
    payload = run.json()
    assert payload["status"] == "succeeded"
    assert called["language"] == "python"
    assert called["rows"] == 3
    assert payload["provenance"]["execution_boundary"] == "isolated sandbox service"


def test_notebook_assistant_execution_requires_confirmation():
    from app.assistant.models import AssistantAction, AssistantContext
    from app.assistant.policy import evaluate_action_policy

    check = evaluate_action_policy(
        AssistantAction(
            id="a1",
            tool="execute_notebook_cell",
            label="Exécuter cellule",
            args={"notebook_id": "n1", "cell_id": "c1"},
            risk="reversible",
        ),
        AssistantContext(),
    )
    assert check.decision == "confirmation_required"


def test_sandbox_compose_security_contract():
    compose = (
        Path(__file__).resolve().parents[2]
        / "docker-compose.yml"
    ).read_text()

    assert "sandbox:" in compose
    assert "read_only: true" in compose
    assert "cap_drop:" in compose
    assert "- ALL" in compose
    assert "no-new-privileges:true" in compose
    assert "internal: true" in compose
    assert '"8090:8090"' not in compose
