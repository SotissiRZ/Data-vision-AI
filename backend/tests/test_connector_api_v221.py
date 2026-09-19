from pathlib import Path

from app.api.routes.enterprise import (
    ConnectorCreateRequest,
    ConnectorSourceCreateRequest,
)


ROOT = Path(__file__).resolve().parents[2]


def test_enterprise_request_accepts_all_connector_types():
    types = [
        "postgresql", "mysql", "mariadb", "sqlite", "sqlserver",
        "oracle", "redshift", "snowflake", "databricks",
        "bigquery", "mongodb",
    ]
    for connector_type in types:
        payload = ConnectorCreateRequest(
            name="x",
            connector_type=connector_type,
            host="host",
            database="db",
            username="user",
            password="secret",
            options={"http_path": "/sql/1.0/warehouses/x"}
            if connector_type == "databricks"
            else {},
        )
        assert payload.connector_type == connector_type


def test_source_request_accepts_collection():
    payload = ConnectorSourceCreateRequest(
        connector_id="c1",
        name="orders",
        source_kind="collection",
        table_name="orders",
    )
    assert payload.source_kind == "collection"


def test_connector_catalog_route_exists():
    routes = (
        ROOT / "backend/app/api/routes/enterprise.py"
    ).read_text()
    assert '/workspaces/{workspace_id}/connectors/catalog' in routes


def test_frontend_exposes_advanced_connectors():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()
    backend = (
        ROOT / "backend/app/services/connector_backends.py"
    ).read_text()

    assert "getConnectorCatalog" in api
    assert "connectorCatalog" in page
    assert "driver absent" in page
    assert "Collection MongoDB" in page
    for token in [
        '"mariadb"',
        '"sqlite"',
        '"sqlserver"',
        '"oracle"',
        '"redshift"',
        '"snowflake"',
        '"databricks"',
        '"bigquery"',
        '"mongodb"',
    ]:
        assert token in backend


def test_assistant_connector_tools_are_bound():
    tools = (
        ROOT / "backend/app/assistant/tools.py"
    ).read_text()
    host = (
        ROOT / "backend/app/assistant/host_v212.py"
    ).read_text()

    assert 'name="list_data_connectors"' in tools
    assert 'name="discover_data_connector"' in tools
    assert 'name="test_data_connector"' in tools
    assert '"list_data_connectors": connectors.list_data_connectors' in host
    assert '"discover_data_connector": connectors.discover_data_connector' in host
    assert '"test_data_connector": connectors.test_data_connector' in host
