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
