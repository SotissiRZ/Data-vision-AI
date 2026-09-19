from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

from app.core.config import get_settings
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
from app.services.storage import load_dataframe

LOCAL_WORKSPACE = "__local__"
LOCAL_ACTOR = "__local_user__"
STAGES = {"draft", "staging", "production", "retired"}
ROLES = {"candidate", "challenger", "champion", "retired"}
TRANSITIONS = {
    "draft": {"staging", "retired"},
    "staging": {"draft", "production", "retired"},
    "production": {"retired"},
    "retired": {"staging"},
}
HIGHER_IS_BETTER = {
    "accuracy", "balanced_accuracy", "f1", "f1_weighted", "roc_auc", "r2"
}
LOWER_IS_BETTER = {"rmse", "mae"}


def _model_paths(model_id: str) -> tuple[Path, Path]:
    root = get_settings().model_dir
    return root / f"{model_id}.joblib", root / f"{model_id}.card.json"


def _sha256(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path.name)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_key(card: dict[str, Any]) -> str:
    dataset = card.get("dataset") or {}
    root = str(dataset.get("root_id") or dataset.get("id") or "unknown")
    target = str(card.get("target") or "target")
    task = str(card.get("task") or "task")
    return f"{root}:{target}:{task}"


def _artifact_integrity(row: dict[str, Any]) -> dict[str, Any]:
    try:
        model_path, card_path = _model_paths(str(row["model_id"]))
        artifact = _sha256(model_path)
        card = _sha256(card_path)
        return {
            "status": "ok" if artifact == row.get("artifact_sha256") and card == row.get("card_sha256") else "changed",
            "artifact_matches": artifact == row.get("artifact_sha256"),
            "card_matches": card == row.get("card_sha256"),
            "current_artifact_sha256": artifact,
            "current_card_sha256": card,
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def _refresh_registry_hashes(workspace_id: str, model_id: str) -> None:
    model_path, card_path = _model_paths(model_id)
    execute(
        """
        UPDATE model_registry_entries
        SET artifact_sha256=:artifact,card_sha256=:card,updated_at=:updated
        WHERE workspace_id=:ws AND model_id=:model
        """,
        {
            "artifact": _sha256(model_path),
            "card": _sha256(card_path),
            "updated": utcnow(),
            "ws": workspace_id,
            "model": model_id,
        },
    )


def _hydrate_entry(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["version_no"] = int(item.get("version_no") or 0)
    item["card"] = get_model_card(str(item["model_id"]))
    item["integrity"] = _artifact_integrity(item)
    return item


def _event(
    *,
    workspace_id: str,
    registry_id: str,
    model_id: str,
    actor_id: str,
    action: str,
    from_stage: str | None = None,
    to_stage: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    execute(
        """
        INSERT INTO model_registry_events(
          id,workspace_id,registry_id,model_id,action,from_stage,to_stage,
          actor_id,payload_json,created_at
        ) VALUES(
          :id,:ws,:registry,:model,:action,:from_stage,:to_stage,
          :actor,:payload,:created
        )
        """,
        {
            "id": str(uuid.uuid4()),
            "ws": workspace_id,
            "registry": registry_id,
            "model": model_id,
            "action": action,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "actor": actor_id,
            "payload": json_dumps(payload or {}),
            "created": utcnow(),
        },
    )


def register_model(
    actor_id: str,
    workspace_id: str,
    model_id: str,
    *,
    name: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    existing = fetch_one(
        "SELECT * FROM model_registry_entries WHERE workspace_id=:ws AND model_id=:model",
        {"ws": workspace_id, "model": model_id},
    )
    if existing:
        return _hydrate_entry(existing) or {}

    card = get_model_card(model_id)
    model_path, card_path = _model_paths(model_id)
    key = _model_key(card)
    latest = fetch_one(
        "SELECT MAX(version_no) AS n FROM model_registry_entries WHERE workspace_id=:ws AND model_key=:key",
        {"ws": workspace_id, "key": key},
    )
    version_no = int((latest or {}).get("n") or 0) + 1
    registry_id = str(uuid.uuid4())
    now = utcnow()
    label = (name or f"{card.get('target','model')} · {card.get('algorithm','model')}").strip()

    execute(
        """
        INSERT INTO model_registry_entries(
          id,workspace_id,model_id,model_key,version_no,name,stage,role,
          artifact_sha256,card_sha256,registered_by,registered_at,updated_at,
          promoted_at,retired_at,notes
        ) VALUES(
          :id,:ws,:model,:key,:version,:name,'draft','candidate',
          :artifact,:card,:actor,:registered,:updated,NULL,NULL,:notes
        )
        """,
        {
            "id": registry_id,
            "ws": workspace_id,
            "model": model_id,
            "key": key,
            "version": version_no,
            "name": label[:240],
            "artifact": _sha256(model_path),
            "card": _sha256(card_path),
            "actor": actor_id,
            "registered": now,
            "updated": now,
            "notes": notes.strip()[:2000] or None,
        },
    )
    _event(
        workspace_id=workspace_id,
        registry_id=registry_id,
        model_id=model_id,
        actor_id=actor_id,
        action="registered",
        to_stage="draft",
        payload={"version_no": version_no, "model_key": key},
    )
    record_event(
        "model_registry.registered",
        user_id=None if actor_id == LOCAL_ACTOR else actor_id,
        workspace_id=None if workspace_id == LOCAL_WORKSPACE else workspace_id,
        resource_type="model",
        resource_id=model_id,
        payload={"registry_id": registry_id, "model_key": key, "version_no": version_no},
    )
    return get_registry_entry(workspace_id, model_id)


def get_registry_entry(workspace_id: str, model_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM model_registry_entries WHERE workspace_id=:ws AND model_id=:model",
        {"ws": workspace_id, "model": model_id},
    )
    if not row:
        raise KeyError("Modèle non enregistré dans le Model Registry.")
    item = _hydrate_entry(row) or {}
    events = fetch_all(
        "SELECT * FROM model_registry_events WHERE workspace_id=:ws AND model_id=:model ORDER BY created_at DESC LIMIT 100",
        {"ws": workspace_id, "model": model_id},
    )
    for event in events:
        event["payload"] = json_loads(event.pop("payload_json", "{}"), {})
    item["events"] = events
    item["latest_monitoring"] = latest_monitoring_run(workspace_id, model_id)
    item["retraining_policy"] = get_retraining_policy(workspace_id, model_id)
    return item


def list_registry_entries(
    workspace_id: str,
    *,
    dataset_id: str | None = None,
    stage: str | None = None,
    model_key: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["workspace_id=:ws"]
    params: dict[str, Any] = {"ws": workspace_id}
    if stage:
        if stage not in STAGES:
            raise ValueError("Stage invalide.")
        clauses.append("stage=:stage")
        params["stage"] = stage
    if model_key:
        clauses.append("model_key=:key")
        params["key"] = model_key
    rows = fetch_all(
        "SELECT * FROM model_registry_entries WHERE "
        + " AND ".join(clauses)
        + " ORDER BY model_key, version_no DESC",
        params,
    )
    items = [_hydrate_entry(row) or {} for row in rows]
    if dataset_id:
        items = [
            item for item in items
            if str((item.get("card") or {}).get("dataset", {}).get("id")) == str(dataset_id)
            or str((item.get("card") or {}).get("dataset", {}).get("root_id")) == str(dataset_id)
        ]
    return items


def _active_certification(workspace_id: str, model_id: str) -> dict[str, Any] | None:
    if workspace_id == LOCAL_WORKSPACE:
        return None
    row = fetch_one(
        """
        SELECT * FROM resource_certifications
        WHERE workspace_id=:ws AND resource_type='model' AND resource_id=:model
          AND status='active'
        ORDER BY certified_at DESC LIMIT 1
        """,
        {"ws": workspace_id, "model": model_id},
    )
    if not row:
        return None
    valid_until = _parse_time(row.get("valid_until"))
    if valid_until is not None and valid_until.astimezone(timezone.utc) < datetime.now(timezone.utc):
        return None
    return row


def _production_preconditions(workspace_id: str, model_id: str) -> dict[str, Any]:
    card = get_model_card(model_id)
    blockers: list[dict[str, Any]] = []
    responsible = card.get("responsible_ai") or {}
    gate = responsible.get("publication_gate") or {}
    if gate and gate.get("allowed") is False:
        blockers.append({
            "code": "responsible_ai_gate_blocked",
            "detail": gate.get("blockers") or [],
        })
    certification = _active_certification(workspace_id, model_id)
    if workspace_id != LOCAL_WORKSPACE and certification is None:
        blockers.append({
            "code": "active_certification_required",
            "detail": "Une certification active est requise avant la production.",
        })
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "certification": certification,
        "responsible_ai_gate": gate or None,
    }


def transition_model(
    actor_id: str,
    workspace_id: str,
    model_id: str,
    *,
    target_stage: str,
    note: str = "",
) -> dict[str, Any]:
    if target_stage not in STAGES:
        raise ValueError("Stage cible invalide.")
    entry = get_registry_entry(workspace_id, model_id)
    current = str(entry["stage"])
    if target_stage == current:
        return entry
    if target_stage not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Transition interdite: {current} → {target_stage}.")

    # Governance metadata (for example Responsible AI summaries) may legitimately
    # enrich draft/staging artifacts. Snapshot the exact bytes before a governed
    # transition; production artifacts are then expected to remain unchanged.
    if current != "production":
        _refresh_registry_hashes(workspace_id, model_id)
        entry = get_registry_entry(workspace_id, model_id)

    preconditions = None
    if target_stage == "production":
        preconditions = _production_preconditions(workspace_id, model_id)
        if not preconditions["allowed"]:
            codes = ", ".join(item["code"] for item in preconditions["blockers"])
            raise ValueError(f"Promotion en production bloquée: {codes}.")

    now = utcnow()
    role = "candidate"
    promoted_at = entry.get("promoted_at")
    retired_at = entry.get("retired_at")

    if target_stage == "staging":
        role = "challenger"
        retired_at = None
    elif target_stage == "production":
        role = "champion"
        promoted_at = now
        retired_at = None
        # Exactly one champion per model family in a workspace.
        previous = fetch_all(
            """
            SELECT * FROM model_registry_entries
            WHERE workspace_id=:ws AND model_key=:key AND stage='production' AND model_id<>:model
            """,
            {"ws": workspace_id, "key": entry["model_key"], "model": model_id},
        )
        for old in previous:
            execute(
                """
                UPDATE model_registry_entries
                SET stage='retired',role='retired',retired_at=:now,updated_at=:now
                WHERE id=:id
                """,
                {"now": now, "id": old["id"]},
            )
            _event(
                workspace_id=workspace_id,
                registry_id=old["id"],
                model_id=old["model_id"],
                actor_id=actor_id,
                action="replaced_by_champion",
                from_stage="production",
                to_stage="retired",
                payload={"replacement_model_id": model_id},
            )
    elif target_stage == "retired":
        role = "retired"
        retired_at = now
    elif target_stage == "draft":
        role = "candidate"
        retired_at = None

    execute(
        """
        UPDATE model_registry_entries
        SET stage=:stage,role=:role,promoted_at=:promoted,retired_at=:retired,
            updated_at=:updated,notes=:notes
        WHERE workspace_id=:ws AND model_id=:model
        """,
        {
            "stage": target_stage,
            "role": role,
            "promoted": promoted_at,
            "retired": retired_at,
            "updated": now,
            "notes": note.strip()[:2000] or entry.get("notes"),
            "ws": workspace_id,
            "model": model_id,
        },
    )
    _event(
        workspace_id=workspace_id,
        registry_id=entry["id"],
        model_id=model_id,
        actor_id=actor_id,
        action="transition",
        from_stage=current,
        to_stage=target_stage,
        payload={"note": note[:1000], "preconditions": preconditions},
    )
    record_event(
        "model_registry.transition",
        user_id=None if actor_id == LOCAL_ACTOR else actor_id,
        workspace_id=None if workspace_id == LOCAL_WORKSPACE else workspace_id,
        resource_type="model",
        resource_id=model_id,
        payload={"from": current, "to": target_stage, "role": role},
    )
    return get_registry_entry(workspace_id, model_id)


def _load_payload(model_id: str) -> dict[str, Any]:
    model_path, _ = _model_paths(model_id)
    if not model_path.exists():
        raise FileNotFoundError(model_id)
    return joblib.load(model_path)


def _numeric_drift(reference: pd.Series, current: pd.Series) -> dict[str, Any] | None:
    left = pd.to_numeric(reference, errors="coerce").dropna()
    right = pd.to_numeric(current, errors="coerce").dropna()
    if len(left) < 3 or len(right) < 3:
        return None
    b = float(left.mean())
    c = float(right.mean())
    pooled = math.sqrt(max((float(left.var(ddof=1)) + float(right.var(ddof=1))) / 2.0, 0.0))
    score = abs(c - b) / pooled if pooled > 1e-12 else (0.0 if abs(c-b) <= 1e-12 else 1.0)
    return {
        "type": "numeric",
        "reference_mean": round(b, 8),
        "current_mean": round(c, 8),
        "standardized_shift": round(float(score), 8),
        "score": round(float(score), 8),
    }


def _categorical_drift(reference: pd.Series, current: pd.Series) -> dict[str, Any] | None:
    left = reference.fillna("__MISSING__").astype(str).value_counts(normalize=True)
    right = current.fillna("__MISSING__").astype(str).value_counts(normalize=True)
    cats = set(left.index) | set(right.index)
    if not cats:
        return None
    tvd = 0.5 * sum(abs(float(right.get(cat, 0.0)) - float(left.get(cat, 0.0))) for cat in cats)
    return {"type": "categorical", "tvd": round(float(tvd), 8), "score": round(float(tvd), 8)}


def _performance(payload: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any] | None:
    target = str(payload.get("target"))
    features = list(payload.get("features") or [])
    if target not in frame.columns or any(feature not in frame.columns for feature in features):
        return None
    work = frame.dropna(subset=[target]).copy()
    if len(work) < 10:
        return None
    X = work[features]
    y = work[target]
    pipe = payload["pipeline"]
    pred = pipe.predict(X)
    task = payload.get("task")
    if task == "classification":
        metrics: dict[str, float] = {
            "accuracy": float(accuracy_score(y, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "f1_weighted": float(f1_score(y, pred, average="weighted", zero_division=0)),
        }
        if hasattr(pipe, "predict_proba"):
            probs = np.asarray(pipe.predict_proba(X), dtype=float)
            classes = list(getattr(pipe, "classes_", []))
            if len(classes) == 2:
                positive = classes[1]
                y_bin = (pd.Series(y).to_numpy() == positive).astype(int)
                try:
                    metrics["roc_auc"] = float(roc_auc_score(y_bin, probs[:, 1]))
                except Exception:
                    pass
    else:
        metrics = {
            "mae": float(mean_absolute_error(y, pred)),
            "rmse": float(mean_squared_error(y, pred) ** 0.5),
            "r2": float(r2_score(y, pred)),
        }
    return {"rows": len(work), "metrics": {key: round(value, 8) for key, value in metrics.items()}}


def _relative_degradation(metric: str, baseline: float, current: float) -> float:
    denominator = max(abs(float(baseline)), 1e-9)
    if metric in LOWER_IS_BETTER:
        return max(0.0, (float(current) - float(baseline)) / denominator)
    return max(0.0, (float(baseline) - float(current)) / denominator)


def monitor_model(
    actor_id: str,
    workspace_id: str,
    model_id: str,
    *,
    current_dataset_id: str,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = get_registry_entry(workspace_id, model_id)
    payload = _load_payload(model_id)
    card = payload.get("model_card") or get_model_card(model_id)
    reference_dataset_id = str((card.get("dataset") or {}).get("id") or "")
    if not reference_dataset_id:
        raise ValueError("La Model Card ne référence aucun dataset d'entraînement.")
    reference = load_dataframe(reference_dataset_id)
    current = load_dataframe(current_dataset_id)
    features = list(payload.get("features") or [])
    missing_current = [feature for feature in features if feature not in current.columns]
    if missing_current:
        raise ValueError(f"Variables requises absentes du dataset courant: {missing_current}")

    drifts: list[dict[str, Any]] = []
    for feature in features:
        if feature not in reference.columns:
            continue
        if pd.api.types.is_numeric_dtype(reference[feature]):
            item = _numeric_drift(reference[feature], current[feature])
        else:
            item = _categorical_drift(reference[feature], current[feature])
        if item:
            drifts.append({"feature": feature, **item})
    drifts.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)

    current_performance = _performance(payload, current)
    primary = str(card.get("primary_metric") or "")
    baseline_metrics = card.get("metrics_final_test") or {}
    baseline_value = baseline_metrics.get(primary)
    current_value = (
        (current_performance or {}).get("metrics", {}).get(primary)
        if current_performance
        else None
    )
    relative_metric_degradation = None
    if baseline_value is not None and current_value is not None:
        relative_metric_degradation = _relative_degradation(primary, float(baseline_value), float(current_value))

    effective_policy = {
        "max_relative_metric_degradation": 0.10,
        "max_feature_drift_score": 0.25,
        "min_labeled_rows": 30,
        **(policy or {}),
    }
    effective_policy["max_relative_metric_degradation"] = max(
        0.0, float(effective_policy["max_relative_metric_degradation"])
    )
    effective_policy["max_feature_drift_score"] = max(
        0.0, float(effective_policy["max_feature_drift_score"])
    )
    effective_policy["min_labeled_rows"] = max(
        1, int(effective_policy["min_labeled_rows"])
    )
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    integrity = entry.get("integrity") or {}
    if entry.get("stage") == "production" and integrity.get("status") != "ok":
        blockers.append({
            "code": "production_artifact_integrity_changed",
            "value": integrity.get("status"),
            "threshold": "immutable production artifact",
        })
    max_drift = max((float(item.get("score") or 0.0) for item in drifts), default=0.0)
    if max_drift > float(effective_policy["max_feature_drift_score"]):
        blockers.append({
            "code": "feature_drift_exceeded",
            "value": round(max_drift, 8),
            "threshold": float(effective_policy["max_feature_drift_score"]),
        })
    if relative_metric_degradation is not None:
        if relative_metric_degradation > float(effective_policy["max_relative_metric_degradation"]):
            blockers.append({
                "code": "performance_degradation_exceeded",
                "value": round(relative_metric_degradation, 8),
                "threshold": float(effective_policy["max_relative_metric_degradation"]),
            })
    elif current_performance is None:
        warnings.append({"code": "labels_unavailable", "message": "Performance non calculée: cible absente ou insuffisamment renseignée."})
    elif int(current_performance.get("rows") or 0) < int(effective_policy["min_labeled_rows"]):
        warnings.append({"code": "limited_labeled_rows", "rows": current_performance.get("rows")})

    status = "degraded" if blockers else "healthy"
    degradation = {
        "detected": bool(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "primary_metric": primary,
        "baseline_metric": baseline_value,
        "current_metric": current_value,
        "relative_metric_degradation": (
            None if relative_metric_degradation is None else round(relative_metric_degradation, 8)
        ),
        "max_feature_drift_score": round(max_drift, 8),
    }
    run_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """
        INSERT INTO model_monitoring_runs(
          id,workspace_id,model_id,registry_id,reference_dataset_id,current_dataset_id,
          status,rows_evaluated,performance_json,drift_json,policy_json,degradation_json,
          created_by,created_at
        ) VALUES(
          :id,:ws,:model,:registry,:reference,:current,:status,:rows,
          :performance,:drift,:policy,:degradation,:actor,:created
        )
        """,
        {
            "id": run_id,
            "ws": workspace_id,
            "model": model_id,
            "registry": entry["id"],
            "reference": reference_dataset_id,
            "current": current_dataset_id,
            "status": status,
            "rows": int((current_performance or {}).get("rows") or len(current)),
            "performance": json_dumps(current_performance or {}),
            "drift": json_dumps({"features": drifts, "max_score": max_drift}),
            "policy": json_dumps(effective_policy),
            "degradation": json_dumps(degradation),
            "actor": actor_id,
            "created": now,
        },
    )
    record_event(
        "model_monitoring.completed",
        user_id=None if actor_id == LOCAL_ACTOR else actor_id,
        workspace_id=None if workspace_id == LOCAL_WORKSPACE else workspace_id,
        resource_type="model",
        resource_id=model_id,
        outcome="warning" if blockers else "success",
        payload={"monitoring_run_id": run_id, "status": status, "current_dataset_id": current_dataset_id},
    )
    return get_monitoring_run(workspace_id, run_id)


def _hydrate_monitor(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["performance"] = json_loads(item.pop("performance_json", "{}"), {})
    item["drift"] = json_loads(item.pop("drift_json", "{}"), {})
    item["policy"] = json_loads(item.pop("policy_json", "{}"), {})
    item["degradation"] = json_loads(item.pop("degradation_json", "{}"), {})
    return item


def get_monitoring_run(workspace_id: str, run_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM model_monitoring_runs WHERE workspace_id=:ws AND id=:id",
        {"ws": workspace_id, "id": run_id},
    )
    if not row:
        raise KeyError("Run de monitoring introuvable.")
    return _hydrate_monitor(row) or {}


def list_monitoring_runs(workspace_id: str, model_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT * FROM model_monitoring_runs
        WHERE workspace_id=:ws AND model_id=:model
        ORDER BY created_at DESC LIMIT :limit
        """,
        {"ws": workspace_id, "model": model_id, "limit": max(1, min(int(limit), 500))},
    )
    return [_hydrate_monitor(row) or {} for row in rows]


def latest_monitoring_run(workspace_id: str, model_id: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT * FROM model_monitoring_runs
        WHERE workspace_id=:ws AND model_id=:model
        ORDER BY created_at DESC LIMIT 1
        """,
        {"ws": workspace_id, "model": model_id},
    )
    return _hydrate_monitor(row)


def get_retraining_policy(workspace_id: str, model_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM model_retraining_policies WHERE workspace_id=:ws AND model_id=:model",
        {"ws": workspace_id, "model": model_id},
    )
    if not row:
        return {
            "workspace_id": workspace_id,
            "model_id": model_id,
            "enabled": False,
            "min_rows": 100,
            "metric_degradation_threshold": 0.15,
            "feature_drift_threshold": 0.35,
            "cooldown_hours": 168,
            "auto_create_request": True,
        }
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["auto_create_request"] = bool(item.get("auto_create_request"))
    return item


def save_retraining_policy(
    actor_id: str,
    workspace_id: str,
    model_id: str,
    *,
    enabled: bool,
    min_rows: int = 100,
    metric_degradation_threshold: float = 0.15,
    feature_drift_threshold: float = 0.35,
    cooldown_hours: int = 168,
    auto_create_request: bool = True,
) -> dict[str, Any]:
    get_registry_entry(workspace_id, model_id)
    if min_rows < 10:
        raise ValueError("min_rows doit être >= 10.")
    if metric_degradation_threshold < 0 or feature_drift_threshold < 0:
        raise ValueError("Les seuils de dégradation doivent être positifs.")
    now = utcnow()
    existing = fetch_one(
        "SELECT model_id FROM model_retraining_policies WHERE workspace_id=:ws AND model_id=:model",
        {"ws": workspace_id, "model": model_id},
    )
    params = {
        "ws": workspace_id,
        "model": model_id,
        "enabled": int(bool(enabled)),
        "min_rows": int(min_rows),
        "metric": float(metric_degradation_threshold),
        "drift": float(feature_drift_threshold),
        "cooldown": max(0, int(cooldown_hours)),
        "auto": int(bool(auto_create_request)),
        "actor": actor_id,
        "updated": now,
    }
    if existing:
        execute(
            """
            UPDATE model_retraining_policies
            SET enabled=:enabled,min_rows=:min_rows,
                metric_degradation_threshold=:metric,
                feature_drift_threshold=:drift,cooldown_hours=:cooldown,
                auto_create_request=:auto,updated_by=:actor,updated_at=:updated
            WHERE workspace_id=:ws AND model_id=:model
            """,
            params,
        )
    else:
        execute(
            """
            INSERT INTO model_retraining_policies(
              workspace_id,model_id,enabled,min_rows,metric_degradation_threshold,
              feature_drift_threshold,cooldown_hours,auto_create_request,updated_by,updated_at
            ) VALUES(
              :ws,:model,:enabled,:min_rows,:metric,:drift,:cooldown,:auto,:actor,:updated
            )
            """,
            params,
        )
    return get_retraining_policy(workspace_id, model_id)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def list_retraining_requests(workspace_id: str, model_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT * FROM model_retraining_requests
        WHERE workspace_id=:ws AND model_id=:model
        ORDER BY requested_at DESC LIMIT 100
        """,
        {"ws": workspace_id, "model": model_id},
    )
    for row in rows:
        row["reasons"] = json_loads(row.pop("reasons_json", "[]"), [])
    return rows


def check_retraining(
    actor_id: str,
    workspace_id: str,
    model_id: str,
    *,
    create_request: bool = True,
) -> dict[str, Any]:
    entry = get_registry_entry(workspace_id, model_id)
    policy = get_retraining_policy(workspace_id, model_id)
    latest = latest_monitoring_run(workspace_id, model_id)
    reasons: list[dict[str, Any]] = []
    if not policy.get("enabled"):
        return {
            "model_id": model_id,
            "enabled": False,
            "retraining_recommended": False,
            "reasons": [],
            "policy": policy,
            "latest_monitoring": latest,
        }
    if latest is None:
        reasons.append({"code": "monitoring_required", "severity": "info"})
    else:
        eligible_rows = int(latest.get("rows_evaluated") or 0) >= int(policy["min_rows"])
        if not eligible_rows:
            reasons.append({
                "code": "insufficient_monitoring_rows",
                "severity": "info",
                "rows": latest.get("rows_evaluated"),
                "required": policy["min_rows"],
            })
        degradation = latest.get("degradation") or {}
        metric_deg = degradation.get("relative_metric_degradation")
        drift = degradation.get("max_feature_drift_score")
        if eligible_rows and metric_deg is not None and float(metric_deg) >= float(policy["metric_degradation_threshold"]):
            reasons.append({
                "code": "metric_degradation_threshold_exceeded",
                "severity": "high",
                "value": metric_deg,
                "threshold": policy["metric_degradation_threshold"],
            })
        if eligible_rows and drift is not None and float(drift) >= float(policy["feature_drift_threshold"]):
            reasons.append({
                "code": "feature_drift_threshold_exceeded",
                "severity": "high",
                "value": drift,
                "threshold": policy["feature_drift_threshold"],
            })

    recommendation = any(item.get("severity") == "high" for item in reasons)
    requests = list_retraining_requests(workspace_id, model_id)
    cooldown_blocked = False
    if requests and recommendation:
        last = _parse_time(requests[0].get("requested_at"))
        if last is not None:
            now = datetime.now(timezone.utc)
            hours = (now - last.astimezone(timezone.utc)).total_seconds() / 3600.0
            cooldown_blocked = hours < int(policy["cooldown_hours"])

    request_row = None
    if (
        recommendation
        and create_request
        and bool(policy.get("auto_create_request"))
        and not cooldown_blocked
    ):
        request_id = str(uuid.uuid4())
        now = utcnow()
        execute(
            """
            INSERT INTO model_retraining_requests(
              id,workspace_id,model_id,registry_id,source_monitoring_run_id,
              status,reasons_json,requested_by,requested_at,updated_at
            ) VALUES(
              :id,:ws,:model,:registry,:run,'requested',:reasons,:actor,:requested,:updated
            )
            """,
            {
                "id": request_id,
                "ws": workspace_id,
                "model": model_id,
                "registry": entry["id"],
                "run": latest.get("id") if latest else None,
                "reasons": json_dumps(reasons),
                "actor": actor_id,
                "requested": now,
                "updated": now,
            },
        )
        request_row = list_retraining_requests(workspace_id, model_id)[0]
        _event(
            workspace_id=workspace_id,
            registry_id=entry["id"],
            model_id=model_id,
            actor_id=actor_id,
            action="retraining_requested",
            from_stage=entry["stage"],
            to_stage=entry["stage"],
            payload={"request_id": request_id, "reasons": reasons},
        )

    return {
        "model_id": model_id,
        "enabled": True,
        "retraining_recommended": recommendation,
        "cooldown_blocked": cooldown_blocked,
        "request_created": request_row is not None,
        "request": request_row,
        "reasons": reasons,
        "policy": policy,
        "latest_monitoring": latest,
    }


def save_monitor_schedule(
    actor_id: str,
    workspace_id: str,
    model_id: str,
    *,
    current_dataset_id: str,
    enabled: bool,
    interval_minutes: int = 1440,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = get_registry_entry(workspace_id, model_id)
    if enabled and entry.get("stage") not in {"staging", "production"}:
        raise ValueError("Le monitoring périodique ne peut être activé qu'en staging ou production.")
    load_dataframe(current_dataset_id)  # fail early if missing / unauthorized in caller context
    interval = max(15, min(int(interval_minutes), 43200))
    now_dt = datetime.now(timezone.utc)
    next_run = (now_dt + timedelta(minutes=interval)).isoformat() if enabled else None
    existing = fetch_one(
        "SELECT id FROM model_monitor_schedules WHERE workspace_id=:ws AND model_id=:model",
        {"ws": workspace_id, "model": model_id},
    )
    params = {
        "ws": workspace_id,
        "model": model_id,
        "dataset": current_dataset_id,
        "enabled": int(bool(enabled)),
        "interval": interval,
        "policy": json_dumps(policy or {}),
        "next": next_run,
        "actor": actor_id,
        "now": utcnow(),
    }
    if existing:
        execute(
            """
            UPDATE model_monitor_schedules
            SET current_dataset_id=:dataset,enabled=:enabled,interval_minutes=:interval,
                policy_json=:policy,next_run_at=:next,updated_by=:actor,updated_at=:now
            WHERE id=:id
            """,
            {**params, "id": existing["id"]},
        )
    else:
        execute(
            """
            INSERT INTO model_monitor_schedules(
              id,workspace_id,model_id,current_dataset_id,enabled,interval_minutes,
              policy_json,next_run_at,last_enqueued_at,created_by,updated_by,created_at,updated_at
            ) VALUES(
              :id,:ws,:model,:dataset,:enabled,:interval,:policy,:next,NULL,
              :actor,:actor,:now,:now
            )
            """,
            {**params, "id": str(uuid.uuid4())},
        )
    return get_monitor_schedule(workspace_id, model_id) or {}


def get_monitor_schedule(workspace_id: str, model_id: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT * FROM model_monitor_schedules WHERE workspace_id=:ws AND model_id=:model",
        {"ws": workspace_id, "model": model_id},
    )
    if not row:
        return None
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["policy"] = json_loads(item.pop("policy_json", "{}"), {})
    return item


def list_monitor_schedules(workspace_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM model_monitor_schedules WHERE workspace_id=:ws ORDER BY updated_at DESC",
        {"ws": workspace_id},
    )
    result = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item.get("enabled"))
        item["policy"] = json_loads(item.pop("policy_json", "{}"), {})
        result.append(item)
    return result


def claim_due_monitor_schedules(limit: int = 20) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    rows = fetch_all(
        """
        SELECT * FROM model_monitor_schedules
        WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=:now
        ORDER BY next_run_at ASC LIMIT :limit
        """,
        {"now": now_iso, "limit": max(1, min(int(limit), 100))},
    )
    claimed: list[dict[str, Any]] = []
    from app.services.metadata_store import connection
    for row in rows:
        interval = max(15, int(row.get("interval_minutes") or 1440))
        next_run = (now + timedelta(minutes=interval)).isoformat()
        with connection() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE model_monitor_schedules
                    SET next_run_at=:next,last_enqueued_at=:now,updated_at=:now
                    WHERE id=:id AND next_run_at=:expected
                    """
                ),
                {
                    "next": next_run,
                    "now": now_iso,
                    "id": row["id"],
                    "expected": row["next_run_at"],
                },
            )
            if getattr(result, "rowcount", 0) == 1:
                item = dict(row)
                item["policy"] = json_loads(item.pop("policy_json", "{}"), {})
                item["next_run_at"] = next_run
                item["last_enqueued_at"] = now_iso
                claimed.append(item)
    return claimed


def registry_summary(workspace_id: str) -> dict[str, Any]:
    rows = fetch_all(
        "SELECT stage,COUNT(*) AS n FROM model_registry_entries WHERE workspace_id=:ws GROUP BY stage",
        {"ws": workspace_id},
    )
    counts = {str(row["stage"]): int(row["n"]) for row in rows}
    degraded = int((fetch_one(
        "SELECT COUNT(*) AS n FROM model_monitoring_runs WHERE workspace_id=:ws AND status='degraded'",
        {"ws": workspace_id},
    ) or {"n": 0})["n"])
    pending_retraining = int((fetch_one(
        "SELECT COUNT(*) AS n FROM model_retraining_requests WHERE workspace_id=:ws AND status='requested'",
        {"ws": workspace_id},
    ) or {"n": 0})["n"])
    schedules = int((fetch_one(
        "SELECT COUNT(*) AS n FROM model_monitor_schedules WHERE workspace_id=:ws AND enabled=1",
        {"ws": workspace_id},
    ) or {"n": 0})["n"])
    return {
        "workspace_id": workspace_id,
        "total_models": sum(counts.values()),
        "by_stage": {stage: counts.get(stage, 0) for stage in sorted(STAGES)},
        "degraded_monitoring_runs": degraded,
        "pending_retraining_requests": pending_retraining,
        "active_monitor_schedules": schedules,
    }
