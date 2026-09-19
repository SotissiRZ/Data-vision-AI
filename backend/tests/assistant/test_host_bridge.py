from app.assistant.host_bridge import DataVisionHostBridges, bind_registry_to_host
from app.assistant.models import AssistantContext
from app.assistant.tools import build_default_registry


class FakeDataBridge:
    def profile_dataset(self, *, context: AssistantContext, **kwargs):
        return {"dataset": context.activeDatasetId, "rows": 42}

    def inspect_missing_values(self, *, context: AssistantContext, **kwargs):
        return {"missing": 0}

    def apply_reversible_transform(self, *, context: AssistantContext, **kwargs):
        return {"ok": True, "rollback_token": "version_1"}

    def merge_datasets(self, *, context: AssistantContext, **kwargs):
        return {"ok": True}

    def delete_column(self, *, context: AssistantContext, **kwargs):
        return {"ok": True}


def test_bind_real_handler_contract():
    registry = build_default_registry()
    bind_registry_to_host(
        registry,
        DataVisionHostBridges(data=FakeDataBridge()),
    )
    assert registry.has_handler("profile_dataset")
    result = registry.execute(
        "profile_dataset",
        context=AssistantContext(activeDatasetId="ds_1"),
    )
    assert result["rows"] == 42
