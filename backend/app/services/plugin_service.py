from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.audit_service import record_event
from app.services.identity_service import get_secret, resolve_secret
from app.services.metadata_store import (
    execute,
    fetch_all,
    fetch_one,
    json_dumps,
    json_loads,
    utcnow,
)
from app.services.tenant_access import current_access_context


PLUGIN_PROTOCOLS = {"http_json", "mcp_http"}
PLUGIN_NETWORK_SCOPES = {"public", "private"}
PLUGIN_AUTH_TYPES = {"none", "bearer", "api_key"}
PLUGIN_CONTEXT_POLICIES = {"none", "semantic"}
PLUGIN_TOOL_RISKS = {"read", "reversible", "destructive", "external"}
PLUGIN_ALLOWED_ASSISTANT_PERMISSIONS = {
    "plugin:execute",
    "dataset:read",
    "dataset:transform",
    "visualization:create",
    "analysis:create",
    "analysis:read",
    "model:create",
    "model:read",
    "report:create",
    "dataset:export",
    "file:read",
    "connectors:read",
    "connectors:manage",
    "action:execute",
}

MAX_PLUGIN_TOOLS = 100
MAX_MANIFEST_BYTES = 256_000
MAX_SCHEMA_BYTES = 64_000
MAX_REQUEST_BYTES = 256_000
MAX_RESPONSE_BYTES = 2_000_000


class PluginToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
    description: str = Field(default="", max_length=4000)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    risk: Literal["read", "reversible", "destructive", "external"] = "read"
    required_permissions: list[str] = Field(default_factory=list, max_length=16)
    requires_dataset: bool = False
    requires_model: bool = False
    method: Literal["GET", "POST"] = "POST"
    path: str = "/"

    @model_validator(mode="after")
    def validate_permissions_and_path(self):
        unknown = sorted(set(self.required_permissions) - PLUGIN_ALLOWED_ASSISTANT_PERMISSIONS)
        if unknown:
            raise ValueError(f"Permissions plugin non autorisées: {', '.join(unknown)}")
        if (
            not self.path.startswith("/")
            or ".." in self.path
            or "?" in self.path
            or "#" in self.path
        ):
            raise ValueError("Le chemin HTTP du tool doit être absolu, sans '..', query ou fragment.")
        _validate_schema_shape(self.input_schema)
        return self


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=180)
    version: str = Field(default="0.1.0", max_length=64)
    description: str = Field(default="", max_length=4000)
    protocol: Literal["http_json", "mcp_http"]
    endpoint: str = Field(min_length=8, max_length=2000)
    network_scope: Literal["public", "private"] = "public"
    auth_type: Literal["none", "bearer", "api_key"] = "none"
    auth_header: str | None = Field(default=None, max_length=120)
    secret_id: str | None = Field(default=None, max_length=128)
    context_policy: Literal["none", "semantic"] = "none"
    timeout_seconds: int = Field(default=15, ge=2, le=30)
    health_path: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    protocol_version: str = Field(default="2025-03-26", max_length=32)
    tools: list[PluginToolDefinition] = Field(default_factory=list, max_length=MAX_PLUGIN_TOOLS)

    @model_validator(mode="after")
    def validate_manifest(self):
        _validate_plugin_url(
            self.endpoint,
            network_scope=self.network_scope,
            resolve_dns=False,
        )
        if self.auth_type != "none" and not self.secret_id:
            raise ValueError("secret_id est requis lorsque auth_type n'est pas none.")
        if self.auth_type == "api_key":
            header = (self.auth_header or "X-API-Key").strip()
            if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", header):
                raise ValueError("auth_header invalide.")
            if header.lower() in {"host", "content-length", "transfer-encoding", "connection"}:
                raise ValueError("auth_header réservé et interdit.")
            self.auth_header = header
        if self.health_path is not None:
            if (
                not self.health_path.startswith("/")
                or ".." in self.health_path
                or "?" in self.health_path
                or "#" in self.health_path
            ):
                raise ValueError("health_path doit être absolu, sans '..', query ou fragment.")

        if self.protocol == "http_json" and not self.tools:
            raise ValueError("Un plugin http_json doit déclarer au moins un tool.")
        if self.protocol == "mcp_http" and self.tools:
            # MCP tools are authoritative from tools/list, not from an untrusted local declaration.
            self.tools = []
        raw = self.model_dump(mode="json")
        _reject_raw_secrets(raw)
        encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise ValueError("Manifest plugin trop volumineux.")
        return self


@dataclass(frozen=True)
class PluginCallResult:
    result: Any
    duration_ms: float


def _reject_raw_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            item_path = f"{path}.{key}" if path else str(key)
            if key_lower == "input_schema":
                continue
            if key_lower in {
                "password",
                "token",
                "api_key",
                "apikey",
                "client_secret",
                "authorization",
                "secret",
            }:
                if item not in (None, "", False):
                    raise ValueError(
                        f"Secret brut interdit dans le manifest ({item_path}). Utilisez secret_id."
                    )
            _reject_raw_secrets(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_raw_secrets(item, f"{path}[{index}]")


def _validate_schema_shape(schema: dict[str, Any]) -> None:
    if not isinstance(schema, dict):
        raise ValueError("input_schema doit être un objet JSON Schema.")
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_SCHEMA_BYTES:
        raise ValueError("JSON Schema trop volumineux.")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ValueError(f"JSON Schema invalide: {exc}") from exc

    count = 0

    def walk(node: Any, depth: int = 0) -> None:
        nonlocal count
        count += 1
        if count > 1500 or depth > 24:
            raise ValueError("JSON Schema trop complexe.")
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str) and value.startswith(("http://", "https://")):
                    raise ValueError("Les $ref JSON Schema distants sont interdits.")
                walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    walk(schema)


def _is_blocked_ip(ip: ipaddress._BaseAddress, network_scope: str) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if str(ip) in {"169.254.169.254", "100.100.100.200"}:
        return True
    if network_scope == "public" and not ip.is_global:
        return True
    return False


def _validate_plugin_url(
    url: str,
    *,
    network_scope: str,
    resolve_dns: bool,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Endpoint plugin: schéma http/https requis.")
    if not parsed.hostname:
        raise ValueError("Endpoint plugin: hostname requis.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials dans l'URL interdits; utilisez Secret Vault.")
    if parsed.query or parsed.fragment:
        raise ValueError("Query string et fragment interdits dans l'endpoint plugin; utilisez Secret Vault et les arguments du tool.")
    if network_scope == "public" and parsed.scheme != "https":
        raise ValueError("Les plugins publics doivent utiliser HTTPS.")
    if network_scope not in PLUGIN_NETWORK_SCOPES:
        raise ValueError("network_scope invalide.")

    host = parsed.hostname
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _is_blocked_ip(literal, network_scope):
        raise ValueError("Endpoint plugin bloqué par la politique réseau.")

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except OSError as exc:
            raise RuntimeError(f"Résolution DNS plugin impossible: {exc}") from exc
        addresses = {item[4][0] for item in infos}
        if not addresses:
            raise RuntimeError("Aucune adresse réseau résolue pour le plugin.")
        for raw in addresses:
            try:
                ip = ipaddress.ip_address(raw)
            except ValueError:
                continue
            if _is_blocked_ip(ip, network_scope):
                raise RuntimeError("Endpoint plugin bloqué après résolution DNS.")


def _checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_plugin(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["enabled"] = bool(out.get("enabled"))
    out["manifest"] = json_loads(out.pop("manifest_json", "{}"), {})
    out["has_secret"] = bool(out.get("secret_id"))
    return out


def _tool_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["enabled"] = bool(out.get("enabled"))
    out["requires_dataset"] = bool(out.get("requires_dataset"))
    out["requires_model"] = bool(out.get("requires_model"))
    out["input_schema"] = json_loads(out.pop("input_schema_json", "{}"), {})
    out["required_permissions"] = json_loads(out.pop("required_permissions_json", "[]"), [])
    out["metadata"] = json_loads(out.pop("metadata_json", "{}"), {})
    return out


def list_plugins(workspace_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM plugin_installations WHERE workspace_id=:ws ORDER BY name,plugin_key",
        {"ws": workspace_id},
    )
    plugins = [_safe_plugin(row) for row in rows]
    for plugin in plugins:
        plugin["tools"] = list_plugin_tools(workspace_id, plugin["id"])
        plugin["tool_count"] = len(plugin["tools"])
    return plugins


def get_plugin(workspace_id: str, plugin_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM plugin_installations WHERE workspace_id=:ws AND id=:id",
        {"ws": workspace_id, "id": plugin_id},
    )
    if not row:
        raise KeyError("Plugin introuvable")
    plugin = _safe_plugin(row)
    plugin["tools"] = list_plugin_tools(workspace_id, plugin_id)
    plugin["tool_count"] = len(plugin["tools"])
    return plugin


def list_plugin_tools(workspace_id: str, plugin_id: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws": workspace_id}
    clause = ""
    if plugin_id:
        clause = " AND plugin_id=:plugin"
        params["plugin"] = plugin_id
    rows = fetch_all(
        "SELECT * FROM plugin_tools WHERE workspace_id=:ws" + clause + " ORDER BY namespaced_name",
        params,
    )
    return [_tool_row(row) for row in rows]


def list_enabled_runtime_tools() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT t.*,p.plugin_key,p.name AS plugin_name,p.version AS plugin_version,
               p.protocol,p.endpoint,p.context_policy,p.network_scope,p.status AS plugin_status
        FROM plugin_tools t
        JOIN plugin_installations p ON p.id=t.plugin_id AND p.workspace_id=t.workspace_id
        WHERE p.enabled=1 AND t.enabled=1
        ORDER BY t.namespaced_name
        """
    )
    return [_tool_row(row) for row in rows]


def install_plugin(
    actor_id: str,
    workspace_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    manifest = PluginManifest.model_validate(payload)
    raw = manifest.model_dump(mode="json")
    if manifest.secret_id:
        get_secret(workspace_id, manifest.secret_id)
    pid = str(uuid.uuid4())
    now = utcnow()
    try:
        execute(
            """
            INSERT INTO plugin_installations(
                id,workspace_id,plugin_key,name,version,description,protocol,endpoint,
                network_scope,auth_type,auth_header,secret_id,context_policy,timeout_seconds,
                manifest_json,checksum,enabled,status,last_error,last_synced_at,
                created_by,created_at,updated_at
            ) VALUES(
                :id,:ws,:key,:name,:version,:description,:protocol,:endpoint,
                :network_scope,:auth_type,:auth_header,:secret_id,:context_policy,:timeout,
                :manifest,:checksum,:enabled,:status,NULL,NULL,:user,:now,:now
            )
            """,
            {
                "id": pid,
                "ws": workspace_id,
                "key": manifest.plugin_key,
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "protocol": manifest.protocol,
                "endpoint": manifest.endpoint,
                "network_scope": manifest.network_scope,
                "auth_type": manifest.auth_type,
                "auth_header": manifest.auth_header,
                "secret_id": manifest.secret_id,
                "context_policy": manifest.context_policy,
                "timeout": manifest.timeout_seconds,
                "manifest": json_dumps(raw),
                "checksum": _checksum(raw),
                "enabled": 1 if manifest.enabled else 0,
                "status": "installed" if manifest.protocol == "http_json" else "needs_sync",
                "user": actor_id,
                "now": now,
            },
        )
    except Exception as exc:
        if "UNIQUE" in str(exc).upper() or "unique" in str(exc).lower():
            raise ValueError(f"plugin_key déjà installé dans ce workspace: {manifest.plugin_key}") from exc
        raise

    if manifest.protocol == "http_json":
        _replace_tool_cache(workspace_id, pid, manifest.plugin_key, manifest.tools, protocol="http_json")
        execute(
            "UPDATE plugin_installations SET last_synced_at=:now,status='ready' WHERE id=:id",
            {"now": now, "id": pid},
        )

    record_event(
        "plugin.install",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="plugin",
        resource_id=pid,
        payload={
            "plugin_key": manifest.plugin_key,
            "protocol": manifest.protocol,
            "endpoint_host": urlparse(manifest.endpoint).hostname,
            "checksum": _checksum(raw)[:16],
        },
    )
    return get_plugin(workspace_id, pid)


def update_plugin(
    actor_id: str,
    workspace_id: str,
    plugin_id: str,
    *,
    enabled: bool | None = None,
    endpoint: str | None = None,
    network_scope: str | None = None,
    secret_id: str | None = None,
    auth_type: str | None = None,
    auth_header: str | None = None,
    context_policy: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    current = get_plugin(workspace_id, plugin_id)
    raw = dict(current["manifest"])
    if enabled is not None:
        raw["enabled"] = bool(enabled)
    if endpoint is not None:
        raw["endpoint"] = endpoint
    if network_scope is not None:
        raw["network_scope"] = network_scope
    if secret_id is not None:
        raw["secret_id"] = secret_id or None
    if auth_type is not None:
        raw["auth_type"] = auth_type
    if auth_header is not None:
        raw["auth_header"] = auth_header or None
    if context_policy is not None:
        raw["context_policy"] = context_policy
    if timeout_seconds is not None:
        raw["timeout_seconds"] = timeout_seconds

    manifest = PluginManifest.model_validate(raw)
    if manifest.secret_id:
        get_secret(workspace_id, manifest.secret_id)
    normalized = manifest.model_dump(mode="json")
    execute(
        """
        UPDATE plugin_installations SET
            endpoint=:endpoint,network_scope=:network_scope,auth_type=:auth_type,
            auth_header=:auth_header,secret_id=:secret_id,context_policy=:context_policy,
            timeout_seconds=:timeout,manifest_json=:manifest,checksum=:checksum,
            enabled=:enabled,status=:status,last_error=NULL,updated_at=:now
        WHERE id=:id AND workspace_id=:ws
        """,
        {
            "endpoint": manifest.endpoint,
            "network_scope": manifest.network_scope,
            "auth_type": manifest.auth_type,
            "auth_header": manifest.auth_header,
            "secret_id": manifest.secret_id,
            "context_policy": manifest.context_policy,
            "timeout": manifest.timeout_seconds,
            "manifest": json_dumps(normalized),
            "checksum": _checksum(normalized),
            "enabled": 1 if manifest.enabled else 0,
            "status": "ready" if current.get("tool_count") else "needs_sync",
            "now": utcnow(),
            "id": plugin_id,
            "ws": workspace_id,
        },
    )
    record_event(
        "plugin.update",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="plugin",
        resource_id=plugin_id,
        payload={"enabled": manifest.enabled, "context_policy": manifest.context_policy},
    )
    return get_plugin(workspace_id, plugin_id)


def delete_plugin(actor_id: str, workspace_id: str, plugin_id: str) -> dict[str, Any]:
    plugin = get_plugin(workspace_id, plugin_id)
    execute(
        "DELETE FROM plugin_tools WHERE workspace_id=:ws AND plugin_id=:id",
        {"ws": workspace_id, "id": plugin_id},
    )
    execute(
        "DELETE FROM plugin_installations WHERE workspace_id=:ws AND id=:id",
        {"ws": workspace_id, "id": plugin_id},
    )
    record_event(
        "plugin.delete",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="plugin",
        resource_id=plugin_id,
        payload={"plugin_key": plugin["plugin_key"]},
    )
    return {"ok": True, "plugin_id": plugin_id}


def _replace_tool_cache(
    workspace_id: str,
    plugin_id: str,
    plugin_key: str,
    tools: list[PluginToolDefinition],
    *,
    protocol: str,
) -> None:
    execute(
        "DELETE FROM plugin_tools WHERE workspace_id=:ws AND plugin_id=:plugin",
        {"ws": workspace_id, "plugin": plugin_id},
    )
    now = utcnow()
    for tool in tools[:MAX_PLUGIN_TOOLS]:
        permissions = ["plugin:execute"] + [
            permission for permission in tool.required_permissions if permission != "plugin:execute"
        ]
        workspace_suffix = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:8]
        namespaced = f"plugin.{plugin_key}.{tool.name}__{workspace_suffix}"
        execute(
            """
            INSERT INTO plugin_tools(
                id,workspace_id,plugin_id,remote_name,namespaced_name,description,
                input_schema_json,declared_risk,required_permissions_json,
                requires_dataset,requires_model,http_method,http_path,metadata_json,
                enabled,created_at,updated_at
            ) VALUES(
                :id,:ws,:plugin,:remote,:namespaced,:description,:schema,:risk,
                :permissions,:requires_dataset,:requires_model,:method,:path,:metadata,
                1,:now,:now
            )
            """,
            {
                "id": str(uuid.uuid4()),
                "ws": workspace_id,
                "plugin": plugin_id,
                "remote": tool.name,
                "namespaced": namespaced,
                "description": tool.description or f"Tool {tool.name} fourni par plugin",
                "schema": json_dumps(tool.input_schema),
                "risk": tool.risk,
                "permissions": json_dumps(permissions),
                "requires_dataset": 1 if tool.requires_dataset else 0,
                "requires_model": 1 if tool.requires_model else 0,
                "method": tool.method if protocol == "http_json" else None,
                "path": tool.path if protocol == "http_json" else None,
                "metadata": json_dumps({
                    "origin": "plugin",
                    "protocol": protocol,
                    "declared_risk": tool.risk,
                    "remote_name": tool.name,
                }),
                "now": now,
            },
        )


def _plugin_headers(plugin: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "User-Agent": "DataVision-PluginHost/2.22",
    }
    auth_type = plugin.get("auth_type") or "none"
    secret_id = plugin.get("secret_id")
    if auth_type == "none":
        return headers
    if not secret_id:
        raise RuntimeError("Plugin configuré avec authentification mais sans secret_id.")
    secret = resolve_secret(plugin["workspace_id"], secret_id)
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {secret}"
    elif auth_type == "api_key":
        header = plugin.get("auth_header") or "X-API-Key"
        headers[header] = secret
    else:
        raise RuntimeError("auth_type plugin non supporté.")
    return headers


def _bounded_json_payload(payload: Any, *, max_bytes: int, label: str) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    if len(raw) > max_bytes:
        raise ValueError(f"{label} trop volumineux ({len(raw)} octets).")
    return raw


def _parse_http_payload(response: httpx.Response) -> Any:
    content = response.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Réponse plugin trop volumineuse.")
    content_type = (response.headers.get("content-type") or "").lower()
    if "text/event-stream" in content_type:
        data_lines = []
        for line in response.text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            return None
        for candidate in reversed(data_lines):
            if candidate == "[DONE]":
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise RuntimeError("Réponse MCP SSE sans payload JSON exploitable.")
    if not content:
        return None
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError("Le plugin n'a pas renvoyé de JSON valide.") from exc


def _request_plugin(
    plugin: dict[str, Any],
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[Any, httpx.Headers]:
    _validate_plugin_url(
        url,
        network_scope=plugin["network_scope"],
        resolve_dns=True,
    )
    headers = _plugin_headers(plugin)
    headers.update(extra_headers or {})
    if payload is not None:
        _bounded_json_payload(payload, max_bytes=MAX_REQUEST_BYTES, label="Requête plugin")
    timeout = httpx.Timeout(float(plugin.get("timeout_seconds") or 15), connect=8.0)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        with client.stream(
            method,
            url,
            json=payload if method != "GET" else None,
            params=params if method == "GET" else None,
            headers=headers,
        ) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise RuntimeError("Réponse plugin trop volumineuse.")
                chunks.append(chunk)
            bounded = httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
                request=response.request,
            )
            return _parse_http_payload(bounded), response.headers


def _mcp_rpc(
    plugin: dict[str, Any],
    *,
    rpc_method: str,
    params: dict[str, Any] | None = None,
    request_id: int | str | None = 1,
    session_id: str | None = None,
) -> tuple[Any, str | None]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": rpc_method,
    }
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    headers = {"Mcp-Session-Id": session_id} if session_id else {}
    result, response_headers = _request_plugin(
        plugin,
        method="POST",
        url=plugin["endpoint"],
        payload=payload,
        extra_headers=headers,
    )
    new_session = response_headers.get("mcp-session-id") or session_id
    if request_id is None:
        return result, new_session
    if not isinstance(result, dict):
        raise RuntimeError("Réponse MCP JSON-RPC invalide.")
    if result.get("error"):
        error = result["error"]
        raise RuntimeError(f"MCP {rpc_method} error: {error}")
    return result.get("result"), new_session


def _mcp_initialize(plugin: dict[str, Any]) -> str | None:
    manifest = plugin.get("manifest") or {}
    protocol_version = str(manifest.get("protocol_version") or "2025-03-26")
    _result, session = _mcp_rpc(
        plugin,
        rpc_method="initialize",
        params={
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "DataVision AI", "version": "2.23.0"},
        },
        request_id=1,
    )
    try:
        _mcp_rpc(
            plugin,
            rpc_method="notifications/initialized",
            params={},
            request_id=None,
            session_id=session,
        )
    except Exception:
        # Some compatible endpoints do not require the notification.
        pass
    return session


def test_plugin(workspace_id: str, plugin_id: str) -> dict[str, Any]:
    plugin = get_plugin(workspace_id, plugin_id)
    started = time.perf_counter()
    try:
        _validate_plugin_url(
            plugin["endpoint"],
            network_scope=plugin["network_scope"],
            resolve_dns=True,
        )
        if plugin["protocol"] == "mcp_http":
            session = _mcp_initialize(plugin)
            result, _ = _mcp_rpc(
                plugin,
                rpc_method="tools/list",
                params={},
                request_id=2,
                session_id=session,
            )
            tool_count = len((result or {}).get("tools") or []) if isinstance(result, dict) else 0
            network_verified = True
            status = "healthy"
        else:
            tool_count = len(plugin.get("tools") or [])
            health_path = str((plugin.get("manifest") or {}).get("health_path") or "").strip()
            if health_path:
                endpoint = plugin["endpoint"].rstrip("/") + "/"
                target = urljoin(endpoint, health_path.lstrip("/"))
                _payload, _headers = _request_plugin(
                    plugin,
                    method="GET",
                    url=target,
                )
                network_verified = True
                status = "healthy"
            else:
                network_verified = False
                status = "configured"
        duration = (time.perf_counter() - started) * 1000
        execute(
            "UPDATE plugin_installations SET status=:status,last_error=NULL,updated_at=:now WHERE id=:id",
            {"status": status, "now": utcnow(), "id": plugin_id},
        )
        return {
            "ok": True,
            "status": status,
            "tool_count": tool_count,
            "duration_ms": round(duration, 2),
            "network_verified": True if plugin["protocol"] == "mcp_http" else network_verified,
            "message": (
                None
                if plugin["protocol"] == "mcp_http" or network_verified
                else "Configuration validée, mais aucun health_path n'est défini: la connectivité HTTP n'a pas été affirmée."
            ),
        }
    except Exception as exc:
        error = str(exc)[:1000]
        execute(
            "UPDATE plugin_installations SET status='error',last_error=:error,updated_at=:now WHERE id=:id",
            {"error": error, "now": utcnow(), "id": plugin_id},
        )
        return {"ok": False, "status": "error", "error": error}


def sync_plugin(actor_id: str, workspace_id: str, plugin_id: str) -> dict[str, Any]:
    plugin = get_plugin(workspace_id, plugin_id)
    if plugin["protocol"] == "http_json":
        manifest = PluginManifest.model_validate(plugin["manifest"])
        _replace_tool_cache(workspace_id, plugin_id, plugin["plugin_key"], manifest.tools, protocol="http_json")
        synced_tools = len(manifest.tools)
    else:
        session = _mcp_initialize(plugin)
        result, _ = _mcp_rpc(
            plugin,
            rpc_method="tools/list",
            params={},
            request_id=2,
            session_id=session,
        )
        remote_tools = (result or {}).get("tools") if isinstance(result, dict) else None
        if not isinstance(remote_tools, list):
            raise RuntimeError("MCP tools/list n'a pas renvoyé de liste tools.")
        if len(remote_tools) > MAX_PLUGIN_TOOLS:
            raise RuntimeError(f"Le serveur MCP expose trop de tools ({len(remote_tools)} > {MAX_PLUGIN_TOOLS}).")
        tools: list[PluginToolDefinition] = []
        for raw in remote_tools:
            if not isinstance(raw, dict):
                continue
            schema = raw.get("inputSchema") or raw.get("input_schema") or {"type": "object", "properties": {}}
            tools.append(
                PluginToolDefinition(
                    name=str(raw.get("name") or ""),
                    description=str(raw.get("description") or ""),
                    input_schema=schema,
                    # Remote MCP risk claims are not trusted. The canonical runtime risk remains external.
                    risk="read",
                    required_permissions=[],
                    method="POST",
                    path="/",
                )
            )
        _replace_tool_cache(workspace_id, plugin_id, plugin["plugin_key"], tools, protocol="mcp_http")
        synced_tools = len(tools)

    now = utcnow()
    execute(
        "UPDATE plugin_installations SET status='ready',last_error=NULL,last_synced_at=:now,updated_at=:now WHERE id=:id",
        {"now": now, "id": plugin_id},
    )
    record_event(
        "plugin.sync",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="plugin",
        resource_id=plugin_id,
        payload={"tool_count": synced_tools, "protocol": plugin["protocol"]},
    )
    return get_plugin(workspace_id, plugin_id)


def _semantic_context(context: Any) -> dict[str, Any]:
    selected = getattr(context, "selectedEntity", None)
    return {
        "workspace_id": getattr(context, "workspaceId", None),
        "organization_id": getattr(context, "organizationId", None),
        "route": getattr(context, "route", None),
        "screen": getattr(context, "screen", None),
        "active_dataset_id": getattr(context, "activeDatasetId", None),
        "active_dataset_version_id": getattr(context, "activeDatasetVersionId", None),
        "active_model_id": getattr(context, "activeModelId", None),
        "active_chart_id": getattr(context, "activeChartId", None),
        "active_report_id": getattr(context, "activeReportId", None),
        "selected_entity": (
            selected.model_dump(mode="json")
            if selected is not None and hasattr(selected, "model_dump")
            else None
        ),
    }


def execute_plugin_tool(
    *,
    plugin_id: str,
    namespaced_name: str,
    context: Any,
    arguments: dict[str, Any],
) -> Any:
    workspace_id = getattr(context, "workspaceId", None)
    if not workspace_id:
        raise PermissionError("Les plugins externes nécessitent un workspace Enterprise actif.")
    plugin = get_plugin(workspace_id, plugin_id)
    if not plugin.get("enabled"):
        raise PermissionError("Plugin désactivé.")

    tool = fetch_one(
        "SELECT * FROM plugin_tools WHERE workspace_id=:ws AND plugin_id=:plugin AND namespaced_name=:name AND enabled=1",
        {"ws": workspace_id, "plugin": plugin_id, "name": namespaced_name},
    )
    if not tool:
        raise KeyError("Tool plugin introuvable ou désactivé.")
    tool = _tool_row(tool)

    payload: dict[str, Any] = {"arguments": dict(arguments)}
    if plugin.get("context_policy") == "semantic":
        payload["context"] = _semantic_context(context)
    _bounded_json_payload(payload, max_bytes=MAX_REQUEST_BYTES, label="Arguments plugin")

    access = current_access_context()
    user_id = getattr(access, "user_id", None) if access is not None else None
    run_id = str(uuid.uuid4())
    started_at = utcnow()
    execute(
        """
        INSERT INTO plugin_runs(id,workspace_id,plugin_id,tool_name,user_id,status,argument_keys_json,error,duration_ms,created_at,finished_at)
        VALUES(:id,:ws,:plugin,:tool,:user,'running',:keys,NULL,NULL,:created,NULL)
        """,
        {
            "id": run_id,
            "ws": workspace_id,
            "plugin": plugin_id,
            "tool": namespaced_name,
            "user": user_id,
            "keys": json_dumps(sorted(arguments.keys())),
            "created": started_at,
        },
    )
    started = time.perf_counter()
    try:
        if plugin["protocol"] == "http_json":
            endpoint = plugin["endpoint"].rstrip("/") + "/"
            target = urljoin(endpoint, str(tool.get("http_path") or "/").lstrip("/"))
            method = str(tool.get("http_method") or "POST").upper()
            if method == "GET":
                result, _headers = _request_plugin(
                    plugin,
                    method="GET",
                    url=target,
                    params=arguments,
                )
            else:
                body = dict(arguments)
                if plugin.get("context_policy") == "semantic":
                    body["_datavision_context"] = _semantic_context(context)
                result, _headers = _request_plugin(
                    plugin,
                    method="POST",
                    url=target,
                    payload=body,
                )
        elif plugin["protocol"] == "mcp_http":
            session = _mcp_initialize(plugin)
            result, _ = _mcp_rpc(
                plugin,
                rpc_method="tools/call",
                params={
                    "name": tool["remote_name"],
                    "arguments": arguments,
                },
                request_id=3,
                session_id=session,
            )
        else:
            raise RuntimeError("Protocole plugin non supporté.")

        _bounded_json_payload(result, max_bytes=MAX_RESPONSE_BYTES, label="Réponse plugin")
        duration = (time.perf_counter() - started) * 1000
        execute(
            "UPDATE plugin_runs SET status='succeeded',duration_ms=:duration,finished_at=:finished WHERE id=:id",
            {"duration": duration, "finished": utcnow(), "id": run_id},
        )
        record_event(
            "plugin.tool.execute",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="plugin_tool",
            resource_id=namespaced_name,
            payload={
                "plugin_id": plugin_id,
                "plugin_key": plugin["plugin_key"],
                "argument_keys": sorted(arguments.keys()),
                "duration_ms": round(duration, 2),
            },
        )
        return {
            "plugin": plugin["plugin_key"],
            "tool": tool["remote_name"],
            "protocol": plugin["protocol"],
            "result": result,
            "provenance": {
                "external": True,
                "endpoint_host": urlparse(plugin["endpoint"]).hostname,
                "plugin_version": plugin["version"],
                "manifest_checksum": plugin["checksum"],
            },
        }
    except Exception as exc:
        duration = (time.perf_counter() - started) * 1000
        error = str(exc)[:1000]
        execute(
            "UPDATE plugin_runs SET status='failed',error=:error,duration_ms=:duration,finished_at=:finished WHERE id=:id",
            {"error": error, "duration": duration, "finished": utcnow(), "id": run_id},
        )
        record_event(
            "plugin.tool.execute",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="plugin_tool",
            resource_id=namespaced_name,
            outcome="failed",
            payload={
                "plugin_id": plugin_id,
                "plugin_key": plugin["plugin_key"],
                "argument_keys": sorted(arguments.keys()),
                "error_type": type(exc).__name__,
            },
        )
        raise


def list_plugin_runs(workspace_id: str, plugin_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws": workspace_id, "limit": max(1, min(int(limit), 500))}
    clause = ""
    if plugin_id:
        clause = " AND plugin_id=:plugin"
        params["plugin"] = plugin_id
    rows = fetch_all(
        "SELECT * FROM plugin_runs WHERE workspace_id=:ws" + clause + " ORDER BY created_at DESC LIMIT :limit",
        params,
    )
    for row in rows:
        row["argument_keys"] = json_loads(row.pop("argument_keys_json", "[]"), [])
    return rows
