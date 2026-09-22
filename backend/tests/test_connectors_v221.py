import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.services.connector_backends import (
    CONNECTOR_SPECS,
    connector_catalog,
    normalize_connector_payload,
)
from app.services.connector_service import (
    create_connector,
    create_source,
    discover_connector,
    get_connector,
    preview_source,
    test_connector as connector_test,
)


def _use_sqlite_metadata(tmp_path, monkeypatch):
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


def _create_sqlite_source_file(tmp_path: Path) -> Path:
    root = tmp_path / "connectors" / "sqlite"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "sales.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE sales (id INTEGER PRIMARY KEY, region TEXT, amount REAL)"
        )
        conn.executemany(
            "INSERT INTO sales(region, amount) VALUES(?,?)",
            [("Nord", 10.0), ("Sud", 20.0), ("Nord", 30.0)],
        )
        conn.commit()
    finally:
        conn.close()
    return path


def test_catalog_contains_all_cdc_connector_families():
    expected = {
        "postgresql",
        "mysql",
        "mariadb",
        "sqlite",
        "sqlserver",
        "oracle",
        "mongodb",
        "bigquery",
        "snowflake",
        "databricks",
        "redshift",
        "s3",
        "gcs",
        "azure_blob",
    }
    assert set(CONNECTOR_SPECS) == expected
    catalog = connector_catalog()
    assert {item["key"] for item in catalog} == expected
    assert all(isinstance(item["driver_available"], bool) for item in catalog)


def test_databricks_requires_http_path():
    try:
        normalize_connector_payload(
            connector_type="databricks",
            host="dbc.example.cloud.databricks.com",
            port=443,
            database="main",
            username="",
            password="token",
            options={},
        )
    except ValueError as exc:
        assert "http_path" in str(exc)
    else:
        raise AssertionError("Databricks without http_path must fail.")


def test_sqlite_is_confined_to_governed_directory(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    outside = tmp_path / "outside.db"
    sqlite3.connect(outside).close()

    try:
        normalize_connector_payload(
            connector_type="sqlite",
            host="",
            port=None,
            database=str(outside),
            username="",
            password="",
            options={},
        )
    except ValueError as exc:
        assert "data/connectors/sqlite" in str(exc)
    else:
        raise AssertionError("SQLite path escape should fail.")


def test_sqlite_connector_end_to_end(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    _create_sqlite_source_file(tmp_path)

    connector = create_connector(
        "user-1",
        "workspace-1",
        name="SQLite Sales",
        connector_type="sqlite",
        database="sales.db",
    )
    assert connector["connector_type"] == "sqlite"
    assert "password" not in connector
    assert connector["database_name"].endswith("sales.db")

    tested = connector_test("workspace-1", connector["id"])
    assert tested["ok"] is True
    assert tested["status"] == "healthy"

    discovered = discover_connector(
        "workspace-1",
        connector["id"],
    )
    names = {item["name"] for item in discovered["tables"]}
    assert "sales" in names

    source = create_source(
        "user-1",
        "workspace-1",
        connector_id=connector["id"],
        name="Sales source",
        source_kind="table",
        table_name="sales",
        refresh_mode="full",
    )
    preview = preview_source(
        "workspace-1",
        source["id"],
        limit=10,
    )
    assert preview["returned_rows"] == 3
    assert preview["columns"] == ["id", "region", "amount"]


def test_bigquery_secret_is_not_returned(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    connector = create_connector(
        "user-1",
        "workspace-1",
        name="BigQuery",
        connector_type="bigquery",
        database="sample-project",
        password='{"type":"service_account","private_key":"secret"}',
        options={"dataset": "analytics"},
    )
    safe = get_connector("workspace-1", connector["id"])
    assert safe["connector_type"] == "bigquery"
    assert "password_ciphertext" not in safe
    assert "password" not in safe
    assert "private_key" not in str(safe)


def test_mongodb_accepts_collection_source_without_network(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    connector = create_connector(
        "user-1",
        "workspace-1",
        name="Mongo",
        connector_type="mongodb",
        host="mongo.internal",
        database="analytics",
        username="reader",
        password="secret",
    )
    source = create_source(
        "user-1",
        "workspace-1",
        connector_id=connector["id"],
        name="Orders",
        source_kind="collection",
        table_name="orders",
        refresh_mode="incremental",
        incremental_column="updated_at",
    )
    assert source["source_kind"] == "collection"
    assert source["table_name"] == "orders"



def test_missing_driver_is_reported_fail_closed(monkeypatch):
    import app.services.connector_backends as backends

    monkeypatch.setattr(
        backends,
        "driver_available",
        lambda connector_type: False
        if connector_type == "oracle"
        else True,
    )
    try:
        backends.require_driver("oracle")
    except RuntimeError as exc:
        assert str(exc).startswith("driver_missing:oracle:")
    else:
        raise AssertionError("Missing driver must fail closed.")
