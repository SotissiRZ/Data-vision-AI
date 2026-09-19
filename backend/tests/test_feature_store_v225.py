from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.services.feature_store import (
    create_feature_set,
    get_feature_set,
    materialize_feature_set,
    model_feature_contract,
    set_feature_set_status,
)
from app.services.modeling import train_model
from app.services.storage import (
    get_meta,
    load_dataframe,
    save_dataframe_source,
)


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


def _frame():
    rows = 40
    x = list(range(1, rows + 1))
    return pd.DataFrame(
        {
            "entity_id": x,
            "event_time": pd.date_range("2026-01-01", periods=rows),
            "x": [float(value) for value in x],
            "segment": ["A" if value % 2 else "B" for value in x],
            "target": [2.0 * value + 1.0 for value in x],
        }
    )


def test_feature_set_materialization_is_immutable_dataset(
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, monkeypatch)
    source = save_dataframe_source(_frame(), "features.csv")

    feature_set = create_feature_set(
        "__local_user__",
        "__local__",
        name="customer_features",
        source_dataset_id=source["id"],
        features=["x", "segment"],
        entity_keys=["entity_id"],
        event_time_column="event_time",
    )
    assert feature_set["status"] == "draft"
    assert [item["name"] for item in feature_set["features"]] == [
        "x",
        "segment",
    ]

    active = set_feature_set_status(
        "__local_user__",
        "__local__",
        feature_set["id"],
        "active",
    )
    assert active["status"] == "active"

    materialized = materialize_feature_set(
        "__local_user__",
        "__local__",
        feature_set["id"],
    )
    snapshot = load_dataframe(materialized["materialized_dataset_id"])
    assert list(snapshot.columns) == [
        "entity_id",
        "event_time",
        "x",
        "segment",
    ]
    assert len(snapshot) == 40
    meta = get_meta(materialized["materialized_dataset_id"])
    assert meta["external_source"]["type"] == "feature_store_materialization"


def test_model_feature_contract_comes_from_training_dataset(
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, monkeypatch)
    frame = _frame()
    source = save_dataframe_source(frame, "train.csv")
    trained = train_model(
        frame,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context={
            "id": source["id"],
            "root_id": source["id"],
            "version": 1,
            "name": "train.csv",
        },
    )
    contract = model_feature_contract(trained.model_id)
    assert contract["features"]
    assert contract["reference_dataset_id"] == source["id"]
    assert len(contract["schema_sha256"]) == 64
    assert all("family" in item for item in contract["schema"])
