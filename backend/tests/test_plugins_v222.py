from __future__ import annotations

from pathlib import Path

import pytest

from app.assistant.executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from app.assistant.models import AssistantAction, AssistantContext
from app.assistant.plugin_runtime import attach_plugin_registry, refresh_runtime_plugins
from app.assistant.tools import build_default_registry
from app.core.config import get_settings
from app.services.plugin_service import (
    PluginManifest,
    delete_plugin,
    get_plugin,
    install_plugin,
    list_plugin_runs,
    sync_plugin,
    test_plugin as probe_plugin,
    update_plugin,
)


def _use_sqlite_metadata(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _http_manifest(key="demo", endpoint="https://plugins.example.com/api"):
    return {
        "plugin_key": key,
        "name": "Demo Plugin",
        "version": "1.0.0",
        "description": "Plugin test",
        "protocol": "http_json",
        "endpoint": endpoint,
        "network_scope": "public",
        "auth_type": "none",
        "context_policy": "none",
        "tools": [
            {
                "name": "lookup",
                "description": "Lookup externe",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "token": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "risk": "read",
                "required_permissions": [],
                "method": "POST",
                "path": "/lookup",
            }
        ],
    }


def test_manifest_forbids_raw_secret_but_allows_schema_field_named_token():
    manifest = PluginManifest.model_validate(_http_manifest())
    assert manifest.tools[0].input_schema["properties"]["token"]["type"] == "string"

    raw = _http_manifest()
    raw["token"] = "should-not-be-here"
    with pytest.raises(Exception):
        PluginManifest.model_validate(raw)


def test_public_plugins_require_https_but_private_http_is_explicitly_supported():
    raw = _http_manifest(endpoint="http://plugins.example.com")
    with pytest.raises(ValueError):
        PluginManifest.model_validate(raw)

    raw["network_scope"] = "private"
    raw["endpoint"] = "http://10.0.0.12:8080/api"
    manifest = PluginManifest.model_validate(raw)
    assert manifest.network_scope == "private"


def test_http_plugin_registers_external_tenant_scoped_tool(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    plugin = install_plugin("u1", "workspace-a", _http_manifest())
    assert plugin["status"] == "ready"
    assert plugin["tool_count"] == 1
    tool = plugin["tools"][0]
    assert tool["namespaced_name"].startswith("plugin.demo.lookup__")

    registry = build_default_registry()
    attach_plugin_registry(registry)
    refresh_runtime_plugins()
    visible = registry.list_for_context(AssistantContext(workspaceId="workspace-a"))
    plugin_specs = [item for item in visible if item.metadata.get("origin") == "plugin"]
    assert len(plugin_specs) == 1
    spec = plugin_specs[0]
    assert spec.risk == "external"
    assert spec.metadata["declared_risk"] == "read"
    assert spec.input_schema["required"] == ["query"]
    assert "plugin:execute" in spec.required_permissions

    hidden = registry.list_for_context(AssistantContext(workspaceId="workspace-b"))
    assert not [item for item in hidden if item.metadata.get("origin") == "plugin"]


def test_same_plugin_key_is_unique_per_workspace_and_runtime_names_do_not_collide(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    a = install_plugin("u1", "workspace-a", _http_manifest(key="shared"))
    b = install_plugin("u2", "workspace-b", _http_manifest(key="shared"))
    assert a["tools"][0]["namespaced_name"] != b["tools"][0]["namespaced_name"]

    registry = build_default_registry()
    attach_plugin_registry(registry)
    refresh_runtime_plugins()
    a_tools = [x for x in registry.list_for_context(AssistantContext(workspaceId="workspace-a")) if x.metadata.get("origin") == "plugin"]
    b_tools = [x for x in registry.list_for_context(AssistantContext(workspaceId="workspace-b")) if x.metadata.get("origin") == "plugin"]
    assert len(a_tools) == 1
    assert len(b_tools) == 1
    assert a_tools[0].name != b_tools[0].name


def test_dynamic_json_schema_and_confirmation_gate(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    plugin = install_plugin("u1", "workspace-a", _http_manifest())
    registry = build_default_registry()
    attach_plugin_registry(registry)
    refresh_runtime_plugins()
    name = plugin["tools"][0]["namespaced_name"]
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    context = AssistantContext(workspaceId="workspace-a")

    invalid = executor.prepare(
        AssistantAction(tool=name, label="Lookup", args={}, risk="read"),
        context,
    )
    assert invalid.status == "deny"
    assert "Arguments invalides" in invalid.reason

    ready = executor.prepare(
        AssistantAction(tool=name, label="Lookup", args={"query": "sales"}, risk="read"),
        context,
    )
    assert ready.status == "confirmation_required"
    assert ready.tool.risk == "external"

    wrong_workspace = executor.prepare(
        AssistantAction(tool=name, label="Lookup", args={"query": "sales"}, risk="external"),
        AssistantContext(workspaceId="workspace-b"),
    )
    assert wrong_workspace.status == "deny"
    assert "workspace" in wrong_workspace.reason.lower()


def test_confirmed_http_plugin_executes_without_persisting_argument_values(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    import app.services.plugin_service as service

    plugin = install_plugin("u1", "workspace-a", _http_manifest())
    registry = build_default_registry()
    attach_plugin_registry(registry)
    refresh_runtime_plugins()
    tool_name = plugin["tools"][0]["namespaced_name"]

    def fake_request(plugin, *, method, url, payload=None, params=None, extra_headers=None):
        assert method == "POST"
        assert url.endswith("/api/lookup")
        assert payload["query"] == "quarterly sales"
        return {"items": [1, 2, 3]}, {}

    monkeypatch.setattr(service, "_request_plugin", fake_request)
    executor = GovernedToolExecutor(registry, AllowAllDevelopmentAuthorization())
    decision = executor.execute(
        AssistantAction(
            tool=tool_name,
            label="Lookup",
            args={"query": "quarterly sales"},
            risk="read",
        ),
        AssistantContext(workspaceId="workspace-a"),
        confirmed=True,
    )
    assert decision.status == "executed"
    assert decision.result["result"]["items"] == [1, 2, 3]

    runs = list_plugin_runs("workspace-a")
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["argument_keys"] == ["query"]
    assert "quarterly sales" not in str(runs[0])


def test_mcp_sync_uses_remote_tools_list_but_runtime_risk_stays_external(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    import app.services.plugin_service as service

    plugin = install_plugin(
        "u1",
        "workspace-a",
        {
            "plugin_key": "mcpdemo",
            "name": "MCP Demo",
            "version": "1.0.0",
            "protocol": "mcp_http",
            "endpoint": "https://mcp.example.com/mcp",
            "network_scope": "public",
            "auth_type": "none",
            "context_policy": "none",
            "tools": [],
        },
    )
    assert plugin["status"] == "needs_sync"

    monkeypatch.setattr(service, "_mcp_initialize", lambda plugin: "session-1")

    def fake_rpc(plugin, *, rpc_method, params=None, request_id=1, session_id=None):
        assert rpc_method == "tools/list"
        return {
            "tools": [
                {
                    "name": "find_customer",
                    "description": "Find customer",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"customer_id": {"type": "string"}},
                        "required": ["customer_id"],
                        "additionalProperties": False,
                    },
                }
            ]
        }, session_id

    monkeypatch.setattr(service, "_mcp_rpc", fake_rpc)
    synced = sync_plugin("u1", "workspace-a", plugin["id"])
    assert synced["status"] == "ready"
    assert synced["tool_count"] == 1

    registry = build_default_registry()
    attach_plugin_registry(registry)
    refresh_runtime_plugins()
    specs = [x for x in registry.list_for_context(AssistantContext(workspaceId="workspace-a")) if x.metadata.get("origin") == "plugin"]
    assert len(specs) == 1
    assert specs[0].risk == "external"
    assert specs[0].input_schema["required"] == ["customer_id"]


def test_http_plugin_probe_without_health_path_does_not_claim_network_verification(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    import app.services.plugin_service as service

    plugin = install_plugin("u1", "workspace-a", _http_manifest())
    monkeypatch.setattr(service, "_validate_plugin_url", lambda *args, **kwargs: None)
    result = probe_plugin("workspace-a", plugin["id"])
    assert result["ok"] is True
    assert result["status"] == "configured"
    assert result["network_verified"] is False
    assert "n'a pas été affirmée" in result["message"]


def test_plugin_can_be_disabled_and_deleted(tmp_path, monkeypatch):
    _use_sqlite_metadata(tmp_path, monkeypatch)
    plugin = install_plugin("u1", "workspace-a", _http_manifest())
    disabled = update_plugin("u1", "workspace-a", plugin["id"], enabled=False)
    assert disabled["enabled"] is False
    result = delete_plugin("u1", "workspace-a", plugin["id"])
    assert result["ok"] is True
    with pytest.raises(KeyError):
        get_plugin("workspace-a", plugin["id"])


def test_endpoint_query_strings_are_rejected():
    raw = _http_manifest(endpoint="https://plugins.example.com/api?token=secret")
    with pytest.raises(ValueError):
        PluginManifest.model_validate(raw)
