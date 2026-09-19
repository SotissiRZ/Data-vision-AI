from __future__ import annotations

from functools import partial
from typing import Any

from app.services.plugin_service import (
    execute_plugin_tool,
    list_enabled_runtime_tools,
)

from .tools import AssistantToolRegistry, ToolSpec


_registry: AssistantToolRegistry | None = None


def attach_plugin_registry(registry: AssistantToolRegistry) -> None:
    global _registry
    _registry = registry


def safe_refresh_runtime_plugins() -> int:
    try:
        return refresh_runtime_plugins()
    except Exception:
        # Startup/import must never fail only because the metadata backend or
        # an optional plugin registry is temporarily unavailable. Enterprise
        # requests can retry the refresh once their auth/metadata context exists.
        return 0


def refresh_runtime_plugins() -> int:
    if _registry is None:
        return 0

    for spec in list(_registry.list()):
        if spec.metadata.get("origin") == "plugin":
            _registry.unregister(spec.name)

    count = 0
    for row in list_enabled_runtime_tools():
        metadata = dict(row.get("metadata") or {})
        metadata.update(
            {
                "origin": "plugin",
                "plugin_id": row["plugin_id"],
                "workspace_id": row.get("workspace_id"),
                "plugin_key": row.get("plugin_key"),
                "plugin_name": row.get("plugin_name"),
                "plugin_version": row.get("plugin_version"),
                "protocol": row.get("protocol"),
                "declared_risk": row.get("declared_risk"),
                "external_endpoint": True,
                "human_confirmation_required": True,
            }
        )

        # Any remote plugin call is canonically external. A plugin cannot lower
        # its own risk classification through its manifest.
        spec = ToolSpec(
            name=row["namespaced_name"],
            description=row["description"],
            category="plugin",
            risk="external",
            required_permissions=tuple(row.get("required_permissions") or ["plugin:execute"]),
            requires_dataset=bool(row.get("requires_dataset")),
            requires_model=bool(row.get("requires_model")),
            deterministic=False,
            input_schema=row.get("input_schema") or {"type": "object", "properties": {}},
            metadata=metadata,
        )

        handler = partial(
            _execute_bound_plugin_tool,
            plugin_id=row["plugin_id"],
            namespaced_name=row["namespaced_name"],
        )
        _registry.register(spec, handler=handler, replace=True)
        count += 1
    return count


def _execute_bound_plugin_tool(
    *,
    plugin_id: str,
    namespaced_name: str,
    context: Any,
    **kwargs: Any,
) -> Any:
    return execute_plugin_tool(
        plugin_id=plugin_id,
        namespaced_name=namespaced_name,
        context=context,
        arguments=kwargs,
    )
