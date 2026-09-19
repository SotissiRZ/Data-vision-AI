import pytest
from pydantic import ValidationError

from app.assistant.contracts import (
    validate_tool_arguments,
    tool_json_schema,
)


def test_automl_requires_target_for_supervised_task():
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "run_automl",
            {"task": "classification"},
        )


def test_valid_automl_contract():
    args = validate_tool_arguments(
        "run_automl",
        {
            "task": "classification",
            "target": "churn",
            "max_models": 5,
        },
    )
    assert args["target"] == "churn"
    assert args["max_models"] == 5


def test_spatial_join_contract():
    args = validate_tool_arguments(
        "gis_spatial_join",
        {
            "left_layer_id": "districts",
            "right_layer_id": "restaurants",
            "predicate": "within",
        },
    )
    assert args["predicate"] == "within"


def test_merge_keys_must_match():
    with pytest.raises(ValidationError):
        validate_tool_arguments(
            "merge_datasets",
            {
                "right_dataset_id": "ds2",
                "left_on": ["id", "date"],
                "right_on": ["id"],
            },
        )


def test_tool_schema_exposed():
    schema = tool_json_schema("run_statistical_test")
    assert schema is not None
    assert "properties" in schema
