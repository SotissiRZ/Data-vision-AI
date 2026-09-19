from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from app.core.config import get_settings
from app.services.audit_service import record_event
from app.services.auth_service import has_permission
from app.services.data_workspace import run_sql
from app.services.metadata_store import (
    execute,
    fetch_all,
    fetch_one,
    json_dumps,
    json_loads,
    utcnow,
)
from app.services.notebook_sandbox import (
    NotebookSandboxUnavailable,
    execute_sandboxed,
    sandbox_health,
)
from app.services.storage import get_meta, load_dataframe
from app.services.tenant_access import (
    authorize_dataset,
    current_access_context,
)

NotebookLanguage = Literal["markdown", "python", "sql", "r"]
LOCAL_SCOPE_ID = "__local__"


def _ensure_tables() -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS notebook_documents (
            id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            dataset_id TEXT,
            dataset_version TEXT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS notebook_cells (
            id TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            language TEXT NOT NULL,
            source TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS notebook_runs (
            id TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL,
            cell_id TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            dataset_id TEXT,
            dataset_version TEXT,
            language TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            engine TEXT,
            stdout TEXT NOT NULL,
            stderr TEXT NOT NULL,
            result_json TEXT NOT NULL,
            artifacts_json TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            error_type TEXT,
            elapsed_ms REAL,
            created_by TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL
        )"""
    )


def _scope(require_run: bool = False) -> tuple[str, str, str | None]:
    access = current_access_context()
    if access is None:
        return "local", LOCAL_SCOPE_ID, None

    if require_run and not has_permission(
        access.user_id,
        access.workspace_id,
        "analysis:run",
    ):
        raise PermissionError("Permission insuffisante: analysis:run.")

    return "workspace", access.workspace_id, access.user_id


def _authorize_dataset(dataset_id: str | None, permission: str = "dataset:read") -> None:
    if not dataset_id:
        return
    access = current_access_context()
    if access is not None:
        authorize_dataset(dataset_id, permission, access)


def _notebook_row(notebook_id: str) -> dict[str, Any]:
    _ensure_tables()
    scope_type, scope_id, _actor = _scope()
    row = fetch_one(
        """SELECT * FROM notebook_documents
           WHERE id=:id AND scope_type=:scope_type AND scope_id=:scope_id""",
        {
            "id": notebook_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
    )
    if not row:
        raise KeyError("Notebook introuvable.")
    _authorize_dataset(row.get("dataset_id"), "dataset:read")
    return row


def _cell_row(notebook_id: str, cell_id: str) -> dict[str, Any]:
    _notebook_row(notebook_id)
    row = fetch_one(
        """SELECT * FROM notebook_cells
           WHERE id=:cell AND notebook_id=:notebook""",
        {"cell": cell_id, "notebook": notebook_id},
    )
    if not row:
        raise KeyError("Cellule introuvable.")
    return row


def _artifact_root() -> Path:
    root = get_settings().data_root / "notebooks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(name: str, fallback: str = "artifact.bin") -> str:
    candidate = Path(name or fallback).name
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate)
    return candidate[:180] or fallback


def _save_artifacts(
    notebook_id: str,
    run_id: str,
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not artifacts:
        return []

    target_dir = _artifact_root() / notebook_id / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    for index, item in enumerate(artifacts[:20], start=1):
        raw_b64 = item.get("content_base64")
        if not isinstance(raw_b64, str):
            continue
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except Exception:
            continue
        if len(raw) > 5 * 1024 * 1024:
            continue

        name = _safe_filename(
            str(item.get("name") or f"artifact_{index}.bin")
        )
        path = target_dir / name
        path.write_bytes(raw)

        saved.append(
            {
                "name": name,
                "size": len(raw),
                "extension": path.suffix.lower(),
                "download_path": (
                    f"/api/v1/notebooks/{notebook_id}/runs/"
                    f"{run_id}/artifacts/{name}"
                ),
            }
        )

    return saved


def _latest_runs(notebook_id: str) -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        """SELECT * FROM notebook_runs
           WHERE notebook_id=:id
           ORDER BY started_at DESC""",
        {"id": notebook_id},
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        cell_id = str(row["cell_id"])
        if cell_id not in latest:
            latest[cell_id] = _run_payload(row)
    return latest


def _run_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "notebook_id": row["notebook_id"],
        "cell_id": row["cell_id"],
        "dataset_id": row.get("dataset_id"),
        "dataset_version": row.get("dataset_version"),
        "language": row["language"],
        "status": row["status"],
        "engine": row.get("engine"),
        "stdout": row.get("stdout") or "",
        "stderr": row.get("stderr") or "",
        "result": json_loads(row.get("result_json"), None),
        "artifacts": json_loads(row.get("artifacts_json"), []),
        "provenance": json_loads(row.get("provenance_json"), {}),
        "error_type": row.get("error_type"),
        "elapsed_ms": row.get("elapsed_ms"),
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _notebook_payload(row: dict[str, Any], *, include_cells: bool = True) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "scope_type": row["scope_type"],
        "scope_id": row["scope_id"],
        "dataset_id": row.get("dataset_id"),
        "dataset_version": row.get("dataset_version"),
        "name": row["name"],
        "description": row.get("description") or "",
        "created_by": row.get("created_by"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

    if include_cells:
        latest = _latest_runs(row["id"])
        cells = fetch_all(
            """SELECT * FROM notebook_cells
               WHERE notebook_id=:id
               ORDER BY position,id""",
            {"id": row["id"]},
        )
        payload["cells"] = [
            {
                "id": cell["id"],
                "position": int(cell["position"]),
                "language": cell["language"],
                "source": cell["source"],
                "metadata": json_loads(cell.get("metadata_json"), {}),
                "created_at": cell["created_at"],
                "updated_at": cell["updated_at"],
                "last_run": latest.get(str(cell["id"])),
            }
            for cell in cells
        ]

    return payload


def list_notebooks(dataset_id: str | None = None) -> list[dict[str, Any]]:
    _ensure_tables()
    scope_type, scope_id, _actor = _scope()
    params: dict[str, Any] = {
        "scope_type": scope_type,
        "scope_id": scope_id,
    }
    where = "scope_type=:scope_type AND scope_id=:scope_id"

    if dataset_id:
        _authorize_dataset(dataset_id)
        where += " AND dataset_id=:dataset_id"
        params["dataset_id"] = dataset_id

    rows = fetch_all(
        f"""SELECT * FROM notebook_documents
            WHERE {where}
            ORDER BY updated_at DESC""",
        params,
    )
    return [_notebook_payload(row, include_cells=False) for row in rows]


def create_notebook(
    *,
    name: str,
    dataset_id: str | None,
    description: str = "",
) -> dict[str, Any]:
    _ensure_tables()
    scope_type, scope_id, actor = _scope(require_run=True)
    now = utcnow()
    notebook_id = str(uuid.uuid4())
    dataset_version = None

    if dataset_id:
        _authorize_dataset(dataset_id)
        meta = get_meta(dataset_id)
        dataset_version = str(meta.get("version") or "1")

    execute(
        """INSERT INTO notebook_documents(
            id,scope_type,scope_id,dataset_id,dataset_version,name,description,
            created_by,created_at,updated_at
        ) VALUES(
            :id,:scope_type,:scope_id,:dataset_id,:dataset_version,:name,:description,
            :created_by,:created_at,:updated_at
        )""",
        {
            "id": notebook_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "name": (name or "Notebook DataVision").strip()[:180],
            "description": (description or "").strip()[:1000],
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
        },
    )

    seed_cells = [
        (
            "markdown",
            "# Analyse DataVision\n\nCe notebook est relié à la version active du dataset.",
        ),
        (
            "python",
            "# Le dataset gouverné est disponible dans `df` et `dataset`.\n"
            "df.head()",
        ),
        (
            "sql",
            "SELECT * FROM dataset LIMIT 20",
        ),
        (
            "r",
            "# Le dataset gouverné est disponible dans `data` et `dataset`.\n"
            "head(data)",
        ),
    ]

    for position, (language, source) in enumerate(seed_cells):
        add_cell(
            notebook_id=notebook_id,
            language=language,
            source=source,
            position=position,
        )

    record_event(
        "notebook.create",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook",
        resource_id=notebook_id,
        payload={
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
        },
    )
    return get_notebook(notebook_id)


def get_notebook(notebook_id: str) -> dict[str, Any]:
    return _notebook_payload(_notebook_row(notebook_id))


def update_notebook(
    notebook_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    row = _notebook_row(notebook_id)
    _scope(require_run=True)
    execute(
        """UPDATE notebook_documents
           SET name=:name,description=:description,updated_at=:updated
           WHERE id=:id""",
        {
            "id": notebook_id,
            "name": (name if name is not None else row["name"]).strip()[:180],
            "description": (
                description if description is not None else row.get("description", "")
            ).strip()[:1000],
            "updated": utcnow(),
        },
    )
    return get_notebook(notebook_id)


def delete_notebook(notebook_id: str) -> None:
    row = _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    execute(
        "DELETE FROM notebook_runs WHERE notebook_id=:id",
        {"id": notebook_id},
    )
    execute(
        "DELETE FROM notebook_cells WHERE notebook_id=:id",
        {"id": notebook_id},
    )
    execute(
        "DELETE FROM notebook_documents WHERE id=:id",
        {"id": notebook_id},
    )
    root = _artifact_root() / notebook_id
    if root.exists():
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    record_event(
        "notebook.delete",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook",
        resource_id=notebook_id,
        payload={"dataset_id": row.get("dataset_id")},
    )


def add_cell(
    *,
    notebook_id: str,
    language: NotebookLanguage,
    source: str = "",
    position: int | None = None,
) -> dict[str, Any]:
    _notebook_row(notebook_id)
    _scope(require_run=True)
    if language not in {"markdown", "python", "sql", "r"}:
        raise ValueError("Langage de cellule non supporté.")

    if position is None:
        row = fetch_one(
            """SELECT COALESCE(MAX(position),-1) AS max_position
               FROM notebook_cells WHERE notebook_id=:id""",
            {"id": notebook_id},
        ) or {}
        position = int(row.get("max_position") or -1) + 1

    cell_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """INSERT INTO notebook_cells(
            id,notebook_id,position,language,source,metadata_json,created_at,updated_at
        ) VALUES(
            :id,:notebook,:position,:language,:source,:metadata,:created,:updated
        )""",
        {
            "id": cell_id,
            "notebook": notebook_id,
            "position": int(position),
            "language": language,
            "source": source,
            "metadata": "{}",
            "created": now,
            "updated": now,
        },
    )
    execute(
        "UPDATE notebook_documents SET updated_at=:updated WHERE id=:id",
        {"updated": now, "id": notebook_id},
    )
    return get_notebook(notebook_id)


def update_cell(
    notebook_id: str,
    cell_id: str,
    *,
    language: NotebookLanguage | None = None,
    source: str | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    cell = _cell_row(notebook_id, cell_id)
    _scope(require_run=True)
    next_language = language or cell["language"]
    if next_language not in {"markdown", "python", "sql", "r"}:
        raise ValueError("Langage de cellule non supporté.")

    now = utcnow()
    execute(
        """UPDATE notebook_cells
           SET position=:position,language=:language,source=:source,updated_at=:updated
           WHERE id=:cell AND notebook_id=:notebook""",
        {
            "position": int(position if position is not None else cell["position"]),
            "language": next_language,
            "source": source if source is not None else cell["source"],
            "updated": now,
            "cell": cell_id,
            "notebook": notebook_id,
        },
    )
    execute(
        "UPDATE notebook_documents SET updated_at=:updated WHERE id=:id",
        {"updated": now, "id": notebook_id},
    )
    return get_notebook(notebook_id)


def delete_cell(notebook_id: str, cell_id: str) -> dict[str, Any]:
    _cell_row(notebook_id, cell_id)
    _scope(require_run=True)
    execute(
        "DELETE FROM notebook_cells WHERE id=:cell AND notebook_id=:notebook",
        {"cell": cell_id, "notebook": notebook_id},
    )
    execute(
        "UPDATE notebook_documents SET updated_at=:updated WHERE id=:id",
        {"updated": utcnow(), "id": notebook_id},
    )
    return get_notebook(notebook_id)


def list_runs(notebook_id: str, limit: int = 100) -> list[dict[str, Any]]:
    _notebook_row(notebook_id)
    rows = fetch_all(
        """SELECT * FROM notebook_runs
           WHERE notebook_id=:id
           ORDER BY started_at DESC
           LIMIT :limit""",
        {"id": notebook_id, "limit": max(1, min(int(limit), 500))},
    )
    return [_run_payload(row) for row in rows]


def run_cell(notebook_id: str, cell_id: str) -> dict[str, Any]:
    notebook = _notebook_row(notebook_id)
    cell = _cell_row(notebook_id, cell_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    dataset_id = notebook.get("dataset_id")
    dataset_version = notebook.get("dataset_version")
    language = str(cell["language"])
    source = str(cell["source"] or "")
    started = utcnow()
    run_id = str(uuid.uuid4())

    if language == "markdown":
        runtime_result = {
            "status": "succeeded",
            "engine": "markdown",
            "stdout": "",
            "stderr": "",
            "result": {
                "type": "markdown",
                "value": source,
            },
            "artifacts": [],
            "elapsed_ms": 0.0,
            "error_type": None,
        }
    else:
        if not dataset_id:
            raise ValueError(
                "Une cellule exécutable nécessite un dataset lié au notebook."
            )
        _authorize_dataset(dataset_id)
        frame = load_dataframe(dataset_id)

        if language == "sql":
            try:
                result = run_sql(frame, source, limit=500)
                runtime_result = {
                    "status": "succeeded",
                    "engine": result.get("engine"),
                    "stdout": "",
                    "stderr": "",
                    "result": {
                        "type": "dataframe",
                        "columns": result["columns"],
                        "rows": result["rows"],
                        "shape": [
                            result["returned_rows"],
                            len(result["columns"]),
                        ],
                        "truncated": result["truncated"],
                        "query": result["query"],
                    },
                    "artifacts": [],
                    "elapsed_ms": result["elapsed_ms"],
                    "error_type": None,
                }
            except Exception as exc:
                runtime_result = {
                    "status": "failed",
                    "engine": "sql-readonly",
                    "stdout": "",
                    "stderr": str(exc),
                    "result": None,
                    "artifacts": [],
                    "elapsed_ms": 0.0,
                    "error_type": type(exc).__name__,
                }
        elif language in {"python", "r"}:
            try:
                runtime_result = execute_sandboxed(
                    language=language,
                    code=source,
                    dataframe=frame,
                )
            except NotebookSandboxUnavailable as exc:
                runtime_result = {
                    "status": "failed",
                    "engine": language,
                    "stdout": "",
                    "stderr": str(exc),
                    "result": None,
                    "artifacts": [],
                    "elapsed_ms": 0.0,
                    "error_type": "SandboxUnavailable",
                }
        else:
            raise ValueError("Langage de cellule non supporté.")

    artifacts = _save_artifacts(
        notebook_id,
        run_id,
        runtime_result.get("artifacts") or [],
    )

    finished = utcnow()
    provenance = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "notebook_id": notebook_id,
        "cell_id": cell_id,
        "language": language,
        "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "execution_boundary": (
            "read-only SQL engine"
            if language == "sql"
            else "isolated sandbox service"
            if language in {"python", "r"}
            else "non-executable markdown"
        ),
        "workspace_id": scope_id if scope_type == "workspace" else None,
    }

    execute(
        """INSERT INTO notebook_runs(
            id,notebook_id,cell_id,scope_type,scope_id,dataset_id,dataset_version,
            language,source_hash,status,engine,stdout,stderr,result_json,
            artifacts_json,provenance_json,error_type,elapsed_ms,created_by,
            started_at,finished_at
        ) VALUES(
            :id,:notebook,:cell,:scope_type,:scope_id,:dataset_id,:dataset_version,
            :language,:source_hash,:status,:engine,:stdout,:stderr,:result,
            :artifacts,:provenance,:error_type,:elapsed_ms,:created_by,
            :started,:finished
        )""",
        {
            "id": run_id,
            "notebook": notebook_id,
            "cell": cell_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "language": language,
            "source_hash": provenance["source_hash"],
            "status": runtime_result.get("status") or "failed",
            "engine": runtime_result.get("engine"),
            "stdout": runtime_result.get("stdout") or "",
            "stderr": runtime_result.get("stderr") or "",
            "result": json_dumps(runtime_result.get("result")),
            "artifacts": json_dumps(artifacts),
            "provenance": json_dumps(provenance),
            "error_type": runtime_result.get("error_type"),
            "elapsed_ms": runtime_result.get("elapsed_ms"),
            "created_by": actor,
            "started": started,
            "finished": finished,
        },
    )
    execute(
        "UPDATE notebook_documents SET updated_at=:updated WHERE id=:id",
        {"updated": finished, "id": notebook_id},
    )

    record_event(
        "notebook.cell_run",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook_cell",
        resource_id=cell_id,
        outcome=(
            "success"
            if runtime_result.get("status") == "succeeded"
            else "failed"
        ),
        payload={
            "notebook_id": notebook_id,
            "run_id": run_id,
            "language": language,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "elapsed_ms": runtime_result.get("elapsed_ms"),
            "error_type": runtime_result.get("error_type"),
        },
    )

    row = fetch_one(
        "SELECT * FROM notebook_runs WHERE id=:id",
        {"id": run_id},
    )
    assert row is not None
    return _run_payload(row)


def artifact_path(
    notebook_id: str,
    run_id: str,
    filename: str,
) -> Path:
    _notebook_row(notebook_id)
    row = fetch_one(
        """SELECT id FROM notebook_runs
           WHERE id=:run AND notebook_id=:notebook""",
        {"run": run_id, "notebook": notebook_id},
    )
    if not row:
        raise KeyError("Run introuvable.")

    safe = _safe_filename(filename)
    path = _artifact_root() / notebook_id / run_id / safe
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(safe)
    return path


def runtime_status() -> dict[str, Any]:
    try:
        sandbox = sandbox_health()
        sandbox_ok = True
    except Exception as exc:
        sandbox = {"status": "unavailable", "detail": str(exc)}
        sandbox_ok = False

    return {
        "sql": {
            "status": "ok",
            "boundary": "DataVision read-only SQL Workspace",
        },
        "sandbox": sandbox,
        "python": {
            "status": "ok" if sandbox_ok else "unavailable",
            "boundary": "isolated sandbox service",
        },
        "r": {
            "status": "ok" if sandbox_ok else "unavailable",
            "boundary": "isolated sandbox service",
        },
    }
