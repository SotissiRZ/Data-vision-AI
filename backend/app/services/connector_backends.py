from __future__ import annotations

import importlib.util
import io
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from app.core.config import get_settings


@dataclass(frozen=True)
class ConnectorSpec:
    key: str
    label: str
    family: str
    default_port: int
    host_required: bool
    database_required: bool
    username_required: bool
    secret_required: bool
    secret_label: str
    supports_query: bool
    supports_incremental: bool
    driver_module: str | None
    docs_hint: str
    options: tuple[str, ...] = ()


CONNECTOR_SPECS: dict[str, ConnectorSpec] = {
    "postgresql": ConnectorSpec(
        "postgresql", "PostgreSQL", "sql", 5432,
        True, True, True, False, "Mot de passe",
        True, True, "psycopg",
        "Connexion PostgreSQL via psycopg.",
    ),
    "mysql": ConnectorSpec(
        "mysql", "MySQL", "sql", 3306,
        True, True, True, False, "Mot de passe",
        True, True, "pymysql",
        "Connexion MySQL via PyMySQL.",
    ),
    "mariadb": ConnectorSpec(
        "mariadb", "MariaDB", "sql", 3306,
        True, True, True, False, "Mot de passe",
        True, True, "pymysql",
        "MariaDB via le protocole MySQL/PyMySQL.",
    ),
    "sqlite": ConnectorSpec(
        "sqlite", "SQLite", "sql", 0,
        False, True, False, False, "Aucun secret",
        True, True, None,
        "Le fichier doit résider dans data/connectors/sqlite.",
        ("readonly",),
    ),
    "sqlserver": ConnectorSpec(
        "sqlserver", "SQL Server", "sql", 1433,
        True, True, True, False, "Mot de passe",
        True, True, "pymssql",
        "SQL Server via pymssql/FreeTDS.",
    ),
    "oracle": ConnectorSpec(
        "oracle", "Oracle", "sql", 1521,
        True, True, True, False, "Mot de passe",
        True, True, "oracledb",
        "Oracle Database via python-oracledb Thin mode.",
        ("service_name",),
    ),
    "redshift": ConnectorSpec(
        "redshift", "Amazon Redshift", "sql", 5439,
        True, True, True, False, "Mot de passe",
        True, True, "redshift_connector",
        "Amazon Redshift via redshift_connector + SQLAlchemy dialect.",
        ("schema",),
    ),
    "snowflake": ConnectorSpec(
        "snowflake", "Snowflake", "cloud_sql", 443,
        True, True, True, True, "Mot de passe / token",
        True, True, "snowflake.connector",
        "Hôte = account identifier. Options: warehouse, schema, role.",
        ("warehouse", "schema", "role"),
    ),
    "databricks": ConnectorSpec(
        "databricks", "Databricks SQL", "cloud_sql", 443,
        True, False, False, True, "Personal Access Token",
        True, True, "databricks.sql",
        "Hôte = server hostname. Option http_path requise.",
        ("http_path", "catalog", "schema"),
    ),
    "bigquery": ConnectorSpec(
        "bigquery", "Google BigQuery", "cloud_native", 443,
        False, True, False, False, "Service account JSON (optionnel si ADC)",
        True, True, "google.cloud.bigquery",
        "Base = project_id. Le secret peut contenir un JSON de service account.",
        ("dataset", "location"),
    ),
    "mongodb": ConnectorSpec(
        "mongodb", "MongoDB", "document", 27017,
        True, True, False, False, "Mot de passe",
        False, True, "pymongo",
        "Base = database MongoDB. Les sources utilisent des collections.",
        ("auth_source", "replica_set", "tls"),
    ),
    "s3": ConnectorSpec(
        "s3", "S3 / S3-compatible", "object_storage", 0,
        False, True, False, False, "Secret access key (optionnel avec IAM)",
        False, False, "boto3",
        "Base = bucket. Hôte optionnel = endpoint S3-compatible. Username = access key ID.",
        ("region", "session_token", "prefix"),
    ),
    "gcs": ConnectorSpec(
        "gcs", "Google Cloud Storage", "object_storage", 0,
        False, True, False, False, "Service account JSON (optionnel avec ADC)",
        False, False, "google.cloud.storage",
        "Base = bucket GCS. Le secret peut contenir un JSON de service account.",
        ("project_id", "prefix"),
    ),
    "azure_blob": ConnectorSpec(
        "azure_blob", "Azure Blob Storage", "object_storage", 0,
        True, True, False, False, "Account key / SAS (optionnel)",
        False, False, "azure.storage.blob",
        "Hôte = account URL (https://<account>.blob.core.windows.net). Base = container.",
        ("prefix",),
    ),
}


def connector_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in CONNECTOR_SPECS.values():
        item = asdict(spec)
        item["options"] = list(spec.options) + ["retry_attempts", "retry_backoff_seconds"]
        item["driver_available"] = driver_available(spec.key)
        rows.append(item)
    return rows


def driver_available(connector_type: str) -> bool:
    spec = CONNECTOR_SPECS[connector_type]
    if spec.driver_module is None:
        return True
    try:
        return importlib.util.find_spec(spec.driver_module) is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def require_driver(connector_type: str) -> None:
    if not driver_available(connector_type):
        spec = CONNECTOR_SPECS[connector_type]
        raise RuntimeError(
            f"driver_missing:{connector_type}: module {spec.driver_module} non installé"
        )


def normalize_connector_payload(
    *,
    connector_type: str,
    host: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
    options: dict[str, Any] | None,
) -> dict[str, Any]:
    connector_type = connector_type.strip().lower()
    if connector_type not in CONNECTOR_SPECS:
        raise ValueError(f"Connecteur non supporté: {connector_type}")
    spec = CONNECTOR_SPECS[connector_type]
    options = dict(options or {})

    host = (host or "").strip()
    database = (database or "").strip()
    username = (username or "").strip()
    password = password or ""

    if spec.host_required and not host:
        raise ValueError(f"Hôte requis pour {spec.label}.")
    if spec.database_required and not database:
        raise ValueError(f"Base/projet requis pour {spec.label}.")
    if spec.username_required and not username:
        raise ValueError(f"Utilisateur requis pour {spec.label}.")
    if spec.secret_required and not password:
        raise ValueError(f"{spec.secret_label} requis pour {spec.label}.")

    if connector_type == "databricks" and not str(options.get("http_path") or "").strip():
        raise ValueError("options.http_path est requis pour Databricks SQL.")

    if connector_type == "sqlite":
        # Only allow files under DataVision's dedicated SQLite connector directory.
        sqlite_root = (get_settings().data_root / "connectors" / "sqlite").resolve()
        sqlite_root.mkdir(parents=True, exist_ok=True)
        candidate = Path(database)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (sqlite_root / candidate).resolve()
        try:
            resolved.relative_to(sqlite_root)
        except ValueError as exc:
            raise ValueError(
                "Le fichier SQLite doit rester dans data/connectors/sqlite."
            ) from exc
        if not resolved.exists():
            raise ValueError(
                f"Fichier SQLite introuvable: {resolved.name}. "
                "Copiez-le d'abord dans data/connectors/sqlite."
            )
        database = str(resolved)

    return {
        "connector_type": connector_type,
        "host": host,
        "port": int(port or spec.default_port or 0),
        "database": database,
        "username": username,
        "password": password,
        "options": options,
    }


def is_sqlalchemy_connector(connector_type: str) -> bool:
    return connector_type in {
        "postgresql", "mysql", "mariadb", "sqlite",
        "sqlserver", "oracle", "redshift",
    }


def _sqlalchemy_url_and_args(
    connector: dict[str, Any],
) -> tuple[URL, dict[str, Any]]:
    ctype = connector["connector_type"]
    require_driver(ctype)
    options = connector.get("options") or {}
    query: dict[str, str] = {}
    connect_args: dict[str, Any] = {}

    if ctype == "postgresql":
        driver = "postgresql+psycopg"
        connect_args["connect_timeout"] = 5
        if connector.get("ssl_mode") in {"disable", "require"}:
            query["sslmode"] = connector["ssl_mode"]
    elif ctype in {"mysql", "mariadb"}:
        driver = "mysql+pymysql"
        connect_args["connect_timeout"] = 5
        if connector.get("ssl_mode") == "require":
            connect_args["ssl"] = {}
    elif ctype == "sqlite":
        driver = "sqlite+pysqlite"
        url = URL.create(driver, database=connector["database_name"])
        return url, {"check_same_thread": False}
    elif ctype == "sqlserver":
        driver = "mssql+pymssql"
        connect_args["login_timeout"] = 5
    elif ctype == "oracle":
        driver = "oracle+oracledb"
        # Thin mode works without Oracle Client. database_name is treated as service name.
        query["service_name"] = str(
            options.get("service_name") or connector["database_name"]
        )
        url = URL.create(
            driver,
            username=connector["username"],
            password=connector.get("password") or "",
            host=connector["host"],
            port=int(connector["port"]),
            query=query,
        )
        return url, connect_args
    elif ctype == "redshift":
        driver = "redshift+redshift_connector"
        connect_args["timeout"] = 5
    else:
        raise ValueError(f"Connecteur SQLAlchemy non supporté: {ctype}")

    for key, value in (
        options.get("query", {}).items()
        if isinstance(options.get("query"), dict)
        else []
    ):
        query[str(key)] = str(value)

    url = URL.create(
        driver,
        username=connector.get("username") or None,
        password=connector.get("password") or None,
        host=connector.get("host") or None,
        port=int(connector.get("port") or 0) or None,
        database=connector.get("database_name") or None,
        query=query,
    )
    return url, connect_args


def sqlalchemy_engine(connector: dict[str, Any]):
    url, connect_args = _sqlalchemy_url_and_args(connector)
    return create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
    )


def test_sqlalchemy(connector: dict[str, Any]) -> dict[str, Any]:
    engine = sqlalchemy_engine(connector)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True}
    finally:
        engine.dispose()


def discover_sqlalchemy(
    connector: dict[str, Any],
    max_tables: int,
) -> dict[str, Any]:
    engine = sqlalchemy_engine(connector)
    try:
        inspector = inspect(engine)
        try:
            schemas = inspector.get_schema_names()
        except Exception:
            schemas = []
        ignored = {
            "information_schema", "pg_catalog", "pg_toast",
            "mysql", "performance_schema", "sys",
        }
        selected = [schema for schema in schemas if schema not in ignored] or [None]
        tables: list[dict[str, Any]] = []
        for schema in selected[:40]:
            try:
                names = inspector.get_table_names(schema=schema)
            except Exception:
                continue
            for name in names:
                if len(tables) >= max_tables:
                    break
                try:
                    cols = inspector.get_columns(name, schema=schema)
                    columns = [
                        {
                            "name": str(col.get("name")),
                            "type": str(col.get("type")),
                            "nullable": bool(col.get("nullable", True)),
                        }
                        for col in cols
                    ]
                except Exception:
                    columns = []
                tables.append(
                    {
                        "schema": schema,
                        "name": name,
                        "qualified_name": f"{schema}.{name}" if schema else name,
                        "columns": columns,
                        "kind": "table",
                    }
                )
            if len(tables) >= max_tables:
                break
        return {
            "schemas": [schema for schema in selected if schema],
            "tables": tables,
            "truncated": len(tables) >= max_tables,
        }
    finally:
        engine.dispose()


def _quote_qualified(engine, name: str) -> str:
    parts = name.split(".")
    if not parts or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", part)
        for part in parts
    ):
        raise ValueError("Identifiant SQL invalide.")
    prep = engine.dialect.identifier_preparer
    return ".".join(prep.quote(part) for part in parts)


def fetch_sqlalchemy(
    connector: dict[str, Any],
    source: dict[str, Any],
    *,
    watermark: Any = None,
    limit: int | None = None,
) -> pd.DataFrame:
    engine = sqlalchemy_engine(connector)
    try:
        params: dict[str, Any] = {}
        if source["source_kind"] == "table":
            base = f"SELECT * FROM {_quote_qualified(engine, source['table_name'])}"
        elif source["source_kind"] == "query":
            base = (
                "SELECT * FROM ("
                + str(source["source_query"]).strip().rstrip(";")
                + ") AS dv_source"
            )
        else:
            raise ValueError("Ce connecteur SQL attend une table ou requête.")

        if source["refresh_mode"] == "incremental" and watermark is not None:
            col = source.get("incremental_column")
            if not col or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", col):
                raise ValueError("Colonne incrémentale invalide.")
            quoted = engine.dialect.identifier_preparer.quote(col)
            base += f" WHERE {quoted} > :dv_watermark ORDER BY {quoted}"
            params["dv_watermark"] = watermark

        if limit is not None:
            safe_limit = max(1, min(int(limit), 5000))
            ctype = connector["connector_type"]
            if ctype == "oracle":
                base = f"SELECT * FROM ({base}) dv_limited FETCH FIRST {safe_limit} ROWS ONLY"
            elif ctype == "sqlserver":
                base = f"SELECT TOP {safe_limit} * FROM ({base}) AS dv_limited"
            else:
                base = f"SELECT * FROM ({base}) AS dv_limited LIMIT {safe_limit}"

        with engine.connect() as conn:
            return pd.read_sql_query(text(base), conn, params=params)
    finally:
        engine.dispose()


def _bigquery_credentials(secret: str):
    if not secret.strip():
        return None
    require_driver("bigquery")
    from google.oauth2 import service_account
    try:
        payload = json.loads(secret)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Le secret BigQuery doit être un JSON de service account valide, "
            "ou vide pour utiliser Application Default Credentials."
        ) from exc
    return service_account.Credentials.from_service_account_info(payload)


def _bigquery_client(connector: dict[str, Any]):
    require_driver("bigquery")
    from google.cloud import bigquery
    credentials = _bigquery_credentials(connector.get("password") or "")
    return bigquery.Client(
        project=connector["database_name"],
        credentials=credentials,
        location=(connector.get("options") or {}).get("location"),
    )


def test_bigquery(connector: dict[str, Any]) -> dict[str, Any]:
    client = _bigquery_client(connector)
    list(client.list_datasets(max_results=1))
    return {"ok": True}


def discover_bigquery(
    connector: dict[str, Any],
    max_tables: int,
) -> dict[str, Any]:
    client = _bigquery_client(connector)
    dataset_filter = str((connector.get("options") or {}).get("dataset") or "").strip()
    datasets = (
        [client.get_dataset(f"{client.project}.{dataset_filter}")]
        if dataset_filter
        else list(client.list_datasets())
    )
    tables: list[dict[str, Any]] = []
    schemas: list[str] = []
    for dataset in datasets[:40]:
        dataset_id = dataset.dataset_id
        schemas.append(dataset_id)
        for item in client.list_tables(dataset.reference):
            if len(tables) >= max_tables:
                break
            table = client.get_table(item.reference)
            tables.append(
                {
                    "schema": dataset_id,
                    "name": item.table_id,
                    "qualified_name": (
                        f"{client.project}.{dataset_id}.{item.table_id}"
                    ),
                    "columns": [
                        {
                            "name": field.name,
                            "type": field.field_type,
                            "nullable": field.mode != "REQUIRED",
                        }
                        for field in table.schema
                    ],
                    "kind": "table",
                }
            )
        if len(tables) >= max_tables:
            break
    return {
        "schemas": schemas,
        "tables": tables,
        "truncated": len(tables) >= max_tables,
    }


def _bq_quote_table(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", name):
        raise ValueError("Identifiant BigQuery invalide.")
    return f"`{name.replace('`', '')}`"


def fetch_bigquery(
    connector: dict[str, Any],
    source: dict[str, Any],
    *,
    watermark: Any = None,
    limit: int | None = None,
) -> pd.DataFrame:
    require_driver("bigquery")
    from google.cloud import bigquery
    client = _bigquery_client(connector)
    params = []
    if source["source_kind"] == "table":
        sql = f"SELECT * FROM {_bq_quote_table(source['table_name'])}"
    elif source["source_kind"] == "query":
        sql = (
            "SELECT * FROM ("
            + str(source["source_query"]).strip().rstrip(";")
            + ") AS dv_source"
        )
    else:
        raise ValueError("BigQuery attend une table ou requête SQL.")

    if source["refresh_mode"] == "incremental" and watermark is not None:
        column = source.get("incremental_column")
        if not column or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
            raise ValueError("Colonne incrémentale BigQuery invalide.")
        sql += f" WHERE `{column}` > @dv_watermark ORDER BY `{column}`"
        if isinstance(watermark, bool):
            param_type = "BOOL"
        elif isinstance(watermark, int):
            param_type = "INT64"
        elif isinstance(watermark, float):
            param_type = "FLOAT64"
        else:
            param_type = "STRING"
        params.append(bigquery.ScalarQueryParameter("dv_watermark", param_type, watermark))

    if limit is not None:
        sql = f"SELECT * FROM ({sql}) AS dv_limited LIMIT {max(1, min(int(limit), 5000))}"

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    result = client.query(sql, job_config=job_config).result()
    rows = [dict(row.items()) for row in result]
    return pd.DataFrame(rows)


def _snowflake_connection(connector: dict[str, Any]):
    require_driver("snowflake")
    import snowflake.connector
    options = connector.get("options") or {}
    kwargs = {
        "account": connector["host"],
        "user": connector["username"],
        "password": connector.get("password") or "",
        "database": connector["database_name"],
        "warehouse": options.get("warehouse"),
        "schema": options.get("schema"),
        "role": options.get("role"),
        "login_timeout": 8,
        "network_timeout": 20,
    }
    return snowflake.connector.connect(
        **{key: value for key, value in kwargs.items() if value not in (None, "")}
    )


def test_snowflake(connector: dict[str, Any]) -> dict[str, Any]:
    conn = _snowflake_connection(connector)
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            cur.close()
        return {"ok": True}
    finally:
        conn.close()


def _quoted(identifier: str, quote: str = '"') -> str:
    parts = identifier.split(".")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", part) for part in parts):
        raise ValueError("Identifiant invalide.")
    return ".".join(
        quote + part.replace(quote, quote + quote) + quote
        for part in parts
    )


def discover_snowflake(
    connector: dict[str, Any],
    max_tables: int,
) -> dict[str, Any]:
    conn = _snowflake_connection(connector)
    database = _quoted(connector["database_name"])
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT TABLE_SCHEMA,TABLE_NAME FROM {database}.INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA,TABLE_NAME"
            )
            rows = cur.fetchmany(max_tables)
            tables = []
            schemas = []
            for schema, name in rows:
                if schema not in schemas:
                    schemas.append(schema)
                qualified = f"{connector['database_name']}.{schema}.{name}"
                try:
                    cur.execute(f"DESCRIBE TABLE {_quoted(qualified)}")
                    columns = [
                        {
                            "name": str(item[0]),
                            "type": str(item[1]),
                            "nullable": str(item[3]).upper() == "Y",
                        }
                        for item in cur.fetchall()
                    ]
                except Exception:
                    columns = []
                tables.append(
                    {
                        "schema": schema,
                        "name": name,
                        "qualified_name": qualified,
                        "columns": columns,
                        "kind": "table",
                    }
                )
            return {
                "schemas": schemas,
                "tables": tables,
                "truncated": len(tables) >= max_tables,
            }
        finally:
            cur.close()
    finally:
        conn.close()


def fetch_snowflake(
    connector: dict[str, Any],
    source: dict[str, Any],
    *,
    watermark: Any = None,
    limit: int | None = None,
) -> pd.DataFrame:
    conn = _snowflake_connection(connector)
    try:
        cur = conn.cursor()
        try:
            if source["source_kind"] == "table":
                sql = f"SELECT * FROM {_quoted(source['table_name'])}"
            elif source["source_kind"] == "query":
                sql = (
                    "SELECT * FROM ("
                    + str(source["source_query"]).strip().rstrip(";")
                    + ") AS dv_source"
                )
            else:
                raise ValueError("Snowflake attend une table ou requête.")

            params = None
            if source["refresh_mode"] == "incremental" and watermark is not None:
                col = source.get("incremental_column")
                if not col or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", col):
                    raise ValueError("Colonne incrémentale invalide.")
                sql += f' WHERE "{col}" > %s ORDER BY "{col}"'
                params = (watermark,)
            if limit is not None:
                sql = f"SELECT * FROM ({sql}) AS dv_limited LIMIT {max(1, min(int(limit), 5000))}"
            cur.execute(sql, params)
            columns = [item[0] for item in cur.description or []]
            return pd.DataFrame(cur.fetchall(), columns=columns)
        finally:
            cur.close()
    finally:
        conn.close()


def _databricks_connection(connector: dict[str, Any]):
    require_driver("databricks")
    from databricks import sql
    options = connector.get("options") or {}
    kwargs = {
        "server_hostname": connector["host"],
        "http_path": options.get("http_path"),
        "access_token": connector.get("password") or "",
        "catalog": options.get("catalog") or connector.get("database_name") or None,
        "schema": options.get("schema"),
    }
    return sql.connect(**{k: v for k, v in kwargs.items() if v not in (None, "")})


def test_databricks(connector: dict[str, Any]) -> dict[str, Any]:
    conn = _databricks_connection(connector)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True}
    finally:
        conn.close()


def discover_databricks(
    connector: dict[str, Any],
    max_tables: int,
) -> dict[str, Any]:
    conn = _databricks_connection(connector)
    options = connector.get("options") or {}
    catalog = options.get("catalog") or connector.get("database_name") or None
    configured_schema = options.get("schema")
    try:
        with conn.cursor() as cur:
            if configured_schema:
                schemas = [configured_schema]
            else:
                cur.execute("SHOW SCHEMAS")
                schemas = [str(row[0]) for row in cur.fetchall()]
            tables: list[dict[str, Any]] = []
            for schema in schemas[:40]:
                namespace = (
                    f"{_quoted(str(catalog), '`')}.{_quoted(schema, '`')}"
                    if catalog
                    else _quoted(schema, "`")
                )
                cur.execute(f"SHOW TABLES IN {namespace}")
                for row in cur.fetchall():
                    if len(tables) >= max_tables:
                        break
                    # Databricks SHOW TABLES usually: database, tableName, isTemporary
                    name = str(row[1] if len(row) > 1 else row[0])
                    qualified = (
                        f"{catalog}.{schema}.{name}" if catalog else f"{schema}.{name}"
                    )
                    try:
                        cur.execute(f"DESCRIBE TABLE {_quoted(qualified, '`')}")
                        columns = [
                            {
                                "name": str(item[0]),
                                "type": str(item[1]) if len(item) > 1 else "",
                                "nullable": True,
                            }
                            for item in cur.fetchall()
                            if item and item[0] and not str(item[0]).startswith("#")
                        ]
                    except Exception:
                        columns = []
                    tables.append(
                        {
                            "schema": schema,
                            "name": name,
                            "qualified_name": qualified,
                            "columns": columns,
                            "kind": "table",
                        }
                    )
                if len(tables) >= max_tables:
                    break
            return {
                "schemas": schemas,
                "tables": tables,
                "truncated": len(tables) >= max_tables,
            }
    finally:
        conn.close()


def fetch_databricks(
    connector: dict[str, Any],
    source: dict[str, Any],
    *,
    watermark: Any = None,
    limit: int | None = None,
) -> pd.DataFrame:
    conn = _databricks_connection(connector)
    try:
        with conn.cursor() as cur:
            if source["source_kind"] == "table":
                sql = f"SELECT * FROM {_quoted(source['table_name'], '`')}"
            elif source["source_kind"] == "query":
                sql = (
                    "SELECT * FROM ("
                    + str(source["source_query"]).strip().rstrip(";")
                    + ") AS dv_source"
                )
            else:
                raise ValueError("Databricks attend une table ou requête.")

            params = None
            if source["refresh_mode"] == "incremental" and watermark is not None:
                col = source.get("incremental_column")
                if not col or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", col):
                    raise ValueError("Colonne incrémentale invalide.")
                sql += f" WHERE `{col}` > ? ORDER BY `{col}`"
                params = [watermark]
            if limit is not None:
                sql = f"SELECT * FROM ({sql}) AS dv_limited LIMIT {max(1, min(int(limit), 5000))}"
            cur.execute(sql, params)
            columns = [item[0] for item in cur.description or []]
            return pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()


def _mongo_client(connector: dict[str, Any]):
    require_driver("mongodb")
    from pymongo import MongoClient
    options = connector.get("options") or {}
    kwargs: dict[str, Any] = {
        "serverSelectionTimeoutMS": 6000,
        "connectTimeoutMS": 6000,
        "tls": bool(options.get("tls", connector.get("ssl_mode") == "require")),
    }
    if options.get("auth_source"):
        kwargs["authSource"] = options["auth_source"]
    if options.get("replica_set"):
        kwargs["replicaSet"] = options["replica_set"]
    return MongoClient(
        host=connector["host"],
        port=int(connector["port"]),
        username=connector.get("username") or None,
        password=connector.get("password") or None,
        **kwargs,
    )


def test_mongodb(connector: dict[str, Any]) -> dict[str, Any]:
    client = _mongo_client(connector)
    try:
        client.admin.command("ping")
        return {"ok": True}
    finally:
        client.close()


def _mongo_type(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__


def discover_mongodb(
    connector: dict[str, Any],
    max_tables: int,
) -> dict[str, Any]:
    client = _mongo_client(connector)
    try:
        db = client[connector["database_name"]]
        collections = db.list_collection_names()[:max_tables]
        tables = []
        for name in collections:
            sample = db[name].find_one() or {}
            columns = [
                {
                    "name": str(key),
                    "type": _mongo_type(value),
                    "nullable": True,
                }
                for key, value in list(sample.items())[:100]
            ]
            tables.append(
                {
                    "schema": connector["database_name"],
                    "name": name,
                    "qualified_name": name,
                    "columns": columns,
                    "kind": "collection",
                }
            )
        return {
            "schemas": [connector["database_name"]],
            "tables": tables,
            "truncated": len(tables) >= max_tables,
        }
    finally:
        client.close()


def _mongo_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _mongo_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mongo_jsonable(v) for v in value]
    return str(value) if value.__class__.__module__.startswith("bson") else value


def fetch_mongodb(
    connector: dict[str, Any],
    source: dict[str, Any],
    *,
    watermark: Any = None,
    limit: int | None = None,
) -> pd.DataFrame:
    if source["source_kind"] not in {"collection", "table"}:
        raise ValueError("MongoDB attend une collection.")
    client = _mongo_client(connector)
    try:
        collection = client[connector["database_name"]][source["table_name"]]
        options = source.get("source_options") or {}
        raw_filter = options.get("filter") or {}
        raw_projection = options.get("projection")
        if not isinstance(raw_filter, dict):
            raise ValueError("source_options.filter doit être un objet JSON.")
        query_filter = dict(raw_filter)
        if source["refresh_mode"] == "incremental" and watermark is not None:
            column = source.get("incremental_column")
            if not column or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", column):
                raise ValueError("Champ watermark MongoDB invalide.")
            query_filter[column] = {"$gt": watermark}
        cursor = collection.find(
            query_filter,
            raw_projection if isinstance(raw_projection, dict) else None,
        )
        if source["refresh_mode"] == "incremental" and source.get("incremental_column"):
            cursor = cursor.sort(source["incremental_column"], 1)
        if limit is not None:
            cursor = cursor.limit(max(1, min(int(limit), 5000)))
        docs = [_mongo_jsonable(doc) for doc in cursor]
        return pd.json_normalize(docs) if docs else pd.DataFrame()
    finally:
        client.close()




def _object_format(key: str, source: dict[str, Any]) -> str:
    options = source.get("source_options") or {}
    configured = str(options.get("format") or "").strip().lower().lstrip(".")
    if configured:
        return configured
    suffix = Path(str(key)).suffix.lower().lstrip(".")
    return "jsonl" if suffix in {"ndjson", "jsonl"} else suffix


def _object_frame_from_bytes(payload: bytes, key: str, source: dict[str, Any]) -> pd.DataFrame:
    options = source.get("source_options") or {}
    max_mb = max(1, min(int(options.get("max_object_mb", 200) or 200), 2048))
    if len(payload) > max_mb * 1024 * 1024:
        raise ValueError(f"Objet cloud trop volumineux: limite {max_mb} MB.")
    fmt = _object_format(key, source)
    buf = io.BytesIO(payload)
    if fmt in {"csv", "txt"}:
        return pd.read_csv(
            buf,
            sep=str(options.get("delimiter") or ","),
            encoding=str(options.get("encoding") or "utf-8"),
        )
    if fmt in {"jsonl", "ndjson"}:
        return pd.read_json(buf, lines=True)
    if fmt == "json":
        try:
            return pd.read_json(buf)
        except ValueError:
            buf.seek(0)
            raw = json.loads(buf.read().decode(str(options.get("encoding") or "utf-8")))
            if isinstance(raw, list):
                return pd.json_normalize(raw)
            if isinstance(raw, dict):
                records = raw.get("records") if isinstance(raw.get("records"), list) else [raw]
                return pd.json_normalize(records)
            raise
    if fmt in {"parquet", "pq"}:
        return pd.read_parquet(buf)
    if fmt in {"xlsx", "xls"}:
        return pd.read_excel(buf, sheet_name=options.get("sheet_name", 0))
    raise ValueError(
        "Format objet non supporté. Utilisez CSV, JSON/JSONL, Parquet ou XLSX."
    )


def _object_discovery_row(key: str, *, size: int | None = None, updated: Any = None) -> dict[str, Any]:
    return {
        "schema": None,
        "name": Path(key).name or key,
        "qualified_name": key,
        "columns": [],
        "kind": "object",
        "size_bytes": int(size or 0),
        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else (str(updated) if updated else None),
        "format": Path(key).suffix.lower().lstrip("."),
    }


def _s3_client(connector: dict[str, Any]):
    require_driver("s3")
    import boto3
    options = connector.get("options") or {}
    kwargs: dict[str, Any] = {
        "region_name": options.get("region") or None,
        "endpoint_url": connector.get("host") or None,
        "aws_access_key_id": connector.get("username") or None,
        "aws_secret_access_key": connector.get("password") or None,
        "aws_session_token": options.get("session_token") or None,
    }
    return boto3.client("s3", **{k: v for k, v in kwargs.items() if v not in (None, "")})


def test_s3(connector: dict[str, Any]) -> dict[str, Any]:
    _s3_client(connector).head_bucket(Bucket=connector["database_name"])
    return {"ok": True, "bucket": connector["database_name"]}


def discover_s3(connector: dict[str, Any], max_tables: int) -> dict[str, Any]:
    client = _s3_client(connector)
    options = connector.get("options") or {}
    prefix = str(options.get("prefix") or "")
    response = client.list_objects_v2(Bucket=connector["database_name"], Prefix=prefix, MaxKeys=max_tables)
    objects = [
        _object_discovery_row(
            str(item.get("Key") or ""),
            size=item.get("Size"),
            updated=item.get("LastModified"),
        )
        for item in response.get("Contents", [])
        if item.get("Key") and not str(item.get("Key")).endswith("/")
    ]
    return {"schemas": [], "tables": objects, "objects": objects, "truncated": bool(response.get("IsTruncated"))}


def fetch_s3(connector: dict[str, Any], source: dict[str, Any], *, watermark: Any = None, limit: int | None = None) -> pd.DataFrame:
    if source.get("source_kind") != "object":
        raise ValueError("S3 attend une source de type object.")
    key = str(source.get("table_name") or "")
    response = _s3_client(connector).get_object(Bucket=connector["database_name"], Key=key)
    frame = _object_frame_from_bytes(response["Body"].read(), key, source)
    return frame.head(max(1, min(int(limit), 5000))) if limit is not None else frame


def _gcs_credentials(secret: str):
    if not secret.strip():
        return None
    from google.oauth2 import service_account
    try:
        payload = json.loads(secret)
    except json.JSONDecodeError as exc:
        raise ValueError("Le secret GCS doit être un JSON de service account valide ou vide pour ADC.") from exc
    return service_account.Credentials.from_service_account_info(payload)


def _gcs_client(connector: dict[str, Any]):
    require_driver("gcs")
    from google.cloud import storage
    options = connector.get("options") or {}
    return storage.Client(project=options.get("project_id") or None, credentials=_gcs_credentials(connector.get("password") or ""))


def test_gcs(connector: dict[str, Any]) -> dict[str, Any]:
    bucket = _gcs_client(connector).bucket(connector["database_name"])
    bucket.reload()
    return {"ok": True, "bucket": connector["database_name"]}


def discover_gcs(connector: dict[str, Any], max_tables: int) -> dict[str, Any]:
    client = _gcs_client(connector)
    prefix = str((connector.get("options") or {}).get("prefix") or "")
    blobs = list(client.list_blobs(connector["database_name"], prefix=prefix, max_results=max_tables))
    objects = [_object_discovery_row(blob.name, size=blob.size, updated=blob.updated) for blob in blobs if blob.name and not blob.name.endswith("/")]
    return {"schemas": [], "tables": objects, "objects": objects, "truncated": len(objects) >= max_tables}


def fetch_gcs(connector: dict[str, Any], source: dict[str, Any], *, watermark: Any = None, limit: int | None = None) -> pd.DataFrame:
    if source.get("source_kind") != "object":
        raise ValueError("GCS attend une source de type object.")
    key = str(source.get("table_name") or "")
    payload = _gcs_client(connector).bucket(connector["database_name"]).blob(key).download_as_bytes()
    frame = _object_frame_from_bytes(payload, key, source)
    return frame.head(max(1, min(int(limit), 5000))) if limit is not None else frame


def _azure_container(connector: dict[str, Any]):
    require_driver("azure_blob")
    from azure.storage.blob import BlobServiceClient
    service = BlobServiceClient(account_url=connector["host"], credential=connector.get("password") or None)
    return service.get_container_client(connector["database_name"])


def test_azure_blob(connector: dict[str, Any]) -> dict[str, Any]:
    _azure_container(connector).get_container_properties()
    return {"ok": True, "container": connector["database_name"]}


def discover_azure_blob(connector: dict[str, Any], max_tables: int) -> dict[str, Any]:
    container = _azure_container(connector)
    prefix = str((connector.get("options") or {}).get("prefix") or "")
    objects: list[dict[str, Any]] = []
    for blob in container.list_blobs(name_starts_with=prefix):
        if len(objects) >= max_tables:
            break
        name = str(getattr(blob, "name", "") or "")
        if not name or name.endswith("/"):
            continue
        objects.append(_object_discovery_row(name, size=getattr(blob, "size", 0), updated=getattr(blob, "last_modified", None)))
    return {"schemas": [], "tables": objects, "objects": objects, "truncated": len(objects) >= max_tables}


def fetch_azure_blob(connector: dict[str, Any], source: dict[str, Any], *, watermark: Any = None, limit: int | None = None) -> pd.DataFrame:
    if source.get("source_kind") != "object":
        raise ValueError("Azure Blob attend une source de type object.")
    key = str(source.get("table_name") or "")
    payload = _azure_container(connector).download_blob(key).readall()
    frame = _object_frame_from_bytes(payload, key, source)
    return frame.head(max(1, min(int(limit), 5000))) if limit is not None else frame

NATIVE_TESTERS = {
    "bigquery": test_bigquery,
    "snowflake": test_snowflake,
    "databricks": test_databricks,
    "mongodb": test_mongodb,
    "s3": test_s3,
    "gcs": test_gcs,
    "azure_blob": test_azure_blob,
}
NATIVE_DISCOVERERS = {
    "bigquery": discover_bigquery,
    "snowflake": discover_snowflake,
    "databricks": discover_databricks,
    "mongodb": discover_mongodb,
    "s3": discover_s3,
    "gcs": discover_gcs,
    "azure_blob": discover_azure_blob,
}
NATIVE_FETCHERS = {
    "bigquery": fetch_bigquery,
    "snowflake": fetch_snowflake,
    "databricks": fetch_databricks,
    "mongodb": fetch_mongodb,
    "s3": fetch_s3,
    "gcs": fetch_gcs,
    "azure_blob": fetch_azure_blob,
}


def test_backend(connector: dict[str, Any]) -> dict[str, Any]:
    ctype = connector["connector_type"]
    if is_sqlalchemy_connector(ctype):
        return test_sqlalchemy(connector)
    tester = NATIVE_TESTERS.get(ctype)
    if tester is None:
        raise ValueError(f"Backend de test absent: {ctype}")
    return tester(connector)


def discover_backend(
    connector: dict[str, Any],
    max_tables: int = 250,
) -> dict[str, Any]:
    ctype = connector["connector_type"]
    if is_sqlalchemy_connector(ctype):
        return discover_sqlalchemy(connector, max_tables)
    discoverer = NATIVE_DISCOVERERS.get(ctype)
    if discoverer is None:
        raise ValueError(f"Backend de découverte absent: {ctype}")
    return discoverer(connector, max_tables)


def fetch_backend(
    connector: dict[str, Any],
    source: dict[str, Any],
    *,
    watermark: Any = None,
    limit: int | None = None,
) -> pd.DataFrame:
    ctype = connector["connector_type"]
    if is_sqlalchemy_connector(ctype):
        return fetch_sqlalchemy(
            connector, source, watermark=watermark, limit=limit
        )
    fetcher = NATIVE_FETCHERS.get(ctype)
    if fetcher is None:
        raise ValueError(f"Backend de lecture absent: {ctype}")
    return fetcher(
        connector, source, watermark=watermark, limit=limit
    )
