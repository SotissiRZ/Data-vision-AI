import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.metadata_store import execute
from app.services.model_registry import (
    LOCAL_ACTOR,
    LOCAL_WORKSPACE,
    check_retraining,
    claim_due_monitor_schedules,
    get_registry_entry,
    list_registry_entries,
    monitor_model,
    register_model,
    save_monitor_schedule,
    save_retraining_policy,
    transition_model,
)
from app.services.modeling import train_model
from app.services.storage import save_upload


def _configure(tmp_path, monkeypatch):
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
    metadata_store.init_metadata_store()


def _frame(rows=140, shift=0.0, noisy=False):
    x = np.linspace(0, 10, rows) + shift
    z = np.sin(x)
    y = 3.0 * x + 2.0 * z + 5.0
    if noisy:
        y = y[::-1]
    return pd.DataFrame({"x": x, "z": z, "target": y})


def _dataset(df: pd.DataFrame, name: str):
    return save_upload(name, df.to_csv(index=False).encode("utf-8"))


def _train(df, meta):
    return train_model(
        df,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={
            "id": meta["id"],
            "root_id": meta["root_id"],
            "version": meta["version"],
            "name": meta["original_name"],
        },
    )


def test_registry_versions_models_with_same_model_key(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    df = _frame()
    meta = _dataset(df, "train.csv")
    first = _train(df, meta)
    second = _train(df, meta)

    r1 = register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, first.model_id)
    r2 = register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, second.model_id)

    assert r1["version_no"] == 1
    assert r2["version_no"] == 2
    assert r1["model_key"] == r2["model_key"]
    assert r1["stage"] == "draft"
    assert r1["integrity"]["status"] == "ok"
    assert len(list_registry_entries(LOCAL_WORKSPACE)) == 2


def test_champion_replacement_retires_previous_production_model(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    df = _frame()
    meta = _dataset(df, "train.csv")
    first = _train(df, meta)
    second = _train(df, meta)
    register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, first.model_id)
    register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, second.model_id)

    transition_model(LOCAL_ACTOR, LOCAL_WORKSPACE, first.model_id, target_stage="staging")
    champion = transition_model(
        LOCAL_ACTOR, LOCAL_WORKSPACE, first.model_id, target_stage="production"
    )
    assert champion["role"] == "champion"

    transition_model(LOCAL_ACTOR, LOCAL_WORKSPACE, second.model_id, target_stage="staging")
    next_champion = transition_model(
        LOCAL_ACTOR, LOCAL_WORKSPACE, second.model_id, target_stage="production"
    )
    old = get_registry_entry(LOCAL_WORKSPACE, first.model_id)

    assert next_champion["stage"] == "production"
    assert next_champion["role"] == "champion"
    assert old["stage"] == "retired"
    assert old["role"] == "retired"


def test_enterprise_production_requires_active_certification(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    df = _frame()
    meta = _dataset(df, "train.csv")
    trained = _train(df, meta)
    register_model("user-1", "ws-1", trained.model_id)
    transition_model("user-1", "ws-1", trained.model_id, target_stage="staging")

    try:
        transition_model("user-1", "ws-1", trained.model_id, target_stage="production")
    except ValueError as exc:
        assert "active_certification_required" in str(exc)
    else:
        raise AssertionError("Enterprise production promotion must require certification")

    now = datetime.now(timezone.utc).isoformat()
    execute(
        """
        INSERT INTO resource_certifications(
          id,workspace_id,dataset_id,resource_type,resource_id,review_id,
          owner_user_id,certified_by,certified_at,valid_until,status,notes
        ) VALUES(
          'cert-1','ws-1',:dataset,'model',:model,'review-1',
          'user-1','user-1',:now,NULL,'active','test'
        )
        """,
        {"dataset": meta["id"], "model": trained.model_id, "now": now},
    )
    promoted = transition_model(
        "user-1", "ws-1", trained.model_id, target_stage="production"
    )
    assert promoted["stage"] == "production"


def test_registry_detects_card_mutation_and_resnapshots_before_staging(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    df = _frame()
    meta = _dataset(df, "train.csv")
    trained = _train(df, meta)
    registered = register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, trained.model_id)
    card_path = get_settings().model_dir / f"{trained.model_id}.card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["governance_note"] = "reviewed"
    card_path.write_text(json.dumps(card), encoding="utf-8")

    changed = get_registry_entry(LOCAL_WORKSPACE, trained.model_id)
    assert changed["integrity"]["status"] == "changed"
    staged = transition_model(
        LOCAL_ACTOR, LOCAL_WORKSPACE, trained.model_id, target_stage="staging"
    )
    assert staged["integrity"]["status"] == "ok"
    assert staged["card_sha256"] != registered["card_sha256"]


def test_monitoring_detects_drift_and_drives_retraining_request(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    reference = _frame(160)
    current = _frame(160, shift=20.0, noisy=True)
    ref_meta = _dataset(reference, "reference.csv")
    cur_meta = _dataset(current, "current.csv")
    trained = _train(reference, ref_meta)
    register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, trained.model_id)

    run = monitor_model(
        LOCAL_ACTOR,
        LOCAL_WORKSPACE,
        trained.model_id,
        current_dataset_id=cur_meta["id"],
        policy={
            "max_relative_metric_degradation": 0.01,
            "max_feature_drift_score": 0.05,
            "min_labeled_rows": 30,
        },
    )
    assert run["status"] == "degraded"
    assert run["degradation"]["detected"] is True
    assert run["degradation"]["max_feature_drift_score"] > 0.05

    save_retraining_policy(
        LOCAL_ACTOR,
        LOCAL_WORKSPACE,
        trained.model_id,
        enabled=True,
        min_rows=50,
        metric_degradation_threshold=0.01,
        feature_drift_threshold=0.05,
        cooldown_hours=24,
        auto_create_request=True,
    )
    check = check_retraining(
        LOCAL_ACTOR,
        LOCAL_WORKSPACE,
        trained.model_id,
        create_request=True,
    )
    assert check["retraining_recommended"] is True
    assert check["request_created"] is True
    assert check["request"]["status"] == "requested"

    again = check_retraining(
        LOCAL_ACTOR,
        LOCAL_WORKSPACE,
        trained.model_id,
        create_request=True,
    )
    assert again["retraining_recommended"] is True
    assert again["cooldown_blocked"] is True
    assert again["request_created"] is False


def test_monitor_schedule_claim_is_atomic(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    df = _frame()
    ref_meta = _dataset(df, "reference.csv")
    cur_meta = _dataset(_frame(140, shift=1.0), "current.csv")
    trained = _train(df, ref_meta)
    register_model(LOCAL_ACTOR, LOCAL_WORKSPACE, trained.model_id)
    transition_model(LOCAL_ACTOR, LOCAL_WORKSPACE, trained.model_id, target_stage="staging")

    schedule = save_monitor_schedule(
        LOCAL_ACTOR,
        LOCAL_WORKSPACE,
        trained.model_id,
        current_dataset_id=cur_meta["id"],
        enabled=True,
        interval_minutes=30,
    )
    due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    execute(
        "UPDATE model_monitor_schedules SET next_run_at=:due WHERE id=:id",
        {"due": due, "id": schedule["id"]},
    )

    claimed = claim_due_monitor_schedules()
    assert len(claimed) == 1
    assert claimed[0]["model_id"] == trained.model_id
    assert claim_due_monitor_schedules() == []
