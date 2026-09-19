from pathlib import Path

from app.assistant.models import AssistantContext
from app.assistant.tools import ToolSpec, AssistantToolRegistry

ROOT = Path(__file__).resolve().parents[2]


def test_plugin_tables_are_migrations_in_metadata_store():
    text = (ROOT / "backend/app/services/metadata_store.py").read_text()
    for table in ("plugin_installations", "plugin_tools", "plugin_runs"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text


def test_plugin_enterprise_routes_and_permissions_exist():
    routes = (ROOT / "backend/app/api/routes/enterprise.py").read_text()
    auth = (ROOT / "backend/app/services/auth_service.py").read_text()
    assert '/workspaces/{workspace_id}/plugins' in routes
    assert '/plugins/{plugin_id}/sync' in routes
    assert '/plugins/{plugin_id}/test' in routes
    assert 'plugins:manage' in auth
    assert 'plugins:execute' in auth


def test_frontend_plugin_center_is_integrated():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()
    assert "plugins:'Plugins & MCP'" in page
    assert "<PluginCenter" in page
    assert "Plugin System · MCP" in page or "PLUGIN SYSTEM · MCP" in page
    assert "Tout tool distant est classé" in page
    for fn in (
        "getWorkspacePlugins",
        "installWorkspacePlugin",
        "updateWorkspacePlugin",
        "deleteWorkspacePlugin",
        "testWorkspacePlugin",
        "syncWorkspacePlugin",
    ):
        assert fn in api


def test_registry_can_filter_plugin_specs_by_workspace():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="builtin",
            description="builtin",
            category="data",
        )
    )
    registry.register(
        ToolSpec(
            name="plugin.demo.x__aaaa",
            description="plugin",
            category="plugin",
            risk="external",
            metadata={"origin": "plugin", "workspace_id": "ws-a"},
        )
    )
    a = {x.name for x in registry.list_for_context(AssistantContext(workspaceId="ws-a"))}
    b = {x.name for x in registry.list_for_context(AssistantContext(workspaceId="ws-b"))}
    local = {x.name for x in registry.list_for_context(None)}
    assert a == {"builtin", "plugin.demo.x__aaaa"}
    assert b == {"builtin"}
    assert local == {"builtin"}
