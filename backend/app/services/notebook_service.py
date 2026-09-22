from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

import pandas as pd

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
    close_kernel_session,
    execute_sandboxed,
    execute_sandboxed_session,
    kernel_session_status,
    kernel_session_variables,
    restart_kernel_session,
    sandbox_health,
    sandbox_packages,
)
from app.services.storage import (
    get_lineage,
    get_meta,
    list_versions,
    load_dataframe,
    save_dataframe_version,
)
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
        """CREATE TABLE IF NOT EXISTS notebook_environments (
            notebook_id TEXT PRIMARY KEY,
            python_requirements_json TEXT NOT NULL,
            r_requirements_json TEXT NOT NULL,
            python_lock_json TEXT NOT NULL,
            r_lock_json TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS notebook_kernel_sessions (
            notebook_id TEXT NOT NULL,
            language TEXT NOT NULL,
            session_id TEXT NOT NULL,
            generation TEXT,
            state_status TEXT NOT NULL,
            execution_count INTEGER NOT NULL,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY(notebook_id, language)
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



_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\s*(?:==|>=|<=|~=|>|<)\s*[A-Za-z0-9_.+!-]+)?$")


def _kernel_session_id(notebook_id: str, language: str) -> str:
    scope_type, scope_id, _actor = _scope()
    digest = hashlib.sha256(
        f"{scope_type}:{scope_id}:{notebook_id}:{language}".encode("utf-8")
    ).hexdigest()[:32]
    return f"dv-{language}-{digest}"


def _normalize_requirements(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in values or []:
        value = str(raw or "").strip()
        if not value:
            continue
        if len(value) > 120 or not _PACKAGE_RE.fullmatch(value):
            raise ValueError(f"Exigence package invalide: {value[:80]}")
        if value not in normalized:
            normalized.append(value)
    return normalized[:100]


def _requirement_name(value: str) -> str:
    return re.split(r"\s*(?:==|>=|<=|~=|>|<)\s*", value.strip(), maxsplit=1)[0].lower()


def _environment_row(notebook_id: str, *, create: bool = True) -> dict[str, Any] | None:
    _ensure_tables()
    row = fetch_one(
        "SELECT * FROM notebook_environments WHERE notebook_id=:id",
        {"id": notebook_id},
    )
    if row or not create:
        return row
    now = utcnow()
    execute(
        """INSERT INTO notebook_environments(
            notebook_id,python_requirements_json,r_requirements_json,
            python_lock_json,r_lock_json,policy_json,created_at,updated_at
        ) VALUES(
            :id,:python,:r,:python_lock,:r_lock,:policy,:created,:updated
        )""",
        {
            "id": notebook_id,
            "python": "[]",
            "r": "[]",
            "python_lock": "{}",
            "r_lock": "{}",
            "policy": json_dumps({
                "install_mode": "image-managed",
                "dynamic_install": False,
                "isolation": "sandbox",
            }),
            "created": now,
            "updated": now,
        },
    )
    return fetch_one(
        "SELECT * FROM notebook_environments WHERE notebook_id=:id",
        {"id": notebook_id},
    )


def _environment_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "notebook_id": row["notebook_id"],
        "python_requirements": json_loads(row.get("python_requirements_json"), []),
        "r_requirements": json_loads(row.get("r_requirements_json"), []),
        "python_lock": json_loads(row.get("python_lock_json"), {}),
        "r_lock": json_loads(row.get("r_lock_json"), {}),
        "policy": json_loads(row.get("policy_json"), {}),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _kernel_row(notebook_id: str, language: str) -> dict[str, Any] | None:
    _ensure_tables()
    return fetch_one(
        """SELECT * FROM notebook_kernel_sessions
           WHERE notebook_id=:notebook AND language=:language""",
        {"notebook": notebook_id, "language": language},
    )


def _update_kernel_tracking(
    notebook_id: str,
    language: str,
    runtime: dict[str, Any],
    *,
    state_status: str | None = None,
) -> dict[str, Any]:
    kernel = runtime.get("kernel") if isinstance(runtime.get("kernel"), dict) else runtime
    session_id = str(kernel.get("session_id") or _kernel_session_id(notebook_id, language))
    generation = kernel.get("generation")
    execution_count = int(kernel.get("execution_count") or runtime.get("execution_count") or 0)
    previous = _kernel_row(notebook_id, language)
    prior_generation = previous.get("generation") if previous else None
    created = bool(runtime.get("kernel_created") or kernel.get("created"))
    if state_status is None:
        if created and previous and previous.get("execution_count", 0):
            state_status = "reset"
        elif prior_generation and generation and prior_generation != generation:
            state_status = "reset"
        else:
            state_status = "ready"
    now = utcnow()
    if previous:
        execute(
            """UPDATE notebook_kernel_sessions
               SET session_id=:session,generation=:generation,state_status=:state,
                   execution_count=:count,last_seen_at=:seen
               WHERE notebook_id=:notebook AND language=:language""",
            {
                "session": session_id,
                "generation": generation,
                "state": state_status,
                "count": execution_count,
                "seen": now,
                "notebook": notebook_id,
                "language": language,
            },
        )
    else:
        execute(
            """INSERT INTO notebook_kernel_sessions(
                notebook_id,language,session_id,generation,state_status,
                execution_count,last_seen_at
            ) VALUES(
                :notebook,:language,:session,:generation,:state,:count,:seen
            )""",
            {
                "notebook": notebook_id,
                "language": language,
                "session": session_id,
                "generation": generation,
                "state": state_status,
                "count": execution_count,
                "seen": now,
            },
        )
    row = _kernel_row(notebook_id, language) or {}
    return {
        "language": language,
        "session_id": row.get("session_id"),
        "generation": row.get("generation"),
        "state_status": row.get("state_status", state_status),
        "execution_count": int(row.get("execution_count") or 0),
        "last_seen_at": row.get("last_seen_at"),
        "persistent": True,
    }


def _kernel_payload(
    notebook_id: str,
    language: str,
    *,
    live: bool = False,
) -> dict[str, Any]:
    session_id = _kernel_session_id(notebook_id, language)
    tracked = _kernel_row(notebook_id, language)
    base = {
        "language": language,
        "session_id": session_id,
        "status": "stopped" if tracked is None else "tracked",
        "state_status": "new" if tracked is None else tracked.get("state_status", "ready"),
        "execution_count": int((tracked or {}).get("execution_count") or 0),
        "generation": (tracked or {}).get("generation"),
        "persistent": True,
        "variables": [],
    }
    if not live:
        return base
    try:
        status = kernel_session_status(session_id)
    except NotebookSandboxUnavailable:
        status = None
    if status is None:
        if tracked:
            base["status"] = "lost"
            base["state_status"] = "reset"
        return base
    variables: list[str] = []
    try:
        inspected = kernel_session_variables(session_id)
        variables = list(inspected.get("variables") or [])[:200]
    except Exception:
        variables = []
    return {
        **base,
        "status": status.get("status", "ready"),
        "state_status": "ready",
        "execution_count": int(status.get("execution_count") or 0),
        "generation": status.get("generation"),
        "variables": variables,
    }


def _authorize_dataset(dataset_id: str | None, permission: str = "dataset:read") -> None:
    if not dataset_id:
        return
    access = current_access_context()
    if access is not None:
        authorize_dataset(dataset_id, permission, access)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_binding(dataset_id: str | None) -> dict[str, Any] | None:
    if not dataset_id:
        return None
    meta = get_meta(dataset_id)
    return {
        "id": meta["id"],
        "root_id": meta.get("root_id") or meta["id"],
        "parent_id": meta.get("parent_id"),
        "version": int(meta.get("version") or 1),
        "name": meta.get("original_name"),
        "created_at": meta.get("created_at"),
        "operation": meta.get("operation"),
    }


def _dataset_run_provenance(dataset_id: str, frame) -> dict[str, Any]:
    meta = get_meta(dataset_id)
    path = Path(meta["path"])
    lineage = get_lineage(dataset_id)
    return {
        "dataset_id": dataset_id,
        "dataset_root_id": meta.get("root_id") or dataset_id,
        "dataset_version": str(meta.get("version") or "1"),
        "dataset_name": meta.get("original_name"),
        "dataset_parent_id": meta.get("parent_id"),
        "dataset_created_at": meta.get("created_at"),
        "dataset_operation": meta.get("operation"),
        "dataset_rows": int(len(frame)),
        "dataset_columns": int(len(frame.columns)),
        "dataset_lineage_ids": [item.get("id") for item in lineage],
        "dataset_fingerprint_sha256": _file_sha256(path),
    }


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
        "dataset_binding": _dataset_binding(row.get("dataset_id")),
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
        env_row = _environment_row(row["id"], create=True)
        payload["environment"] = _environment_payload(env_row or {}) if env_row else None
        payload["kernels"] = {
            language: _kernel_payload(row["id"], language)
            for language in ("python", "r")
        }

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
        version_ids = [str(item["id"]) for item in list_versions(dataset_id)]
        if version_ids:
            placeholders = []
            for index, version_id in enumerate(version_ids):
                key = f"dataset_{index}"
                placeholders.append(f":{key}")
                params[key] = version_id
            where += f" AND dataset_id IN ({','.join(placeholders)})"
        else:
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

    _environment_row(notebook_id, create=True)

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


def bind_notebook_dataset(
    notebook_id: str,
    dataset_id: str | None,
) -> dict[str, Any]:
    row = _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    dataset_version = None
    if dataset_id:
        _authorize_dataset(dataset_id, "dataset:read")
        meta = get_meta(dataset_id)
        dataset_version = str(meta.get("version") or "1")

    execute(
        """UPDATE notebook_documents
           SET dataset_id=:dataset_id,dataset_version=:dataset_version,updated_at=:updated
           WHERE id=:id""",
        {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "updated": utcnow(),
            "id": notebook_id,
        },
    )
    if row.get("dataset_id") != dataset_id:
        for kernel_language in ("python", "r"):
            try:
                close_kernel_session(_kernel_session_id(notebook_id, kernel_language))
            except Exception:
                pass
            if _kernel_row(notebook_id, kernel_language):
                execute(
                    """UPDATE notebook_kernel_sessions
                       SET state_status='reset',execution_count=0,last_seen_at=:seen
                       WHERE notebook_id=:notebook AND language=:language""",
                    {
                        "seen": utcnow(),
                        "notebook": notebook_id,
                        "language": kernel_language,
                    },
                )
    record_event(
        "notebook.dataset_bind",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook",
        resource_id=notebook_id,
        payload={
            "previous_dataset_id": row.get("dataset_id"),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
        },
    )
    return get_notebook(notebook_id)


def delete_notebook(notebook_id: str) -> None:
    row = _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    for language in ("python", "r"):
        try:
            close_kernel_session(_kernel_session_id(notebook_id, language))
        except Exception:
            pass
    execute(
        "DELETE FROM notebook_kernel_sessions WHERE notebook_id=:id",
        {"id": notebook_id},
    )
    execute(
        "DELETE FROM notebook_environments WHERE notebook_id=:id",
        {"id": notebook_id},
    )
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
        dataset_meta = get_meta(dataset_id)
        dataset_version = str(dataset_meta.get("version") or dataset_version or "1")

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
            session_id = _kernel_session_id(notebook_id, language)
            try:
                runtime_result = execute_sandboxed_session(
                    session_id=session_id,
                    language=language,
                    code=source,
                    dataframe=frame,
                )
                runtime_result["kernel_tracking"] = _update_kernel_tracking(
                    notebook_id, language, runtime_result
                )
            except NotebookSandboxUnavailable as exc:
                runtime_result = {
                    "status": "failed",
                    "engine": f"{language}-persistent",
                    "stdout": "",
                    "stderr": str(exc),
                    "result": None,
                    "artifacts": [],
                    "elapsed_ms": 0.0,
                    "error_type": "SandboxUnavailable",
                    "kernel_tracking": _kernel_payload(notebook_id, language),
                }
        else:
            raise ValueError("Langage de cellule non supporté.")

    artifacts = _save_artifacts(
        notebook_id,
        run_id,
        runtime_result.get("artifacts") or [],
    )

    finished = utcnow()
    dataset_provenance = {}
    if dataset_id and language != "markdown":
        dataset_provenance = _dataset_run_provenance(dataset_id, frame)

    provenance = {
        **dataset_provenance,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "notebook_id": notebook_id,
        "cell_id": cell_id,
        "language": language,
        "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "artifact_count": len(artifacts),
        "execution_boundary": (
            "read-only SQL engine"
            if language == "sql"
            else "isolated persistent sandbox kernel"
            if language in {"python", "r"}
            else "non-executable markdown"
        ),
        "kernel": runtime_result.get("kernel_tracking") if language in {"python", "r"} else None,
        "kernel_created": bool(runtime_result.get("kernel_created")) if language in {"python", "r"} else False,
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


def run_notebook(
    notebook_id: str,
    *,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    notebook = _notebook_row(notebook_id)
    _scope(require_run=True)
    cells = fetch_all(
        """SELECT id,language FROM notebook_cells
           WHERE notebook_id=:id ORDER BY position,id""",
        {"id": notebook_id},
    )
    runs: list[dict[str, Any]] = []
    for cell in cells:
        result = run_cell(notebook_id, str(cell["id"]))
        runs.append(result)
        if result.get("status") == "failed" and not continue_on_error:
            break
    succeeded = sum(1 for item in runs if item.get("status") == "succeeded")
    failed = sum(1 for item in runs if item.get("status") == "failed")
    return {
        "notebook_id": notebook_id,
        "dataset_id": notebook.get("dataset_id"),
        "dataset_version": notebook.get("dataset_version"),
        "status": "failed" if failed else "succeeded",
        "executed": len(runs),
        "succeeded": succeeded,
        "failed": failed,
        "stopped_early": len(runs) < len(cells),
        "runs": runs,
    }


def promote_artifact_to_dataset(
    notebook_id: str,
    run_id: str,
    filename: str,
) -> dict[str, Any]:
    notebook = _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    row = fetch_one(
        """SELECT * FROM notebook_runs
           WHERE id=:run AND notebook_id=:notebook""",
        {"run": run_id, "notebook": notebook_id},
    )
    if not row:
        raise KeyError("Run introuvable.")

    parent_id = row.get("dataset_id") or notebook.get("dataset_id")
    if not parent_id:
        raise ValueError("Aucun dataset source n'est lié à ce run.")
    _authorize_dataset(str(parent_id), "dataset:write")

    path = artifact_path(notebook_id, run_id, filename)
    extension = path.suffix.lower()
    if extension == ".csv":
        frame = pd.read_csv(path)
    elif extension == ".json":
        try:
            frame = pd.read_json(path)
        except ValueError:
            payload = json.loads(path.read_text(encoding="utf-8"))
            frame = pd.DataFrame(payload)
    else:
        raise ValueError("Seuls les artefacts CSV ou JSON peuvent devenir une version de dataset.")
    if frame.empty and len(frame.columns) == 0:
        raise ValueError("L'artefact ne contient aucune donnée tabulaire.")

    meta = save_dataframe_version(
        str(parent_id),
        frame,
        {
            "type": "notebook_artifact",
            "label": f"Artefact notebook · {path.name}",
            "notebook_id": notebook_id,
            "run_id": run_id,
            "cell_id": row.get("cell_id"),
            "artifact_name": path.name,
            "source_hash": row.get("source_hash"),
        },
    )
    record_event(
        "notebook.artifact_promote",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="dataset",
        resource_id=meta["id"],
        payload={
            "notebook_id": notebook_id,
            "run_id": run_id,
            "parent_dataset_id": parent_id,
            "artifact_name": path.name,
            "dataset_version": meta.get("version"),
        },
    )
    return {
        "dataset": {
            "id": meta["id"],
            "root_id": meta.get("root_id") or meta["id"],
            "parent_id": meta.get("parent_id"),
            "version": int(meta.get("version") or 1),
            "name": meta.get("original_name"),
            "operation": meta.get("operation"),
        }
    }


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



def get_notebook_environment(notebook_id: str) -> dict[str, Any]:
    _notebook_row(notebook_id)
    row = _environment_row(notebook_id, create=True)
    assert row is not None
    return _environment_payload(row)


def update_notebook_environment(
    notebook_id: str,
    *,
    python_requirements: list[str] | None = None,
    r_requirements: list[str] | None = None,
) -> dict[str, Any]:
    _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    row = _environment_row(notebook_id, create=True)
    assert row is not None
    python = (
        _normalize_requirements(python_requirements)
        if python_requirements is not None
        else json_loads(row.get("python_requirements_json"), [])
    )
    r = (
        _normalize_requirements(r_requirements)
        if r_requirements is not None
        else json_loads(row.get("r_requirements_json"), [])
    )
    execute(
        """UPDATE notebook_environments
           SET python_requirements_json=:python,r_requirements_json=:r,
               python_lock_json='{}',r_lock_json='{}',updated_at=:updated
           WHERE notebook_id=:id""",
        {
            "python": json_dumps(python),
            "r": json_dumps(r),
            "updated": utcnow(),
            "id": notebook_id,
        },
    )
    record_event(
        "notebook.environment_update",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook",
        resource_id=notebook_id,
        payload={
            "python_requirements": python,
            "r_requirements": r,
            "install_mode": "image-managed",
        },
    )
    return get_notebook_environment(notebook_id)


def sync_notebook_environment(notebook_id: str) -> dict[str, Any]:
    _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    row = _environment_row(notebook_id, create=True)
    assert row is not None
    env = _environment_payload(row)
    inventory = sandbox_packages()
    python_inventory = {
        str(k).lower(): str(v)
        for k, v in (inventory.get("python") or {}).items()
    }
    r_inventory = {
        str(k).lower(): str(v)
        for k, v in (inventory.get("r") or {}).items()
    }
    python_lock: dict[str, str] = {}
    r_lock: dict[str, str] = {}
    missing_python: list[str] = []
    missing_r: list[str] = []
    for requirement in env["python_requirements"]:
        name = _requirement_name(requirement)
        if name in python_inventory:
            python_lock[name] = python_inventory[name]
        else:
            missing_python.append(requirement)
    for requirement in env["r_requirements"]:
        name = _requirement_name(requirement)
        if name in r_inventory:
            r_lock[name] = r_inventory[name]
        else:
            missing_r.append(requirement)
    execute(
        """UPDATE notebook_environments
           SET python_lock_json=:python_lock,r_lock_json=:r_lock,updated_at=:updated
           WHERE notebook_id=:id""",
        {
            "python_lock": json_dumps(python_lock),
            "r_lock": json_dumps(r_lock),
            "updated": utcnow(),
            "id": notebook_id,
        },
    )
    status = "ready" if not missing_python and not missing_r else "missing_packages"
    record_event(
        "notebook.environment_sync",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook",
        resource_id=notebook_id,
        outcome="success" if status == "ready" else "warning",
        payload={
            "status": status,
            "missing_python": missing_python,
            "missing_r": missing_r,
        },
    )
    return {
        **get_notebook_environment(notebook_id),
        "status": status,
        "missing_python": missing_python,
        "missing_r": missing_r,
        "inventory_policy": inventory.get("install_policy", "image-managed"),
        "dynamic_install": bool(inventory.get("dynamic_install", False)),
    }


def notebook_kernel_status(notebook_id: str) -> dict[str, Any]:
    _notebook_row(notebook_id)
    return {
        "notebook_id": notebook_id,
        "persistent": True,
        "kernels": {
            language: _kernel_payload(notebook_id, language, live=True)
            for language in ("python", "r")
        },
    }


def restart_notebook_kernel(notebook_id: str, language: str) -> dict[str, Any]:
    _notebook_row(notebook_id)
    scope_type, scope_id, actor = _scope(require_run=True)
    if language not in {"python", "r"}:
        raise ValueError("Kernel non supporté.")
    session_id = _kernel_session_id(notebook_id, language)
    runtime = restart_kernel_session(session_id=session_id, language=language)
    tracked = _update_kernel_tracking(
        notebook_id,
        language,
        {"kernel": runtime, "kernel_created": True},
        state_status="reset",
    )
    record_event(
        "notebook.kernel_restart",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="notebook",
        resource_id=notebook_id,
        payload={"language": language, "session_id": session_id},
    )
    return tracked


def restart_notebook_kernels(notebook_id: str, *, replay: bool = False) -> dict[str, Any]:
    _notebook_row(notebook_id)
    kernels = {
        language: restart_notebook_kernel(notebook_id, language)
        for language in ("python", "r")
    }
    replay_result = run_notebook(notebook_id, continue_on_error=False) if replay else None
    return {
        "notebook_id": notebook_id,
        "kernels": kernels,
        "replayed": bool(replay),
        "replay_result": replay_result,
    }


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
            "boundary": "isolated persistent sandbox kernel",
            "persistent": True,
        },
        "r": {
            "status": "ok" if sandbox_ok else "unavailable",
            "boundary": "isolated persistent sandbox kernel",
            "persistent": True,
        },
        "environment": {
            "install_mode": "image-managed",
            "dynamic_install": False,
        },
    }
