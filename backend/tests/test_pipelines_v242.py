import pandas as pd
import pytest

from app.core.config import get_settings
from app.services.pipelines import run_pipeline, save_lineage_as_pipeline, validate_pipeline
from app.services.preparation import apply_operation, combine_dataframes
from app.services.storage import (
    get_meta,
    list_versions,
    load_dataframe,
    save_dataframe_source,
    save_dataframe_version,
)


def _configure(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _combine_version(left_meta, right_meta):
    left = load_dataframe(left_meta["id"])
    right = load_dataframe(right_meta["id"])
    frame, operation = combine_dataframes(
        left,
        right,
        {"type": "merge", "left_on": ["id", "period"], "right_on": ["id", "period"], "how": "left"},
    )
    operation.setdefault("params", {})["other_dataset_id"] = right_meta["id"]
    operation["params"]["other_dataset_version"] = right_meta.get("version", 1)
    return save_dataframe_version(left_meta["id"], frame, operation)


def test_multidataset_pipeline_can_be_saved_validated_and_replayed(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    left = save_dataframe_source(pd.DataFrame({"id": [1, 2], "period": [1, 1], "x": [10.0, 20.0]}), "left.csv")
    right = save_dataframe_source(pd.DataFrame({"id": [1, 2], "period": [1, 1], "bonus": [5.0, 7.0]}), "right.csv")
    combined = _combine_version(left, right)
    frame, operation = apply_operation(load_dataframe(combined["id"]), {"type": "add_calculated_column", "new_name": "total", "expression": 'col("x") + col("bonus")'})
    final = save_dataframe_version(combined["id"], frame, operation)

    pipeline = save_lineage_as_pipeline(final["id"], "merge-and-feature")
    assert pipeline["multi_dataset"] is True
    assert pipeline["steps_count"] == 2
    assert pipeline["dependencies"][0]["dataset_id"] == right["id"]

    new_left = save_dataframe_source(pd.DataFrame({"id": [1, 2], "period": [1, 1], "x": [100.0, 200.0]}), "left-new.csv")
    check = validate_pipeline(new_left["id"], pipeline["id"])
    assert check["valid"] is True
    assert check["steps_count"] == 2
    assert len(list_versions(new_left["id"])) == 1  # validation never persists

    result = run_pipeline(new_left["id"], pipeline["id"])
    replayed = load_dataframe(result["dataset_id"])
    assert replayed["total"].tolist() == [105.0, 207.0]
    assert result["validation"]["status"] == "pass"
    assert len(result["executed"]) == 2


def test_pipeline_binding_can_replace_secondary_dataset(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    left = save_dataframe_source(pd.DataFrame({"id": [1, 2], "period": [1, 1], "x": [10.0, 20.0]}), "left.csv")
    right = save_dataframe_source(pd.DataFrame({"id": [1, 2], "period": [1, 1], "bonus": [1.0, 2.0]}), "right.csv")
    combined = _combine_version(left, right)
    pipeline = save_lineage_as_pipeline(combined["id"], "replaceable-dependency")

    replacement = save_dataframe_source(pd.DataFrame({"id": [1, 2], "period": [1, 1], "bonus": [50.0, 70.0]}), "right-v2.csv")
    dependency_root = pipeline["dependencies"][0]["root_id"]
    result = run_pipeline(left["id"], pipeline["id"], {dependency_root: replacement["id"]})
    replayed = load_dataframe(result["dataset_id"])
    assert replayed["bonus"].tolist() == [50.0, 70.0]
    assert result["bindings"][dependency_root] == replacement["id"]
    op = get_meta(result["dataset_id"])["operation"]
    assert op["params"]["other_dataset_id"] == replacement["id"]


def test_pipeline_preflight_prevents_partial_versions_on_late_failure(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    source = save_dataframe_source(pd.DataFrame({"x": [1, 2], "z": [3, 4]}), "source.csv")
    first_frame, first_op = apply_operation(load_dataframe(source["id"]), {"type": "rename_column", "column": "x", "new_name": "y"})
    first = save_dataframe_version(source["id"], first_frame, first_op)
    second_frame, second_op = apply_operation(load_dataframe(first["id"]), {"type": "rename_column", "column": "z", "new_name": "w"})
    second = save_dataframe_version(first["id"], second_frame, second_op)
    pipeline = save_lineage_as_pipeline(second["id"], "two-renames")

    incompatible = save_dataframe_source(pd.DataFrame({"x": [10, 20]}), "incompatible.csv")
    assert len(list_versions(incompatible["id"])) == 1
    with pytest.raises(ValueError, match="Colonne introuvable: z"):
        run_pipeline(incompatible["id"], pipeline["id"])
    assert len(list_versions(incompatible["id"])) == 1
