from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services.cdc_ingestion import canonicalize_cdc_event, cdc_status, ingest_cdc_events
from app.services.connector_backends import CONNECTOR_SPECS, _object_frame_from_bytes, normalize_connector_payload
from app.services.connector_service import create_connector, create_source
from app.services.storage import load_dataframe_raw


def _use_isolated_store(tmp_path: Path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()
    monkeypatch.setattr("app.services.workspace_service.bind_dataset", lambda *args, **kwargs: None)


def test_object_storage_catalog_and_normalization():
    assert {"s3", "gcs", "azure_blob"}.issubset(CONNECTOR_SPECS)
    s3 = normalize_connector_payload(
        connector_type="s3", host="https://minio.internal", port=None,
        database="analytics", username="AKIA", password="secret",
        options={"region": "eu-west-1", "prefix": "exports/"},
    )
    assert s3["database"] == "analytics"
    assert s3["host"] == "https://minio.internal"
    gcs = normalize_connector_payload(
        connector_type="gcs", host="", port=None, database="bucket",
        username="", password="", options={"prefix": "daily/"},
    )
    assert gcs["connector_type"] == "gcs"


def test_object_frame_formats_are_bounded_and_readable():
    frame = _object_frame_from_bytes(
        b"id,amount\n1,10\n2,20\n", "exports/sales.csv",
        {"source_options": {"format": "csv", "max_object_mb": 1}},
    )
    assert list(frame.columns) == ["id", "amount"]
    assert frame["amount"].sum() == 30


def test_debezium_event_is_normalized_deterministically():
    raw = {
        "payload": {
            "before": None,
            "after": {"id": 7, "amount": 42},
            "op": "c",
            "source": {"db": "sales", "table": "orders", "lsn": "16/B374D848", "ts_ms": 1710000000000},
            "ts_ms": 1710000000000,
        }
    }
    a = canonicalize_cdc_event(raw, event_format="debezium-json")
    b = canonicalize_cdc_event(raw, event_format="debezium-json")
    assert a == b
    assert a["op"] == "upsert"
    assert a["offset"] == "16/B374D848"
    assert len(a["event_id"]) == 64


def test_cdc_checkpoint_dedup_resume_and_immutable_materialization(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    connector = create_connector(
        "user-1", "workspace-1", name="Postgres CDC", connector_type="postgresql",
        host="db.internal", database="sales", username="reader", password="secret",
    )
    source = create_source(
        "user-1", "workspace-1", connector_id=connector["id"], name="Orders CDC",
        source_kind="table", table_name="public.orders", refresh_mode="cdc",
        schema_drift_policy="warn", source_options={"primary_key": ["id"]},
    )

    first = ingest_cdc_events(
        "workspace-1", source["id"], actor_id="user-1", event_format="canonical",
        events=[
            {"event_id": "e1", "partition": "p0", "offset": 1, "op": "c", "after": {"id": 1, "amount": 10}},
            {"event_id": "e2", "partition": "p0", "offset": 2, "op": "c", "after": {"id": 2, "amount": 20}},
        ],
    )
    assert first["events_applied"] == 2
    assert first["duplicates"] == 0
    first_dataset = first["dataset_id"]
    frame = load_dataframe_raw(first_dataset)
    assert frame.to_dict(orient="records") == [{"id": 1, "amount": 10}, {"id": 2, "amount": 20}]

    second_events = [
        {"event_id": "e3", "partition": "p0", "offset": 3, "op": "u", "before": {"id": 1, "amount": 10}, "after": {"id": 1, "amount": 25}},
        {"event_id": "e4", "partition": "p0", "offset": 4, "op": "d", "before": {"id": 2, "amount": 20}},
    ]
    second = ingest_cdc_events("workspace-1", source["id"], actor_id="user-1", event_format="canonical", events=second_events)
    assert second["dataset_id"] != first_dataset
    assert load_dataframe_raw(second["dataset_id"]).to_dict(orient="records") == [{"id": 1, "amount": 25}]

    replay = ingest_cdc_events("workspace-1", source["id"], actor_id="user-1", event_format="canonical", events=second_events)
    assert replay["idempotent"] is True
    assert replay["dataset_id"] == second["dataset_id"]

    stale = ingest_cdc_events(
        "workspace-1", source["id"], actor_id="user-1", event_format="canonical",
        events=[{"event_id": "late-new-id", "partition": "p0", "offset": 2, "op": "u", "after": {"id": 1, "amount": 999}}],
    )
    assert stale["events_applied"] == 0
    assert stale["stale_events"] == 1
    assert stale["dataset_id"] == second["dataset_id"]

    status = cdc_status("workspace-1", source["id"])
    assert status["checkpoints"][0]["offset_value"] == "4"
    assert status["events_applied_total"] == 4


def test_cdc_dry_run_does_not_advance_checkpoint(tmp_path, monkeypatch):
    _use_isolated_store(tmp_path, monkeypatch)
    connector = create_connector(
        "user-1", "workspace-1", name="Mongo CDC", connector_type="mongodb",
        host="mongo.internal", database="analytics", username="reader", password="secret",
    )
    source = create_source(
        "user-1", "workspace-1", connector_id=connector["id"], name="Events",
        source_kind="collection", table_name="events", refresh_mode="cdc",
        source_options={"primary_key": ["id"]},
    )
    preview = ingest_cdc_events(
        "workspace-1", source["id"], actor_id="user-1", event_format="canonical", dry_run=True,
        events=[{"event_id": "x1", "partition": "0", "offset": 10, "op": "c", "after": {"id": "a", "value": 1}}],
    )
    assert preview["dry_run"] is True
    assert preview["rows_after"] == 1
    assert cdc_status("workspace-1", source["id"])["checkpoints"] == []
