import pandas as pd

from app.core.config import get_settings
from app.services.metadata_store import fetch_all
from app.services.model_registry import (
    register_model,
    transition_model,
)
from app.services.model_serving import (
    batch_score_dataset,
    create_deployment,
    deployment_metrics,
    rollback_deployment,
    score_deployment,
    update_deployment,
)
from app.services.modeling import train_model
from app.services.storage import (
    load_dataframe,
    save_dataframe_source,
)


def _configure(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(
        settings,
        "database_url",
        f"sqlite:///{tmp_path / 'metadata.db'}",
    )
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _frame():
    rows = 80
    x = list(range(rows))
    return pd.DataFrame(
        {
            "x": x,
            "z": [value % 7 for value in x],
            "target": [2.5 * value + (value % 7) + 3 for value in x],
        }
    )


def _trained_pair(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    frame = _frame()
    source = save_dataframe_source(frame, "train.csv")
    context = {
        "id": source["id"],
        "root_id": source["id"],
        "version": 1,
        "name": "train.csv",
    }
    first = train_model(
        frame,
        "target",
        task="regression",
        algorithm="linear_regression",
        dataset_context=context,
    )
    second = train_model(
        frame,
        "target",
        task="regression",
        algorithm="ridge",
        dataset_context=context,
    )
    for model in (first, second):
        register_model(
            "__local_user__",
            "__local__",
            model.model_id,
        )
        transition_model(
            "__local_user__",
            "__local__",
            model.model_id,
            target_stage="staging",
        )
    transition_model(
        "__local_user__",
        "__local__",
        first.model_id,
        target_stage="production",
    )
    return frame, source, first, second


def test_shadow_serving_logs_only_summary(
    tmp_path,
    monkeypatch,
):
    _frame_data, _source, first, second = _trained_pair(
        tmp_path,
        monkeypatch,
    )
    deployment = create_deployment(
        "__local_user__",
        "__local__",
        name="sales-api",
        endpoint_key="sales-api",
        primary_model_id=first.model_id,
        strategy="shadow",
        secondary_model_id=second.model_id,
    )
    result = score_deployment(
        "__local__",
        "sales-api",
        [{"x": "10", "z": 3}, {"x": 20, "z": 6}],
        request_id="request-1",
    )
    assert result["model_used"] == first.model_id
    assert len(result["predictions"]) == 2
    assert result["shadow"]["rows_compared"] == 2
    assert result["serving_backend"] == "datavision_internal"

    metrics = deployment_metrics(
        "__local__",
        deployment["id"],
    )
    assert metrics["requests"] == 1
    assert metrics["rows_scored"] == 2
    rows = fetch_all("SELECT * FROM model_serving_requests")
    assert len(rows) == 1
    assert '"x"' not in rows[0]["summary_json"]
    assert '"z"' not in rows[0]["summary_json"]


def test_canary_routing_is_deterministic(
    tmp_path,
    monkeypatch,
):
    _frame_data, _source, first, second = _trained_pair(
        tmp_path,
        monkeypatch,
    )
    create_deployment(
        "__local_user__",
        "__local__",
        name="canary",
        endpoint_key="canary",
        primary_model_id=first.model_id,
        strategy="canary",
        secondary_model_id=second.model_id,
        traffic_percent=50,
    )
    left = score_deployment(
        "__local__",
        "canary",
        [{"x": 10, "z": 3}],
        request_id="stable-request",
    )
    right = score_deployment(
        "__local__",
        "canary",
        [{"x": 10, "z": 3}],
        request_id="stable-request",
    )
    assert left["model_used"] == right["model_used"]


def test_champion_switch_and_governed_rollback(
    tmp_path,
    monkeypatch,
):
    _frame_data, _source, first, second = _trained_pair(
        tmp_path,
        monkeypatch,
    )
    deployment = create_deployment(
        "__local_user__",
        "__local__",
        name="prod",
        endpoint_key="prod",
        primary_model_id=first.model_id,
    )

    transition_model(
        "__local_user__",
        "__local__",
        second.model_id,
        target_stage="production",
    )
    switched = update_deployment(
        "__local_user__",
        "__local__",
        deployment["id"],
        primary_model_id=second.model_id,
        strategy="champion",
        reason="new_champion",
    )
    assert switched["primary_model_id"] == second.model_id
    assert switched["revision_no"] == 2

    restored = rollback_deployment(
        "__local_user__",
        "__local__",
        deployment["id"],
    )
    assert restored["primary_model_id"] == first.model_id
    assert restored["revision_no"] == 3


def test_batch_scoring_creates_new_dataset_version(
    tmp_path,
    monkeypatch,
):
    frame, source, first, _second = _trained_pair(
        tmp_path,
        monkeypatch,
    )
    result = batch_score_dataset(
        "__local_user__",
        "__local__",
        model_id=first.model_id,
        dataset_id=source["id"],
        prediction_column="score",
    )
    scored = load_dataframe(result["output_dataset"]["id"])
    assert len(scored) == len(frame)
    assert "score" in scored.columns
    assert result["output_dataset"]["parent_id"] == source["id"]
