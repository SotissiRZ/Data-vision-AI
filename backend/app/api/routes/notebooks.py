from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.notebook_service import (
    add_cell,
    artifact_path,
    bind_notebook_dataset,
    create_notebook,
    delete_cell,
    delete_notebook,
    get_notebook,
    list_notebooks,
    list_runs,
    promote_artifact_to_dataset,
    run_cell,
    run_notebook,
    runtime_status,
    update_cell,
    update_notebook,
)

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


class NotebookCreateRequest(BaseModel):
    name: str = Field(default="Notebook DataVision", min_length=1, max_length=180)
    dataset_id: str | None = None
    description: str = Field(default="", max_length=1000)


class NotebookUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=1000)




class NotebookBindRequest(BaseModel):
    dataset_id: str | None = None


class NotebookRunRequest(BaseModel):
    continue_on_error: bool = False


class CellCreateRequest(BaseModel):
    language: str = Field(pattern="^(markdown|python|sql|r)$")
    source: str = Field(default="", max_length=100000)
    position: int | None = Field(default=None, ge=0)


class CellUpdateRequest(BaseModel):
    language: str | None = Field(
        default=None,
        pattern="^(markdown|python|sql|r)$",
    )
    source: str | None = Field(default=None, max_length=100000)
    position: int | None = Field(default=None, ge=0)


def _error(exc: Exception):
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/runtime")
def notebook_runtime():
    return runtime_status()


@router.get("")
def notebook_list(dataset_id: str | None = None):
    try:
        return {"items": list_notebooks(dataset_id)}
    except Exception as exc:
        _error(exc)


@router.post("")
def notebook_create(payload: NotebookCreateRequest):
    try:
        return create_notebook(
            name=payload.name,
            dataset_id=payload.dataset_id,
            description=payload.description,
        )
    except Exception as exc:
        _error(exc)


@router.get("/{notebook_id}")
def notebook_detail(notebook_id: str):
    try:
        return get_notebook(notebook_id)
    except Exception as exc:
        _error(exc)


@router.patch("/{notebook_id}")
def notebook_update(
    notebook_id: str,
    payload: NotebookUpdateRequest,
):
    try:
        return update_notebook(
            notebook_id,
            name=payload.name,
            description=payload.description,
        )
    except Exception as exc:
        _error(exc)


@router.delete("/{notebook_id}")
def notebook_delete(notebook_id: str):
    try:
        delete_notebook(notebook_id)
        return {"ok": True}
    except Exception as exc:
        _error(exc)


@router.post("/{notebook_id}/bind")
def notebook_bind(notebook_id: str, payload: NotebookBindRequest):
    try:
        return bind_notebook_dataset(notebook_id, payload.dataset_id)
    except Exception as exc:
        _error(exc)


@router.post("/{notebook_id}/run")
def notebook_run_all(notebook_id: str, payload: NotebookRunRequest | None = None):
    try:
        return run_notebook(
            notebook_id,
            continue_on_error=bool(payload and payload.continue_on_error),
        )
    except Exception as exc:
        _error(exc)


@router.post("/{notebook_id}/cells")
def cell_create(
    notebook_id: str,
    payload: CellCreateRequest,
):
    try:
        return add_cell(
            notebook_id=notebook_id,
            language=payload.language,
            source=payload.source,
            position=payload.position,
        )
    except Exception as exc:
        _error(exc)


@router.patch("/{notebook_id}/cells/{cell_id}")
def cell_update(
    notebook_id: str,
    cell_id: str,
    payload: CellUpdateRequest,
):
    try:
        return update_cell(
            notebook_id,
            cell_id,
            language=payload.language,
            source=payload.source,
            position=payload.position,
        )
    except Exception as exc:
        _error(exc)


@router.delete("/{notebook_id}/cells/{cell_id}")
def cell_delete(notebook_id: str, cell_id: str):
    try:
        return delete_cell(notebook_id, cell_id)
    except Exception as exc:
        _error(exc)


@router.post("/{notebook_id}/cells/{cell_id}/run")
def cell_run(notebook_id: str, cell_id: str):
    try:
        return run_cell(notebook_id, cell_id)
    except Exception as exc:
        _error(exc)


@router.get("/{notebook_id}/runs")
def notebook_runs(notebook_id: str, limit: int = 100):
    try:
        return {"items": list_runs(notebook_id, limit)}
    except Exception as exc:
        _error(exc)


@router.post(
    "/{notebook_id}/runs/{run_id}/artifacts/{filename}/promote"
)
def notebook_artifact_promote(
    notebook_id: str,
    run_id: str,
    filename: str,
):
    try:
        return promote_artifact_to_dataset(
            notebook_id,
            run_id,
            filename,
        )
    except Exception as exc:
        _error(exc)


@router.get(
    "/{notebook_id}/runs/{run_id}/artifacts/{filename}"
)
def notebook_artifact(
    notebook_id: str,
    run_id: str,
    filename: str,
):
    try:
        path = artifact_path(notebook_id, run_id, filename)
        return FileResponse(path)
    except Exception as exc:
        _error(exc)
