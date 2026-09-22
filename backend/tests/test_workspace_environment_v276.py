from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.workspace_environment import (
    get_workspace_environment,
    merge_requirements,
    sync_workspace_environment,
    update_workspace_environment,
    verify_workspace_environment,
)


def _use_isolated_store(tmp_path: Path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def test_workspace_environment_manifest_is_deterministic(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.services.workspace_environment.sandbox_packages",
        lambda: {
            "python": {"pandas": "2.3.2", "numpy": "2.3.2"},
            "r": {"dplyr": "1.1.4"},
            "install_policy": "image-managed",
            "dynamic_install": False,
        },
    )
    update_workspace_environment(
        python_requirements=["pandas>=2", "numpy"],
        r_requirements=["dplyr"],
    )
    synced = sync_workspace_environment()
    assert synced["status"] == "ready"
    assert synced["python_lock"] == {"pandas": "2.3.2", "numpy": "2.3.2"}
    assert synced["r_lock"] == {"dplyr": "1.1.4"}
    encoded = json.dumps(synced["manifest"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(encoded.encode()).hexdigest() == synced["fingerprint_sha256"]
    assert synced["policy"]["dynamic_install"] is False
    assert synced["policy"]["isolation"] == "workspace-sandbox"


def test_workspace_environment_detects_inventory_drift(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    inventory = {
        "python": {"pandas": "2.3.2"},
        "r": {},
        "install_policy": "image-managed",
        "dynamic_install": False,
    }
    monkeypatch.setattr("app.services.workspace_environment.sandbox_packages", lambda: inventory)
    update_workspace_environment(python_requirements=["pandas"])
    synced = sync_workspace_environment()
    assert synced["reproducible"] is True
    inventory["python"] = {"pandas": "2.4.0"}
    verified = verify_workspace_environment()
    assert verified["verified"] is False
    assert verified["lock_drift"][0]["package"] == "pandas"
    assert verified["lock_drift"][0]["expected"] == "2.3.2"
    assert verified["lock_drift"][0]["actual"] == "2.4.0"


def test_workspace_environment_missing_package_is_not_reproducible(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.services.workspace_environment.sandbox_packages",
        lambda: {"python": {}, "r": {}, "install_policy": "image-managed", "dynamic_install": False},
    )
    update_workspace_environment(python_requirements=["polars==1.0.0"])
    synced = sync_workspace_environment()
    assert synced["status"] == "missing_packages"
    assert synced["missing_python"] == ["polars==1.0.0"]
    assert synced["reproducible"] is False


def test_notebook_overlay_replaces_same_workspace_package_constraint():
    assert merge_requirements(
        ["pandas>=2", "numpy==2.3.2"],
        ["pandas==2.3.2", "scipy"],
    ) == ["pandas==2.3.2", "numpy==2.3.2", "scipy"]


def test_notebook_inherits_workspace_manifest_and_builds_effective_lock(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    import app.services.notebook_service as notebook_service
    inventory = {
        "python": {"pandas": "2.3.2", "scipy": "1.16.1"},
        "r": {"dplyr": "1.1.4", "ggplot2": "3.5.2"},
        "install_policy": "image-managed",
        "dynamic_install": False,
    }
    monkeypatch.setattr("app.services.workspace_environment.sandbox_packages", lambda: inventory)
    monkeypatch.setattr(notebook_service, "sandbox_packages", lambda: inventory)
    update_workspace_environment(python_requirements=["pandas>=2"], r_requirements=["dplyr"])
    workspace = sync_workspace_environment()
    notebook = notebook_service.create_notebook(name="Inherited environment", dataset_id=None)
    notebook_service.update_notebook_environment(
        notebook["id"], python_requirements=["scipy"], r_requirements=["ggplot2"]
    )
    synced = notebook_service.sync_notebook_environment(notebook["id"])
    assert synced["effective_python_requirements"] == ["pandas>=2", "scipy"]
    assert synced["effective_r_requirements"] == ["dplyr", "ggplot2"]
    assert synced["python_lock"] == {"pandas": "2.3.2", "scipy": "1.16.1"}
    assert synced["r_lock"] == {"dplyr": "1.1.4", "ggplot2": "3.5.2"}
    assert synced["workspace_environment"]["fingerprint_sha256"] == workspace["fingerprint_sha256"]
    assert synced["reproducible"] is True
    assert len(synced["fingerprint_sha256"]) == 64


def test_workspace_environment_api_uses_static_route(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/notebooks/workspace-environment")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope_type"] == "local"
    assert payload["policy"]["network_install"] is False
    assert len(payload["fingerprint_sha256"]) == 64
