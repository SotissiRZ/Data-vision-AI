from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import numpy as np
import pandas as pd

from app.services.audit_service import record_event
from app.services.feature_store import (
    model_feature_contract,
    validate_serving_rows,
)
from app.services.metadata_store import (
    execute,
    fetch_all,
    fetch_one,
    json_dumps,
    json_loads,
    utcnow,
)
from app.services.model_registry import (
    get_registry_entry,
    transition_model,
)
from app.services.modeling import predict
from app.services.storage import (
    get_meta,
    load_dataframe,
    save_dataframe_version,
)

STRATEGIES = {"champion", "shadow", "canary"}
DEPLOYMENT_STATUSES = {"active", "inactive"}


def _hydrate(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["traffic_percent"] = float(item.get("traffic_percent") or 0.0)
    item["revision_no"] = int(item.get("revision_no") or 1)
    item["feature_contract"] = json_loads(
        item.pop("feature_contract_json", "{}"),
        {},
    )
    return item


def _deployment_config(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "endpoint_key": item["endpoint_key"],
        "model_key": item["model_key"],
        "primary_model_id": item["primary_model_id"],
        "secondary_model_id": item.get("secondary_model_id"),
        "strategy": item["strategy"],
        "traffic_percent": float(item.get("traffic_percent") or 0.0),
        "status": item["status"],
        "feature_contract": item.get("feature_contract") or {},
    }


def _snapshot_revision(
    actor_id: str,
    workspace_id: str,
    deployment: dict[str, Any],
    *,
    reason: str,
) -> None:
    execute(
        """
        INSERT INTO model_deployment_revisions(
          id,workspace_id,deployment_id,revision_no,config_json,reason,
          created_by,created_at
        ) VALUES(
          :id,:ws,:deployment,:revision,:config,:reason,:actor,:created
        )
        """,
        {
            "id": str(uuid.uuid4()),
            "ws": workspace_id,
            "deployment": deployment["id"],
            "revision": int(deployment["revision_no"]),
            "config": json_dumps(_deployment_config(deployment)),
            "reason": reason[:1000],
            "actor": actor_id,
            "created": utcnow(),
        },
    )


def _validate_models(
    workspace_id: str,
    primary_model_id: str,
    secondary_model_id: str | None,
    strategy: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    primary = get_registry_entry(workspace_id, primary_model_id)
    if primary.get("stage") != "production" or primary.get("role") != "champion":
        raise ValueError(
            "Le modèle primaire doit être le champion en production."
        )
    if (primary.get("integrity") or {}).get("status") != "ok":
        raise ValueError("L'intégrité de l'artefact primaire n'est pas valide.")

    secondary = None
    if strategy in {"shadow", "canary"}:
        if not secondary_model_id:
            raise ValueError(
                f"Un modèle secondaire est requis pour la stratégie {strategy}."
            )
        secondary = get_registry_entry(workspace_id, secondary_model_id)
        if secondary.get("model_key") != primary.get("model_key"):
            raise ValueError(
                "Le challenger doit appartenir à la même famille de modèles."
            )
        if secondary.get("stage") not in {"staging", "production"}:
            raise ValueError(
                "Le modèle secondaire doit être en staging ou production."
            )
        if (secondary.get("integrity") or {}).get("status") != "ok":
            raise ValueError(
                "L'intégrité de l'artefact secondaire n'est pas valide."
            )
    return primary, secondary


def create_deployment(
    actor_id: str,
    workspace_id: str,
    *,
    name: str,
    endpoint_key: str,
    primary_model_id: str,
    strategy: str = "champion",
    secondary_model_id: str | None = None,
    traffic_percent: float = 0.0,
    status: str = "active",
) -> dict[str, Any]:
    if strategy not in STRATEGIES:
        raise ValueError("Stratégie de deployment invalide.")
    if status not in DEPLOYMENT_STATUSES:
        raise ValueError("Statut de deployment invalide.")
    clean_key = endpoint_key.strip().lower()
    if not clean_key or not all(ch.isalnum() or ch in "-_" for ch in clean_key):
        raise ValueError(
            "endpoint_key doit contenir uniquement lettres, chiffres, '-' ou '_'."
        )
    traffic = max(0.0, min(float(traffic_percent), 100.0))
    if strategy != "canary":
        traffic = 0.0

    primary, _secondary = _validate_models(
        workspace_id,
        primary_model_id,
        secondary_model_id,
        strategy,
    )
    contract = model_feature_contract(primary_model_id)
    deployment_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """
        INSERT INTO model_deployments(
          id,workspace_id,endpoint_key,name,model_key,primary_model_id,
          secondary_model_id,strategy,traffic_percent,status,
          feature_contract_json,revision_no,created_by,created_at,
          updated_by,updated_at
        ) VALUES(
          :id,:ws,:endpoint,:name,:key,:primary,:secondary,:strategy,
          :traffic,:status,:contract,1,:actor,:created,:actor,:updated
        )
        """,
        {
            "id": deployment_id,
            "ws": workspace_id,
            "endpoint": clean_key,
            "name": name.strip()[:240] or clean_key,
            "key": primary["model_key"],
            "primary": primary_model_id,
            "secondary": secondary_model_id,
            "strategy": strategy,
            "traffic": traffic,
            "status": status,
            "contract": json_dumps(contract),
            "actor": actor_id,
            "created": now,
            "updated": now,
        },
    )
    item = get_deployment(workspace_id, deployment_id)
    _snapshot_revision(
        actor_id,
        workspace_id,
        item,
        reason="deployment_created",
    )
    record_event(
        "model_deployment.created",
        user_id=None if actor_id.startswith("__local") else actor_id,
        workspace_id=None if workspace_id == "__local__" else workspace_id,
        resource_type="model_deployment",
        resource_id=deployment_id,
        payload={
            "endpoint_key": clean_key,
            "primary_model_id": primary_model_id,
            "strategy": strategy,
        },
    )
    return get_deployment(workspace_id, deployment_id)


def get_deployment(
    workspace_id: str,
    deployment_id_or_key: str,
) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT * FROM model_deployments
        WHERE workspace_id=:ws AND (id=:value OR endpoint_key=:value)
        """,
        {"ws": workspace_id, "value": deployment_id_or_key},
    )
    if not row:
        raise KeyError("Deployment introuvable.")
    item = _hydrate(row) or {}
    revisions = fetch_all(
        """
        SELECT * FROM model_deployment_revisions
        WHERE workspace_id=:ws AND deployment_id=:id
        ORDER BY revision_no DESC LIMIT 50
        """,
        {"ws": workspace_id, "id": item["id"]},
    )
    for revision in revisions:
        revision["config"] = json_loads(
            revision.pop("config_json", "{}"),
            {},
        )
    item["revisions"] = revisions
    return item


def list_deployments(
    workspace_id: str,
) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT * FROM model_deployments
        WHERE workspace_id=:ws ORDER BY updated_at DESC
        """,
        {"ws": workspace_id},
    )
    return [_hydrate(row) or {} for row in rows]


def update_deployment(
    actor_id: str,
    workspace_id: str,
    deployment_id: str,
    *,
    primary_model_id: str | None = None,
    strategy: str | None = None,
    secondary_model_id: str | None = None,
    traffic_percent: float | None = None,
    status: str | None = None,
    reason: str = "deployment_updated",
) -> dict[str, Any]:
    current = get_deployment(workspace_id, deployment_id)
    next_primary = primary_model_id or current["primary_model_id"]
    next_strategy = strategy or current["strategy"]
    if next_strategy not in STRATEGIES:
        raise ValueError("Stratégie de deployment invalide.")
    next_secondary = (
        secondary_model_id
        if secondary_model_id is not None
        else current.get("secondary_model_id")
    )
    if next_strategy == "champion":
        next_secondary = None
    next_status = status or current["status"]
    if next_status not in DEPLOYMENT_STATUSES:
        raise ValueError("Statut de deployment invalide.")
    next_traffic = (
        float(traffic_percent)
        if traffic_percent is not None
        else float(current.get("traffic_percent") or 0.0)
    )
    next_traffic = max(0.0, min(next_traffic, 100.0))
    if next_strategy != "canary":
        next_traffic = 0.0

    primary_entry, _secondary_entry = _validate_models(
        workspace_id,
        next_primary,
        next_secondary,
        next_strategy,
    )
    if primary_entry["model_key"] != current["model_key"]:
        raise ValueError(
            "Le nouveau champion doit appartenir à la même famille de modèles."
        )
    contract = model_feature_contract(next_primary)

    revision = int(current["revision_no"]) + 1
    execute(
        """
        UPDATE model_deployments
        SET primary_model_id=:primary,secondary_model_id=:secondary,
            strategy=:strategy,traffic_percent=:traffic,status=:status,
            feature_contract_json=:contract,revision_no=:revision,
            updated_by=:actor,updated_at=:updated
        WHERE workspace_id=:ws AND id=:id
        """,
        {
            "primary": next_primary,
            "secondary": next_secondary,
            "strategy": next_strategy,
            "traffic": next_traffic,
            "status": next_status,
            "contract": json_dumps(contract),
            "revision": revision,
            "actor": actor_id,
            "updated": utcnow(),
            "ws": workspace_id,
            "id": current["id"],
        },
    )
    updated = get_deployment(workspace_id, current["id"])
    _snapshot_revision(
        actor_id,
        workspace_id,
        updated,
        reason=reason,
    )
    return updated


def _request_hash(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        rows,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _choose_canary_model(
    request_id: str,
    primary_model_id: str,
    secondary_model_id: str,
    traffic_percent: float,
) -> str:
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 10000 / 100.0
    return (
        secondary_model_id
        if bucket < traffic_percent
        else primary_model_id
    )


def _shadow_summary(
    primary: dict[str, Any],
    shadow: dict[str, Any],
) -> dict[str, Any]:
    p = primary.get("predictions") or []
    s = shadow.get("predictions") or []
    if not p or len(p) != len(s):
        return {"rows_compared": 0}
    classification = bool(
        primary.get("classes") or shadow.get("classes")
    )
    numeric = not classification
    if numeric:
        try:
            p_num = np.asarray(p, dtype=float)
            s_num = np.asarray(s, dtype=float)
        except Exception:
            numeric = False

    if numeric:
        diff = np.abs(p_num - s_num)
        return {
            "rows_compared": len(p),
            "mean_absolute_prediction_difference": round(
                float(np.mean(diff)),
                8,
            ),
            "max_absolute_prediction_difference": round(
                float(np.max(diff)),
                8,
            ),
        }
    disagreements = sum(1 for left, right in zip(p, s) if left != right)
    return {
        "rows_compared": len(p),
        "disagreement_count": disagreements,
        "disagreement_rate": round(disagreements / len(p), 8),
    }


def score_deployment(
    workspace_id: str,
    endpoint_key: str,
    rows: list[dict[str, Any]],
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    deployment = get_deployment(workspace_id, endpoint_key)
    if deployment["status"] != "active":
        raise ValueError("Ce deployment est inactif.")

    validation = validate_serving_rows(
        deployment["primary_model_id"],
        rows,
    )
    if not validation["valid"]:
        raise ValueError(
            "Feature contract invalide: "
            + json.dumps(validation["errors"][:5], ensure_ascii=False)
        )

    normalized_rows = [dict(row) for row in rows]
    schema_by_name = {
        item["name"]: item
        for item in validation["contract"]["schema"]
    }
    for row in normalized_rows:
        for name, spec in schema_by_name.items():
            if name not in row or row[name] is None:
                continue
            if spec["family"] == "numeric":
                row[name] = float(row[name])

    request_id = request_id or str(uuid.uuid4())
    model_used = deployment["primary_model_id"]
    shadow_model_id = None
    shadow_summary = None

    if deployment["strategy"] == "canary":
        secondary = str(deployment.get("secondary_model_id") or "")
        if secondary:
            model_used = _choose_canary_model(
                request_id,
                deployment["primary_model_id"],
                secondary,
                float(deployment["traffic_percent"]),
            )
    result = predict(model_used, normalized_rows)

    if deployment["strategy"] == "shadow":
        shadow_model_id = str(deployment.get("secondary_model_id") or "")
        if shadow_model_id:
            shadow = predict(shadow_model_id, normalized_rows)
            shadow_summary = _shadow_summary(result, shadow)

    latency_ms = (time.perf_counter() - started) * 1000.0
    log_id = str(uuid.uuid4())
    summary = {
        "extra_features": validation["extra_features"],
        "shadow": shadow_summary,
    }
    execute(
        """
        INSERT INTO model_serving_requests(
          id,workspace_id,deployment_id,request_id,model_id,shadow_model_id,
          strategy,row_count,schema_valid,latency_ms,status,request_sha256,
          summary_json,created_at
        ) VALUES(
          :id,:ws,:deployment,:request,:model,:shadow,:strategy,:rows,1,
          :latency,'completed',:sha,:summary,:created
        )
        """,
        {
            "id": log_id,
            "ws": workspace_id,
            "deployment": deployment["id"],
            "request": request_id,
            "model": model_used,
            "shadow": shadow_model_id,
            "strategy": deployment["strategy"],
            "rows": len(rows),
            "latency": round(latency_ms, 3),
            "sha": _request_hash(rows),
            "summary": json_dumps(summary),
            "created": utcnow(),
        },
    )
    return {
        "deployment_id": deployment["id"],
        "endpoint_key": deployment["endpoint_key"],
        "request_id": request_id,
        "strategy": deployment["strategy"],
        "model_used": model_used,
        "predictions": result.get("predictions"),
        "probabilities": result.get("probabilities"),
        "classes": result.get("classes"),
        "feature_contract": {
            "schema_sha256": (
                deployment.get("feature_contract") or {}
            ).get("schema_sha256"),
            "extra_features": validation["extra_features"],
        },
        "shadow": shadow_summary,
        "latency_ms": round(latency_ms, 3),
        "serving_backend": "datavision_internal",
    }


def deployment_metrics(
    workspace_id: str,
    deployment_id: str,
    *,
    limit: int = 500,
) -> dict[str, Any]:
    deployment = get_deployment(workspace_id, deployment_id)
    rows = fetch_all(
        """
        SELECT * FROM model_serving_requests
        WHERE workspace_id=:ws AND deployment_id=:deployment
        ORDER BY created_at DESC LIMIT :limit
        """,
        {
            "ws": workspace_id,
            "deployment": deployment["id"],
            "limit": max(1, min(int(limit), 5000)),
        },
    )
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "deployment": deployment,
        "requests": len(rows),
        "rows_scored": sum(int(row.get("row_count") or 0) for row in rows),
        "mean_latency_ms": (
            None if not latencies else round(float(np.mean(latencies)), 3)
        ),
        "p95_latency_ms": (
            None if not latencies else round(float(np.quantile(latencies, 0.95)), 3)
        ),
        "recent": [
            {
                "request_id": row["request_id"],
                "model_id": row["model_id"],
                "shadow_model_id": row.get("shadow_model_id"),
                "strategy": row["strategy"],
                "row_count": int(row["row_count"]),
                "latency_ms": float(row["latency_ms"]),
                "status": row["status"],
                "summary": json_loads(row.get("summary_json"), {}),
                "created_at": row["created_at"],
            }
            for row in rows[:50]
        ],
    }


def rollback_deployment(
    actor_id: str,
    workspace_id: str,
    deployment_id: str,
) -> dict[str, Any]:
    current = get_deployment(workspace_id, deployment_id)
    revisions = current.get("revisions") or []
    previous = next(
        (
            item
            for item in revisions
            if int(item["revision_no"]) < int(current["revision_no"])
        ),
        None,
    )
    if not previous:
        raise ValueError("Aucune révision précédente disponible.")

    config = previous["config"]
    previous_primary = str(config["primary_model_id"])
    entry = get_registry_entry(workspace_id, previous_primary)

    # Restore Registry consistency before serving the old champion again.
    if entry["stage"] == "retired":
        transition_model(
            actor_id,
            workspace_id,
            previous_primary,
            target_stage="staging",
            note="Rollback deployment: restauration du champion précédent.",
        )
        transition_model(
            actor_id,
            workspace_id,
            previous_primary,
            target_stage="production",
            note="Rollback deployment: restauration du champion précédent.",
        )
    elif entry["stage"] == "staging":
        transition_model(
            actor_id,
            workspace_id,
            previous_primary,
            target_stage="production",
            note="Rollback deployment: promotion du modèle précédent.",
        )
    elif entry["stage"] != "production":
        raise ValueError(
            "Le modèle précédent n'est pas éligible à un rollback gouverné."
        )

    # Secondary models from an old revision may no longer be eligible.
    restored_secondary = config.get("secondary_model_id")
    restored_strategy = config.get("strategy", "champion")
    if restored_secondary:
        try:
            _validate_models(
                workspace_id,
                previous_primary,
                str(restored_secondary),
                restored_strategy,
            )
        except Exception:
            restored_secondary = None
            restored_strategy = "champion"

    revision = int(current["revision_no"]) + 1
    contract = model_feature_contract(previous_primary)
    execute(
        """
        UPDATE model_deployments
        SET primary_model_id=:primary,secondary_model_id=:secondary,
            strategy=:strategy,traffic_percent=:traffic,status='active',
            feature_contract_json=:contract,revision_no=:revision,
            updated_by=:actor,updated_at=:updated
        WHERE workspace_id=:ws AND id=:id
        """,
        {
            "primary": previous_primary,
            "secondary": restored_secondary,
            "strategy": restored_strategy,
            "traffic": (
                float(config.get("traffic_percent") or 0.0)
                if restored_strategy == "canary"
                else 0.0
            ),
            "contract": json_dumps(contract),
            "revision": revision,
            "actor": actor_id,
            "updated": utcnow(),
            "ws": workspace_id,
            "id": current["id"],
        },
    )
    restored = get_deployment(workspace_id, current["id"])
    _snapshot_revision(
        actor_id,
        workspace_id,
        restored,
        reason=f"rollback_from_revision_{current['revision_no']}",
    )
    record_event(
        "model_deployment.rollback",
        user_id=None if actor_id.startswith("__local") else actor_id,
        workspace_id=None if workspace_id == "__local__" else workspace_id,
        resource_type="model_deployment",
        resource_id=current["id"],
        payload={
            "from_revision": current["revision_no"],
            "restored_revision": previous["revision_no"],
            "primary_model_id": previous_primary,
        },
    )
    return restored


def batch_score_dataset(
    actor_id: str,
    workspace_id: str,
    *,
    model_id: str,
    dataset_id: str,
    prediction_column: str = "prediction",
) -> dict[str, Any]:
    registry = get_registry_entry(workspace_id, model_id)
    if registry["stage"] not in {"staging", "production"}:
        raise ValueError(
            "Le batch scoring requiert un modèle staging ou production."
        )
    frame = load_dataframe(dataset_id)
    contract = model_feature_contract(model_id)
    missing = [feature for feature in contract["features"] if feature not in frame.columns]
    if missing:
        raise ValueError(f"Features absentes du dataset: {missing}")
    if len(frame) > 1_000_000:
        raise ValueError(
            "Le batch scoring local est limité à 1 000 000 lignes par job."
        )

    rows = frame[contract["features"]].to_dict(orient="records")
    result = predict(model_id, rows)
    output = frame.copy()
    output[prediction_column] = result["predictions"]

    classes = result.get("classes") or []
    probabilities = result.get("probabilities") or []
    if classes and probabilities:
        matrix = np.asarray(probabilities)
        for index, label in enumerate(classes):
            safe = "".join(
                ch if ch.isalnum() else "_"
                for ch in str(label)
            )[:40]
            output[f"{prediction_column}_proba_{safe}"] = matrix[:, index]

    meta = save_dataframe_version(
        dataset_id,
        output,
        {
            "type": "batch_scoring",
            "label": f"Batch scoring avec modèle {model_id}",
            "model_id": model_id,
            "registry_version": registry["version_no"],
            "feature_contract_sha256": contract["schema_sha256"],
            "prediction_column": prediction_column,
        },
    )
    record_event(
        "model_serving.batch_scored",
        user_id=None if actor_id.startswith("__local") else actor_id,
        workspace_id=None if workspace_id == "__local__" else workspace_id,
        resource_type="dataset",
        resource_id=meta["id"],
        payload={
            "source_dataset_id": dataset_id,
            "model_id": model_id,
            "rows": len(output),
        },
    )
    return {
        "status": "completed",
        "model_id": model_id,
        "source_dataset_id": dataset_id,
        "output_dataset": meta,
        "rows_scored": len(output),
        "prediction_column": prediction_column,
        "serving_backend": "datavision_internal_batch",
    }
