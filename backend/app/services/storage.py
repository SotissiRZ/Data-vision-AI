from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json", ".parquet", ".txt"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_path(dataset_id: str) -> Path:
    return get_settings().upload_dir / f"{dataset_id}.json"


def _write_meta(meta: dict) -> None:
    _meta_path(meta["id"]).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def save_upload(filename: str, content: bytes) -> dict:
    settings = get_settings()
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Format non supporté: {ext}")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"Fichier trop volumineux (max {settings.max_upload_mb} MB)")

    dataset_id = str(uuid.uuid4())
    target = settings.upload_dir / f"{dataset_id}{ext}"
    target.write_bytes(content)
    meta = {
        "id": dataset_id,
        "root_id": dataset_id,
        "parent_id": None,
        "version": 1,
        "original_name": Path(filename).name,
        "extension": ext,
        "path": str(target),
        "created_at": _now(),
        "operation": {"type": "upload", "label": "Import du fichier original"},
    }
    _write_meta(meta)
    return meta


def save_dataframe_version(parent_id: str, df: pd.DataFrame, operation: dict, *, governance_materialized: bool = True) -> dict:
    """Persist a transformed dataframe as an immutable CSV version with schema metadata."""
    parent = get_meta(parent_id)
    settings = get_settings()
    dataset_id = str(uuid.uuid4())
    target = settings.upload_dir / f"{dataset_id}.csv"
    df.to_csv(target, index=False)
    schema = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
    root_id = parent.get("root_id") or parent["id"]
    existing_versions = []
    for meta_path in settings.upload_dir.glob("*.json"):
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (existing.get("root_id") or existing.get("id")) == root_id:
            existing_versions.append(int(existing.get("version", 1)))
    version = max(existing_versions or [int(parent.get("version", 1))]) + 1
    source_stem = Path(parent.get("source_name") or parent.get("original_name", "dataset")).stem
    stem = source_stem
    meta = {
        "id": dataset_id,
        "root_id": root_id,
        "parent_id": parent_id,
        "version": version,
        "original_name": f"{stem}_v{version}.csv",
        "source_name": parent.get("source_name") or parent.get("original_name"),
        "extension": ".csv",
        "path": str(target),
        "created_at": _now(),
        "operation": operation,
        "schema": schema,
    }
    try:
        from app.services.tenant_access import current_access_context, inherited_policies
        ctx = current_access_context()
        if ctx is not None and governance_materialized:
            policies = inherited_policies(parent_id, ctx)
            meta["governance_materialization"] = {
                "workspace_id": ctx.workspace_id,
                "role": ctx.role,
                "row_security_materialized": True,
                "policy_versions": [
                    {"id": p.get("id"), "updated_at": p.get("updated_at")}
                    for p in policies if p.get("id")
                ],
            }
    except PermissionError:
        raise
    except Exception:
        pass
    _write_meta(meta)
    try:
        from app.services.tenant_access import bind_derived_dataset
        bind_derived_dataset(parent_id, dataset_id)
    except PermissionError:
        raise
    except Exception:
        # Metadata persistence is authoritative; local mode and migrations must remain usable.
        pass
    return meta



def save_dataframe_source(df: pd.DataFrame, source_name: str, source_metadata: dict | None = None) -> dict:
    """Persist a dataframe obtained from an external connector as a new immutable root dataset."""
    settings = get_settings()
    dataset_id = str(uuid.uuid4())
    target = settings.upload_dir / f"{dataset_id}.csv"
    df.to_csv(target, index=False)
    schema = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
    meta = {
        "id": dataset_id, "root_id": dataset_id, "parent_id": None, "version": 1,
        "original_name": f"{Path(source_name).stem or 'source'}.csv", "source_name": source_name,
        "extension": ".csv", "path": str(target), "created_at": _now(),
        "operation": {"type": "connector_import", "label": "Import depuis une source externe"},
        "schema": schema, "external_source": source_metadata or {},
    }
    _write_meta(meta)
    return meta


def get_meta(dataset_id: str) -> dict:
    meta_path = _meta_path(dataset_id)
    if not meta_path.exists():
        raise FileNotFoundError(dataset_id)
    return json.loads(meta_path.read_text(encoding="utf-8"))


def get_lineage(dataset_id: str) -> list[dict]:
    """Return current version ancestry from v1 to the selected version."""
    chain: list[dict] = []
    current = get_meta(dataset_id)
    seen: set[str] = set()
    while current and current["id"] not in seen:
        seen.add(current["id"])
        chain.append(current)
        parent_id = current.get("parent_id")
        if not parent_id:
            break
        current = get_meta(parent_id)
    chain.reverse()
    return chain


def list_versions(dataset_id: str) -> list[dict]:
    """Return all persisted versions belonging to the same root dataset."""
    root_id = get_meta(dataset_id).get("root_id") or dataset_id
    versions: list[dict] = []
    for meta_path in get_settings().upload_dir.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (meta.get("root_id") or meta.get("id")) == root_id:
            versions.append(meta)
    versions.sort(key=lambda x: (int(x.get("version", 1)), x.get("created_at", "")))
    return versions



def list_dataset_catalog() -> list[dict]:
    """List persisted dataset versions, newest first, for local workspace selection."""
    rows: list[dict] = []
    for meta_path in get_settings().upload_dir.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "id": meta.get("id"),
            "root_id": meta.get("root_id") or meta.get("id"),
            "parent_id": meta.get("parent_id"),
            "version": int(meta.get("version", 1)),
            "name": meta.get("original_name"),
            "source_name": meta.get("source_name") or meta.get("original_name"),
            "created_at": meta.get("created_at"),
            "operation": meta.get("operation"),
        })
    try:
        from app.services.tenant_access import governed_catalog_ids
        visible_roots = governed_catalog_ids()
    except PermissionError:
        raise
    except Exception:
        visible_roots = None
    if visible_roots is not None:
        rows = [row for row in rows if str(row.get("root_id") or row.get("id")) in visible_roots]
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return rows


def _restore_schema(df: pd.DataFrame, schema: dict | None) -> pd.DataFrame:
    if not schema:
        return df
    out = df.copy()
    for column, dtype in schema.items():
        if column not in out.columns:
            continue
        try:
            low = dtype.lower()
            if low.startswith("datetime"):
                out[column] = pd.to_datetime(out[column], errors="coerce")
            elif low in {"boolean", "bool"}:
                out[column] = out[column].astype("boolean")
            elif low.startswith("int") or low.startswith("uint") or low == "int64":
                out[column] = pd.to_numeric(out[column], errors="coerce").astype("Int64")
            elif low.startswith("float"):
                out[column] = pd.to_numeric(out[column], errors="coerce").astype(float)
            elif low == "category":
                out[column] = out[column].astype("category")
            elif low.startswith("string"):
                out[column] = out[column].astype("string")
        except Exception:
            # A stored schema is advisory; loading the values is preferable to making a version unreadable.
            continue
    return out


def load_dataframe_raw(dataset_id: str) -> pd.DataFrame:
    """Load the immutable persisted dataset without applying tenant policies.

    This function is reserved for trusted internal lifecycle operations such as connector
    refresh. User-facing analytics must call load_dataframe().
    """
    meta = get_meta(dataset_id)
    path = Path(meta["path"])
    ext = meta["extension"]
    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext == ".txt":
        df = pd.read_csv(path, sep=None, engine="python")
    elif ext == ".xlsx":
        df = pd.read_excel(path)
    elif ext == ".json":
        try:
            df = pd.read_json(path)
        except ValueError:
            df = pd.read_json(path, lines=True)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Format non supporté: {ext}")
    return _restore_schema(df, meta.get("schema"))


def load_dataframe(dataset_id: str) -> pd.DataFrame:
    df = load_dataframe_raw(dataset_id)
    try:
        from app.services.tenant_access import current_access_context, govern_dataframe
        if current_access_context() is not None:
            df, _ = govern_dataframe(dataset_id, df)
    except PermissionError:
        raise
    return df
