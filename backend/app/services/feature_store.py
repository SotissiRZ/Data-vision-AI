from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import pandas as pd

from app.services.audit_service import record_event
from app.services.metadata_store import (
    execute,
    fetch_all,
    fetch_one,
    json_dumps,
    json_loads,
    utcnow,
)
from app.services.modeling import get_model_card
from app.services.storage import (
    get_meta,
    load_dataframe,
    save_dataframe_source,
)

STATUSES = {"draft", "active", "archived"}


def _schema_for_frame(
    frame: pd.DataFrame,
    columns: list[str],
) -> list[dict[str, Any]]:
    result = []
    for name in columns:
        series = frame[name]
        dtype = str(series.dtype)
        if pd.api.types.is_numeric_dtype(series):
            family = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(series):
            family = "datetime"
        elif pd.api.types.is_bool_dtype(series):
            family = "boolean"
        else:
            family = "categorical"
        result.append(
            {
                "name": name,
                "dtype": dtype,
                "family": family,
                "nullable": bool(series.isna().any()),
            }
        )
    return result


def _schema_hash(schema: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _hydrate(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["entity_keys"] = json_loads(item.pop("entity_keys_json", "[]"), [])
    item["features"] = json_loads(item.pop("features_json", "[]"), [])
    item["schema"] = json_loads(item.pop("schema_json", "[]"), [])
    return item


def create_feature_set(
    actor_id: str,
    workspace_id: str,
    *,
    name: str,
    source_dataset_id: str,
    features: list[str],
    entity_keys: list[str] | None = None,
    event_time_column: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Nom du Feature Set requis.")

    frame = load_dataframe(source_dataset_id)
    get_meta(source_dataset_id)
    feature_names = list(dict.fromkeys(str(x).strip() for x in features if str(x).strip()))
    entity_names = list(dict.fromkeys(str(x).strip() for x in (entity_keys or []) if str(x).strip()))

    if not feature_names:
        raise ValueError("Au moins une feature est requise.")

    required = (
        entity_names
        + ([event_time_column] if event_time_column else [])
        + feature_names
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Colonnes inconnues dans le dataset source: {missing}")

    if set(feature_names) & set(entity_names):
        raise ValueError("Une entity key ne doit pas être dupliquée comme feature.")

    selected = list(dict.fromkeys(required))
    schema = _schema_for_frame(frame, selected)
    feature_defs = [
        next(item for item in schema if item["name"] == name)
        for name in feature_names
    ]

    feature_set_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """
        INSERT INTO feature_sets(
          id,workspace_id,name,description,source_dataset_id,
          entity_keys_json,event_time_column,features_json,schema_json,
          schema_sha256,status,created_by,created_at,updated_at
        ) VALUES(
          :id,:ws,:name,:description,:source,:entities,:event_time,
          :features,:schema,:sha,'draft',:actor,:created,:updated
        )
        """,
        {
            "id": feature_set_id,
            "ws": workspace_id,
            "name": clean_name[:240],
            "description": description.strip()[:2000] or None,
            "source": source_dataset_id,
            "entities": json_dumps(entity_names),
            "event_time": event_time_column,
            "features": json_dumps(feature_defs),
            "schema": json_dumps(schema),
            "sha": _schema_hash(schema),
            "actor": actor_id,
            "created": now,
            "updated": now,
        },
    )
    record_event(
        "feature_store.created",
        user_id=None if actor_id.startswith("__local") else actor_id,
        workspace_id=None if workspace_id == "__local__" else workspace_id,
        resource_type="feature_set",
        resource_id=feature_set_id,
        payload={
            "source_dataset_id": source_dataset_id,
            "features": feature_names,
            "entity_keys": entity_names,
        },
    )
    return get_feature_set(workspace_id, feature_set_id)


def get_feature_set(workspace_id: str, feature_set_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM feature_sets WHERE workspace_id=:ws AND id=:id",
        {"ws": workspace_id, "id": feature_set_id},
    )
    if not row:
        raise KeyError("Feature Set introuvable.")
    item = _hydrate(row) or {}
    mats = fetch_all(
        """
        SELECT * FROM feature_materializations
        WHERE workspace_id=:ws AND feature_set_id=:id
        ORDER BY created_at DESC LIMIT 50
        """,
        {"ws": workspace_id, "id": feature_set_id},
    )
    item["materializations"] = mats
    return item


def list_feature_sets(
    workspace_id: str,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws": workspace_id}
    where = "workspace_id=:ws"
    if status:
        if status not in STATUSES:
            raise ValueError("Statut Feature Store invalide.")
        where += " AND status=:status"
        params["status"] = status
    return [
        _hydrate(row) or {}
        for row in fetch_all(
            f"SELECT * FROM feature_sets WHERE {where} ORDER BY updated_at DESC",
            params,
        )
    ]


def set_feature_set_status(
    actor_id: str,
    workspace_id: str,
    feature_set_id: str,
    status: str,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError("Statut Feature Store invalide.")
    current = get_feature_set(workspace_id, feature_set_id)
    execute(
        """
        UPDATE feature_sets SET status=:status,updated_at=:updated
        WHERE workspace_id=:ws AND id=:id
        """,
        {
            "status": status,
            "updated": utcnow(),
            "ws": workspace_id,
            "id": feature_set_id,
        },
    )
    record_event(
        "feature_store.status_changed",
        user_id=None if actor_id.startswith("__local") else actor_id,
        workspace_id=None if workspace_id == "__local__" else workspace_id,
        resource_type="feature_set",
        resource_id=feature_set_id,
        payload={"from": current["status"], "to": status},
    )
    return get_feature_set(workspace_id, feature_set_id)


def materialize_feature_set(
    actor_id: str,
    workspace_id: str,
    feature_set_id: str,
    *,
    source_dataset_id: str | None = None,
) -> dict[str, Any]:
    feature_set = get_feature_set(workspace_id, feature_set_id)
    source_id = source_dataset_id or feature_set["source_dataset_id"]
    frame = load_dataframe(source_id)
    meta = get_meta(source_id)

    columns = (
        list(feature_set["entity_keys"])
        + ([feature_set["event_time_column"]] if feature_set.get("event_time_column") else [])
        + [item["name"] for item in feature_set["features"]]
    )
    columns = list(dict.fromkeys(columns))
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Feature contract cassé; colonnes absentes: {missing}")

    current_schema = _schema_for_frame(frame, columns)
    current_hash = _schema_hash(current_schema)
    if current_hash != feature_set["schema_sha256"]:
        raise ValueError(
            "Le schéma du dataset courant ne correspond plus au Feature Set. "
            "Créez une nouvelle version du Feature Set."
        )

    materialized = frame[columns].copy()
    dataset = save_dataframe_source(
        materialized,
        f"feature_set_{feature_set['name']}.csv",
        {
            "type": "feature_store_materialization",
            "feature_set_id": feature_set_id,
            "workspace_id": workspace_id,
            "source_dataset_id": source_id,
            "source_dataset_version": int(meta.get("version", 1)),
            "schema_sha256": current_hash,
        },
    )
    if workspace_id != "__local__":
        try:
            from app.services.workspace_service import bind_dataset
            bind_dataset(actor_id, workspace_id, dataset["id"])
        except PermissionError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Impossible de lier la matérialisation au workspace: {exc}"
            ) from exc

    materialization_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """
        INSERT INTO feature_materializations(
          id,workspace_id,feature_set_id,source_dataset_id,source_dataset_version,
          materialized_dataset_id,row_count,schema_sha256,created_by,created_at
        ) VALUES(
          :id,:ws,:feature_set,:source,:version,:materialized,:rows,:sha,:actor,:created
        )
        """,
        {
            "id": materialization_id,
            "ws": workspace_id,
            "feature_set": feature_set_id,
            "source": source_id,
            "version": int(meta.get("version", 1)),
            "materialized": dataset["id"],
            "rows": int(len(materialized)),
            "sha": current_hash,
            "actor": actor_id,
            "created": now,
        },
    )
    return {
        "id": materialization_id,
        "feature_set_id": feature_set_id,
        "source_dataset_id": source_id,
        "source_dataset_version": int(meta.get("version", 1)),
        "materialized_dataset_id": dataset["id"],
        "row_count": int(len(materialized)),
        "schema_sha256": current_hash,
        "created_at": now,
        "dataset": dataset,
    }


def model_feature_contract(model_id: str) -> dict[str, Any]:
    card = get_model_card(model_id)
    dataset_id = str((card.get("dataset") or {}).get("id") or "")
    if not dataset_id:
        raise ValueError("La Model Card ne référence aucun dataset d'entraînement.")
    frame = load_dataframe(dataset_id)
    features = [str(name) for name in card.get("features") or []]
    if not features:
        raise ValueError("La Model Card ne contient aucune feature.")
    missing = [name for name in features if name not in frame.columns]
    if missing:
        raise ValueError(f"Features absentes du dataset d'entraînement: {missing}")
    schema = _schema_for_frame(frame, features)
    return {
        "model_id": model_id,
        "reference_dataset_id": dataset_id,
        "features": features,
        "schema": schema,
        "schema_sha256": _schema_hash(schema),
        "policy": {
            "missing_features": "reject",
            "extra_features": "ignored_but_reported",
            "numeric_non_convertible": "reject",
        },
    }


def validate_serving_rows(
    model_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("Aucune observation fournie.")
    if len(rows) > 5000:
        raise ValueError("Maximum 5 000 observations par requête de serving.")
    contract = model_feature_contract(model_id)
    required = contract["features"]
    schema_by_name = {item["name"]: item for item in contract["schema"]}
    errors: list[dict[str, Any]] = []
    extras: set[str] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append({"row": index, "code": "row_not_object"})
            continue
        missing = [name for name in required if name not in row]
        if missing:
            errors.append(
                {"row": index, "code": "missing_features", "features": missing}
            )
        extras.update(set(row) - set(required))
        for name in required:
            if name not in row or row[name] is None:
                continue
            spec = schema_by_name[name]
            if spec["family"] == "numeric":
                try:
                    float(row[name])
                except (TypeError, ValueError):
                    errors.append(
                        {
                            "row": index,
                            "code": "numeric_non_convertible",
                            "feature": name,
                        }
                    )

    return {
        "valid": not errors,
        "errors": errors[:100],
        "extra_features": sorted(extras),
        "contract": contract,
    }
