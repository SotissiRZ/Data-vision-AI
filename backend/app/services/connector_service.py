from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from app.core.config import get_settings
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

SUPPORTED_CONNECTORS = {"postgresql", "mysql"}
SUPPORTED_REFRESH_MODES = {"full", "incremental"}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)*$")


def _fernet() -> Fernet:
    # Stable application-level envelope key derived from AUTH_SECRET. The secret must be
    # rotated through a controlled migration if credentials already exist.
    settings = get_settings()
    material = settings.connector_secret_key or settings.auth_secret
    raw = hashlib.sha256(material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Impossible de déchiffrer les credentials. Vérifiez AUTH_SECRET.") from exc


def _safe_error(exc: Exception, password: str = "") -> str:
    msg = str(exc)
    if password:
        msg = msg.replace(password, "***")
    return msg[:1800]


def _row_to_connector(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["options"] = json_loads(row.pop("options_json", "{}"), {})
    row.pop("password_ciphertext", None)
    row.pop("password", None)
    row["has_credentials"] = True
    return row


def _row_to_source(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["source_options"] = json_loads(row.pop("source_options_json", "{}"), {})
    row["watermark"] = json_loads(row.pop("watermark_json", None), None)
    row["schema"] = json_loads(row.pop("schema_json", None), None)
    row["schema_drift"] = json_loads(row.pop("schema_drift_json", None), None)
    return row


def create_connector(
    actor_id: str,
    workspace_id: str,
    *,
    name: str,
    connector_type: str,
    host: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
    ssl_mode: str = "prefer",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    connector_type = connector_type.lower().strip()
    if connector_type not in SUPPORTED_CONNECTORS:
        raise ValueError("Connecteur non supporté. Utilisez postgresql ou mysql.")
    if not host.strip() or not database.strip() or not username.strip():
        raise ValueError("Hôte, base et utilisateur sont requis.")
    if ssl_mode not in {"disable", "prefer", "require"}:
        raise ValueError("ssl_mode invalide")
    cid = str(uuid.uuid4()); now = utcnow()
    execute(
        """INSERT INTO data_connectors(id,workspace_id,name,connector_type,host,port,database_name,username,password_ciphertext,ssl_mode,options_json,status,created_by,created_at,updated_at)
           VALUES(:id,:ws,:name,:type,:host,:port,:db,:username,:password,:ssl,:options,'untested',:user,:created,:updated)""",
        {"id":cid,"ws":workspace_id,"name":name.strip(),"type":connector_type,"host":host.strip(),"port":port or (5432 if connector_type=="postgresql" else 3306),"db":database.strip(),"username":username.strip(),"password":encrypt_secret(password),"ssl":ssl_mode,"options":json_dumps(options or {}),"user":actor_id,"created":now,"updated":now},
    )
    return get_connector(workspace_id, cid)


def update_connector(
    actor_id: str,
    workspace_id: str,
    connector_id: str,
    *,
    name: str | None = None,
    host: str | None = None,
    port: int | None = None,
    database: str | None = None,
    username: str | None = None,
    password: str | None = None,
    ssl_mode: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _get_connector_secret(workspace_id, connector_id)
    updates: dict[str, Any] = {"id":connector_id,"ws":workspace_id,"updated":utcnow()}
    clauses = ["updated_at=:updated", "status='untested'"]
    mapping = {"name":("name",name),"host":("host",host),"port":("port",port),"database":("database_name",database),"username":("username",username),"ssl_mode":("ssl_mode",ssl_mode)}
    for key,(column,value) in mapping.items():
        if value is not None:
            if key == "ssl_mode" and value not in {"disable","prefer","require"}: raise ValueError("ssl_mode invalide")
            clauses.append(f"{column}=:{key}"); updates[key]=value
    if password is not None and password != "":
        clauses.append("password_ciphertext=:password"); updates["password"] = encrypt_secret(password)
    if options is not None:
        clauses.append("options_json=:options"); updates["options"] = json_dumps(options)
    execute(f"UPDATE data_connectors SET {', '.join(clauses)} WHERE id=:id AND workspace_id=:ws", updates)
    if not current: raise KeyError("Connecteur introuvable")
    return get_connector(workspace_id, connector_id)


def get_connector(workspace_id: str, connector_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM data_connectors WHERE id=:id AND workspace_id=:ws", {"id":connector_id,"ws":workspace_id})
    if not row: raise KeyError("Connecteur introuvable")
    return _row_to_connector(row)


def _get_connector_secret(workspace_id: str, connector_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM data_connectors WHERE id=:id AND workspace_id=:ws", {"id":connector_id,"ws":workspace_id})
    if not row: raise KeyError("Connecteur introuvable")
    row = dict(row); row["options"] = json_loads(row.get("options_json"), {})
    row["password"] = decrypt_secret(row.get("password_ciphertext"))
    return row


def list_connectors(workspace_id: str) -> list[dict[str, Any]]:
    return [_row_to_connector(r) for r in fetch_all("SELECT * FROM data_connectors WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws":workspace_id})]


def delete_connector(workspace_id: str, connector_id: str) -> None:
    linked = fetch_one("SELECT COUNT(*) AS n FROM connector_sources WHERE connector_id=:id", {"id":connector_id})
    if linked and int(linked["n"]) > 0:
        raise ValueError("Supprimez d'abord les sources rattachées à ce connecteur.")
    execute("DELETE FROM data_connectors WHERE id=:id AND workspace_id=:ws", {"id":connector_id,"ws":workspace_id})


def _url_and_connect_args(connector: dict[str, Any]) -> tuple[URL, dict[str, Any]]:
    ctype = connector["connector_type"]
    driver = "postgresql+psycopg" if ctype == "postgresql" else "mysql+pymysql"
    query: dict[str, str] = {}
    connect_args: dict[str, Any] = {"connect_timeout": 5}
    ssl_mode = connector.get("ssl_mode", "prefer")
    if ctype == "postgresql" and ssl_mode in {"disable", "require"}:
        query["sslmode"] = ssl_mode
    if ctype == "mysql" and ssl_mode == "require":
        connect_args["ssl"] = {}
    options = connector.get("options") or {}
    for key,value in options.get("query", {}).items() if isinstance(options.get("query"), dict) else []:
        query[str(key)] = str(value)
    url = URL.create(driver, username=connector["username"], password=connector.get("password") or "", host=connector["host"], port=int(connector["port"]), database=connector["database_name"], query=query)
    return url, connect_args


def connector_engine(workspace_id: str, connector_id: str):
    connector = _get_connector_secret(workspace_id, connector_id)
    url, connect_args = _url_and_connect_args(connector)
    engine = create_engine(url, future=True, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args)
    return connector, engine


def test_connector(workspace_id: str, connector_id: str) -> dict[str, Any]:
    connector, engine = connector_engine(workspace_id, connector_id)
    now = utcnow()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        execute("UPDATE data_connectors SET status='healthy',last_tested_at=:now,last_error=NULL,updated_at=:now WHERE id=:id", {"now":now,"id":connector_id})
        return {"ok":True,"status":"healthy","tested_at":now,"connector_id":connector_id}
    except Exception as exc:
        error = _safe_error(exc, connector.get("password", ""))
        execute("UPDATE data_connectors SET status='error',last_tested_at=:now,last_error=:error,updated_at=:now WHERE id=:id", {"now":now,"error":error,"id":connector_id})
        return {"ok":False,"status":"error","tested_at":now,"connector_id":connector_id,"error":error}
    finally:
        engine.dispose()


def discover_connector(workspace_id: str, connector_id: str, max_tables: int = 250) -> dict[str, Any]:
    connector, engine = connector_engine(workspace_id, connector_id)
    try:
        inspector = inspect(engine)
        schemas = []
        try: schemas = inspector.get_schema_names()
        except Exception: schemas = []
        ignore = {"information_schema", "pg_catalog", "pg_toast", "mysql", "performance_schema", "sys"}
        selected_schemas = [s for s in schemas if s not in ignore] or [None]
        tables: list[dict[str, Any]] = []
        for schema in selected_schemas[:30]:
            try: names = inspector.get_table_names(schema=schema)
            except Exception: continue
            for name in names:
                if len(tables) >= max_tables: break
                try:
                    cols = inspector.get_columns(name, schema=schema)
                    columns = [{"name":str(c.get("name")),"type":str(c.get("type")),"nullable":bool(c.get("nullable", True))} for c in cols]
                except Exception:
                    columns = []
                tables.append({"schema":schema,"name":name,"qualified_name":f"{schema}.{name}" if schema else name,"columns":columns})
            if len(tables) >= max_tables: break
        return {"connector":_row_to_connector(connector),"schemas":[s for s in selected_schemas if s],"tables":tables,"truncated":len(tables)>=max_tables}
    finally:
        engine.dispose()


def create_source(
    actor_id: str,
    workspace_id: str,
    *,
    connector_id: str,
    name: str,
    source_kind: str,
    table_name: str | None = None,
    query: str | None = None,
    refresh_mode: str = "full",
    incremental_column: str | None = None,
    freshness_sla_minutes: int = 1440,
    schema_drift_policy: str = "warn",
    source_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    get_connector(workspace_id, connector_id)
    if source_kind not in {"table", "query"}: raise ValueError("source_kind doit être table ou query")
    if source_kind == "table":
        if not table_name or not _IDENTIFIER.match(table_name): raise ValueError("Nom de table invalide")
    else:
        if not query or not query.strip().lower().startswith(("select", "with")): raise ValueError("La source SQL doit être une requête SELECT/CTE en lecture seule")
        cleaned = query.strip().rstrip(";")
        if ";" in cleaned: raise ValueError("Une seule requête SQL est autorisée")
        if re.search(r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|call|execute|copy)\b", cleaned, flags=re.I):
            raise ValueError("La source SQL doit rester strictement en lecture seule")
    if refresh_mode not in SUPPORTED_REFRESH_MODES: raise ValueError("refresh_mode invalide")
    if refresh_mode == "incremental" and not incremental_column: raise ValueError("incremental_column requis en mode incremental")
    if incremental_column and not re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", incremental_column): raise ValueError("Colonne incrémentale invalide")
    if schema_drift_policy not in {"warn","fail"}: raise ValueError("schema_drift_policy invalide")
    sid = str(uuid.uuid4()); now = utcnow()
    execute("""INSERT INTO connector_sources(id,workspace_id,connector_id,name,source_kind,table_name,source_query,refresh_mode,incremental_column,watermark_json,freshness_sla_minutes,schema_drift_policy,source_options_json,status,created_by,created_at,updated_at)
             VALUES(:id,:ws,:connector,:name,:kind,:table,:query,:mode,:incremental,NULL,:sla,:drift,:options,'never_refreshed',:user,:created,:updated)""",
            {"id":sid,"ws":workspace_id,"connector":connector_id,"name":name.strip(),"kind":source_kind,"table":table_name,"query":query,"mode":refresh_mode,"incremental":incremental_column,"sla":max(5,int(freshness_sla_minutes)),"drift":schema_drift_policy,"options":json_dumps(source_options or {}),"user":actor_id,"created":now,"updated":now})
    return get_source(workspace_id, sid)


def get_source(workspace_id: str, source_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM connector_sources WHERE id=:id AND workspace_id=:ws", {"id":source_id,"ws":workspace_id})
    if not row: raise KeyError("Source introuvable")
    return _with_freshness(_row_to_source(row))


def list_sources(workspace_id: str) -> list[dict[str, Any]]:
    return [_with_freshness(_row_to_source(r)) for r in fetch_all("SELECT * FROM connector_sources WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws":workspace_id})]


def delete_source(workspace_id: str, source_id: str) -> None:
    execute("DELETE FROM refresh_schedules WHERE source_id=:id AND workspace_id=:ws", {"id":source_id,"ws":workspace_id})
    execute("DELETE FROM connector_sources WHERE id=:id AND workspace_id=:ws", {"id":source_id,"ws":workspace_id})


def _quote_qualified(engine, name: str) -> str:
    if not _IDENTIFIER.match(name): raise ValueError("Identifiant SQL invalide")
    prep = engine.dialect.identifier_preparer
    return ".".join(prep.quote(part) for part in name.split("."))


def _source_sql(engine, source: dict[str, Any], watermark: Any = None) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    if source["source_kind"] == "table":
        base = f"SELECT * FROM {_quote_qualified(engine, source['table_name'])}"
    else:
        base = f"SELECT * FROM ({str(source['source_query']).strip().rstrip(';')}) AS dv_source"
    if source["refresh_mode"] == "incremental" and watermark is not None:
        col = source.get("incremental_column")
        if not col or not re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", col): raise ValueError("Colonne incrémentale invalide")
        quoted = engine.dialect.identifier_preparer.quote(col)
        base += f" WHERE {quoted} > :dv_watermark ORDER BY {quoted}"
        params["dv_watermark"] = watermark
    return base, params


def fetch_source_frame(workspace_id: str, source_id: str, *, watermark: Any = None, limit: int | None = None) -> pd.DataFrame:
    source = get_source(workspace_id, source_id)
    connector, engine = connector_engine(workspace_id, source["connector_id"])
    try:
        sql, params = _source_sql(engine, source, watermark)
        if limit is not None:
            sql = f"SELECT * FROM ({sql}) AS dv_limited LIMIT {max(1,min(int(limit),5000))}"
        with engine.connect() as conn:
            return pd.read_sql_query(text(sql), conn, params=params)
    except Exception as exc:
        raise RuntimeError(_safe_error(exc, connector.get("password", ""))) from exc
    finally:
        engine.dispose()


def preview_source(workspace_id: str, source_id: str, limit: int = 50) -> dict[str, Any]:
    df = fetch_source_frame(workspace_id, source_id, limit=limit)
    sample = df.head(limit).where(df.head(limit).notna(), None).to_dict(orient="records")
    return {"columns":[str(c) for c in df.columns],"rows":sample,"returned_rows":len(sample),"dtypes":{str(c):str(t) for c,t in df.dtypes.items()}}


def _schema_of(df: pd.DataFrame) -> dict[str, str]:
    return {str(c):str(t) for c,t in df.dtypes.items()}


def _schema_drift(previous: dict[str, str] | None, current: dict[str, str]) -> dict[str, Any]:
    previous = previous or {}
    added = sorted(set(current)-set(previous)); removed = sorted(set(previous)-set(current))
    changed = [{"column":c,"before":previous[c],"after":current[c]} for c in sorted(set(previous)&set(current)) if previous[c] != current[c]]
    return {"detected":bool(previous and (added or removed or changed)),"added":added,"removed":removed,"type_changed":changed}


def _json_scalar(value: Any) -> Any:
    if value is None or (isinstance(value,float) and pd.isna(value)): return None
    if isinstance(value, pd.Timestamp): return value.isoformat()
    if hasattr(value, "item"):
        try: return value.item()
        except Exception: pass
    return value


def _watermark_from_frame(df: pd.DataFrame, column: str | None) -> Any:
    if not column or column not in df.columns or df.empty: return None
    series = df[column].dropna()
    if series.empty: return None
    try: return _json_scalar(series.max())
    except Exception: return _json_scalar(series.astype(str).max())


def refresh_source(workspace_id: str, source_id: str, *, actor_id: str, trigger: str = "manual", job_id: str | None = None) -> dict[str, Any]:
    from app.services.storage import load_dataframe_raw, save_dataframe_source, save_dataframe_version
    from app.services.workspace_service import bind_dataset

    source = get_source(workspace_id, source_id)
    run_id = str(uuid.uuid4()); started = utcnow(); before_id = source.get("dataset_id")
    execute("""INSERT INTO refresh_runs(id,workspace_id,source_id,connector_id,dataset_id_before,mode,status,trigger_type,triggered_by,job_id,watermark_before_json,started_at)
             VALUES(:id,:ws,:source,:connector,:before,:mode,'running',:trigger,:user,:job,:watermark,:started)""",
            {"id":run_id,"ws":workspace_id,"source":source_id,"connector":source["connector_id"],"before":before_id,"mode":source["refresh_mode"],"trigger":trigger,"user":actor_id,"job":job_id,"watermark":json_dumps(source.get("watermark")) if source.get("watermark") is not None else None,"started":started})
    execute("UPDATE connector_sources SET status='refreshing',last_refresh_started_at=:now,updated_at=:now WHERE id=:id", {"now":started,"id":source_id})
    try:
        watermark_before = source.get("watermark") if source["refresh_mode"] == "incremental" else None
        fetched = fetch_source_frame(workspace_id, source_id, watermark=watermark_before)
        incoming_schema = _schema_of(fetched)
        if source["refresh_mode"] == "incremental" and fetched.empty and source.get("schema"):
            incoming_schema = source.get("schema")
            drift = {"detected":False,"added":[],"removed":[],"type_changed":[]}
        else:
            drift = _schema_drift(source.get("schema"), incoming_schema)
        if drift["detected"] and source.get("schema_drift_policy") == "fail" and (drift["removed"] or drift["type_changed"]):
            raise ValueError(f"Schema drift bloquant: {drift}")

        rows_fetched = len(fetched); rows_written = rows_fetched
        if before_id:
            if source["refresh_mode"] == "incremental" and rows_fetched == 0:
                after_meta = None
                after_id = before_id
                watermark_after = source.get("watermark")
                rows_written = 0
            else:
                if source["refresh_mode"] == "incremental":
                    previous = load_dataframe_raw(before_id)
                    combined = pd.concat([previous, fetched], ignore_index=True, sort=False)
                    rows_written = len(combined)
                    payload = combined
                else:
                    payload = fetched
                operation = {"type":"connector_refresh","label":f"Refresh {source['name']}","source_id":source_id,"refresh_mode":source["refresh_mode"],"rows_fetched":rows_fetched,"trigger":trigger}
                after_meta = save_dataframe_version(before_id, payload, operation, governance_materialized=False)
                after_id = after_meta["id"]
                bind_dataset(actor_id, workspace_id, after_id)
                watermark_after = _watermark_from_frame(fetched, source.get("incremental_column")) if source["refresh_mode"] == "incremental" else None
        else:
            source_meta = {"connector_id":source["connector_id"],"source_id":source_id,"workspace_id":workspace_id,"source_kind":source["source_kind"],"table_name":source.get("table_name"),"refresh_mode":source["refresh_mode"]}
            after_meta = save_dataframe_source(fetched, source["name"], source_meta)
            after_id = after_meta["id"]
            bind_dataset(actor_id, workspace_id, after_id)
            watermark_after = _watermark_from_frame(fetched, source.get("incremental_column")) if source["refresh_mode"] == "incremental" else None

        finished = utcnow()
        effective_schema = incoming_schema if rows_fetched or not source.get("schema") else source.get("schema")
        execute("""UPDATE connector_sources SET dataset_id=:dataset,watermark_json=:watermark,schema_json=:schema,status='healthy',last_refresh_finished_at=:finished,last_success_at=:finished,last_error=NULL,last_rows_fetched=:rows,schema_drift_json=:drift,updated_at=:finished WHERE id=:id""",
                {"dataset":after_id,"watermark":json_dumps(watermark_after) if watermark_after is not None else None,"schema":json_dumps(effective_schema),"finished":finished,"rows":rows_fetched,"drift":json_dumps(drift),"id":source_id})
        execute("""UPDATE refresh_runs SET dataset_id_after=:after,status='completed',rows_fetched=:fetched,rows_written=:written,watermark_after_json=:watermark,schema_drift_json=:drift,finished_at=:finished WHERE id=:id""",
                {"after":after_id,"fetched":rows_fetched,"written":rows_written,"watermark":json_dumps(watermark_after) if watermark_after is not None else None,"drift":json_dumps(drift),"finished":finished,"id":run_id})
        contract_runs = []
        try:
            from app.services.data_reliability import list_contracts, run_contract, register_lineage_edge
            register_lineage_edge(workspace_id, "source", source_id, "dataset", after_id, "materialized_as", {"refresh_run_id": run_id, "refresh_mode": source["refresh_mode"]})
            for contract in list_contracts(workspace_id, after_id):
                if not contract.get("enabled"):
                    continue
                try:
                    cr = run_contract(actor_id, workspace_id, contract["id"], after_id)
                    contract_runs.append({"contract_id": contract["id"], "run_id": cr["id"], "status": cr["status"], "score": cr["score"]})
                except Exception as contract_exc:
                    contract_runs.append({"contract_id": contract["id"], "status": "error", "error": str(contract_exc)[:500]})
        except Exception:
            # Reliability automation must never corrupt a successfully materialized refresh.
            contract_runs = []
        return {"run_id":run_id,"source_id":source_id,"dataset_id":after_id,"previous_dataset_id":before_id,"status":"completed","rows_fetched":rows_fetched,"rows_written":rows_written,"watermark_before":watermark_before,"watermark_after":watermark_after,"schema_drift":drift,"contract_runs":contract_runs,"finished_at":finished}
    except Exception as exc:
        finished = utcnow(); error = _safe_error(exc)
        execute("UPDATE connector_sources SET status='error',last_refresh_finished_at=:finished,last_error=:error,updated_at=:finished WHERE id=:id", {"finished":finished,"error":error,"id":source_id})
        execute("UPDATE refresh_runs SET status='failed',error=:error,finished_at=:finished WHERE id=:id", {"error":error,"finished":finished,"id":run_id})
        raise


def get_refresh_runs(workspace_id: str, source_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws":workspace_id,"limit":max(1,min(int(limit),500))}
    where = "workspace_id=:ws"
    if source_id:
        where += " AND source_id=:source"; params["source"] = source_id
    rows = fetch_all(f"SELECT * FROM refresh_runs WHERE {where} ORDER BY started_at DESC LIMIT :limit", params)
    for row in rows:
        row["watermark_before"] = json_loads(row.pop("watermark_before_json", None), None)
        row["watermark_after"] = json_loads(row.pop("watermark_after_json", None), None)
        row["schema_drift"] = json_loads(row.pop("schema_drift_json", None), None)
    return rows


def save_schedule(workspace_id: str, source_id: str, *, enabled: bool, interval_minutes: int, actor_id: str) -> dict[str, Any]:
    get_source(workspace_id, source_id)
    interval = max(15, min(int(interval_minutes), 43200))
    now = datetime.now(timezone.utc); next_run = (now + timedelta(minutes=interval)).isoformat()
    existing = fetch_one("SELECT id FROM refresh_schedules WHERE workspace_id=:ws AND source_id=:source", {"ws":workspace_id,"source":source_id})
    if existing:
        execute("UPDATE refresh_schedules SET enabled=:enabled,interval_minutes=:interval,next_run_at=:next,updated_by=:user,updated_at=:now WHERE id=:id", {"enabled":1 if enabled else 0,"interval":interval,"next":next_run if enabled else None,"user":actor_id,"now":utcnow(),"id":existing["id"]})
        sid = existing["id"]
    else:
        sid = str(uuid.uuid4())
        execute("""INSERT INTO refresh_schedules(id,workspace_id,source_id,enabled,interval_minutes,next_run_at,created_by,updated_by,created_at,updated_at)
                 VALUES(:id,:ws,:source,:enabled,:interval,:next,:user,:user,:now,:now)""",
                {"id":sid,"ws":workspace_id,"source":source_id,"enabled":1 if enabled else 0,"interval":interval,"next":next_run if enabled else None,"user":actor_id,"now":utcnow()})
    return get_schedule(workspace_id, source_id)


def get_schedule(workspace_id: str, source_id: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM refresh_schedules WHERE workspace_id=:ws AND source_id=:source", {"ws":workspace_id,"source":source_id})
    if not row: return None
    row = dict(row); row["enabled"] = bool(row.get("enabled")); return row


def list_schedules(workspace_id: str) -> list[dict[str, Any]]:
    rows = fetch_all("SELECT * FROM refresh_schedules WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws":workspace_id})
    for row in rows: row["enabled"] = bool(row.get("enabled"))
    return rows


def claim_due_schedules(limit: int = 20) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc); now_iso = now.isoformat()
    rows = fetch_all("SELECT * FROM refresh_schedules WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=:now ORDER BY next_run_at ASC LIMIT :limit", {"now":now_iso,"limit":max(1,min(limit,100))})
    claimed: list[dict[str, Any]] = []
    for row in rows:
        interval = max(15,int(row.get("interval_minutes") or 60))
        nxt = (now + timedelta(minutes=interval)).isoformat()
        # Conditional update is the scheduler lock: only one worker can move this exact due timestamp.
        from app.services.metadata_store import connection
        with connection() as conn:
            result = conn.execute(text("UPDATE refresh_schedules SET next_run_at=:next,last_enqueued_at=:now,updated_at=:now WHERE id=:id AND next_run_at=:expected"), {"next":nxt,"now":now_iso,"id":row["id"],"expected":row["next_run_at"]})
            if getattr(result, "rowcount", 0) == 1:
                row = dict(row); row["next_run_at"] = nxt; row["last_enqueued_at"] = now_iso; claimed.append(row)
    return claimed


def _parse_dt(value: str | None) -> datetime | None:
    if not value: return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception: return None


def _with_freshness(source: dict[str, Any]) -> dict[str, Any]:
    last = _parse_dt(source.get("last_success_at")); now = datetime.now(timezone.utc); sla = max(5,int(source.get("freshness_sla_minutes") or 1440))
    if source.get("status") == "refreshing": freshness = "refreshing"; age = None if not last else int((now-last).total_seconds()/60)
    elif source.get("status") == "error": freshness = "error"; age = None if not last else int((now-last).total_seconds()/60)
    elif not last: freshness = "never"; age = None
    else:
        age = max(0,int((now-last).total_seconds()/60)); freshness = "fresh" if age <= sla else "stale"
        if freshness == "fresh" and age > int(sla*0.8): freshness = "warning"
    source["freshness"] = {"status":freshness,"age_minutes":age,"sla_minutes":sla}
    source["schedule"] = get_schedule(source["workspace_id"], source["id"])
    return source


def workspace_refresh_health(workspace_id: str) -> dict[str, Any]:
    connectors = list_connectors(workspace_id); sources = list_sources(workspace_id); runs = get_refresh_runs(workspace_id, limit=100)
    counts = {k:0 for k in ["fresh","warning","stale","error","never","refreshing"]}
    for source in sources: counts[source.get("freshness",{}).get("status","never")] = counts.get(source.get("freshness",{}).get("status","never"),0)+1
    completed = [r for r in runs if r.get("status") == "completed"]; failed = [r for r in runs if r.get("status") == "failed"]
    durations=[]
    for r in completed:
        a,b=_parse_dt(r.get("started_at")),_parse_dt(r.get("finished_at"))
        if a and b: durations.append(max(0,(b-a).total_seconds()))
    return {
        "connectors":len(connectors),"connector_errors":sum(1 for c in connectors if c.get("status")=="error"),"sources":len(sources),"freshness":counts,
        "runs_considered":len(runs),"success_rate":round((len(completed)/len(runs))*100,1) if runs else None,"avg_duration_seconds":round(sum(durations)/len(durations),2) if durations else None,
        "rows_fetched":sum(int(r.get("rows_fetched") or 0) for r in completed),"scheduled":sum(1 for s in sources if (s.get("schedule") or {}).get("enabled")),
    }
