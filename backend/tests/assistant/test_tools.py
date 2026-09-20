import pytest

from app.assistant.tools import AssistantToolRegistry, ToolSpec, build_default_registry


def test_default_registry_has_core_tools():
    registry = build_default_registry()
    assert registry.get("profile_dataset") is not None
    assert registry.get("inspect_data_leakage") is not None
    assert registry.get("generate_report") is not None


def test_duplicate_tool_refused():
    registry = AssistantToolRegistry()
    spec = ToolSpec(name="x", description="x", category="test")
    registry.register(spec)
    with pytest.raises(ValueError):
        registry.register(spec)


def test_declared_without_handler_cannot_execute():
    registry = build_default_registry()
    with pytest.raises(RuntimeError):
        registry.execute("profile_dataset")


def test_executable_catalog_hides_declared_but_unbound_tools():
    registry = build_default_registry()
    registry.bind_handler("profile_dataset", lambda **kwargs: {"rows": 1})
    names = {spec.name for spec in registry.list_for_context(None, executable_only=True)}
    assert "profile_dataset" in names
    assert "gis_reproject" not in names
    assert registry.is_executable("profile_dataset") is True
    assert registry.is_executable("gis_reproject") is False
