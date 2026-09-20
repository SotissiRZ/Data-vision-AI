import pandas as pd
import pytest

from app.core.config import get_settings
from app.services.preparation import apply_operation, combine_dataframes


def _frame():
    return pd.DataFrame(
        {
            "id": [2, 1, 3, 4, 5, 6],
            "group": ["A", "A", "A", "B", "B", "B"],
            "time": pd.to_datetime([
                "2026-01-02", "2026-01-01", "2026-01-03",
                "2026-01-01", "2026-01-03", "2026-01-02",
            ]),
            "value": [20.0, 10.0, 30.0, 100.0, 300.0, 200.0],
            "score": [2.0, 1.0, 3.0, 10.0, 30.0, 20.0],
        }
    )


def test_bin_numeric_quantiles_is_replayable():
    out, operation = apply_operation(
        _frame(),
        {"type": "bin_numeric", "column": "value", "new_name": "value_band", "method": "quantile", "bins": 3},
    )
    assert "value_band" in out.columns
    assert out["value_band"].nunique(dropna=True) == 3
    assert operation["params"]["method"] == "quantile"
    replayed, _ = apply_operation(_frame(), {"type": "bin_numeric", **operation["params"]})
    assert replayed["value_band"].astype(str).tolist() == out["value_band"].astype(str).tolist()


def test_lag_feature_grouped_and_ordered_preserves_original_row_order():
    source = _frame()
    out, operation = apply_operation(
        source,
        {
            "type": "lag_feature",
            "column": "value",
            "new_name": "previous_value",
            "periods": 1,
            "group_by": ["group"],
            "order_by": "time",
        },
    )
    assert out["id"].tolist() == source["id"].tolist()
    by_id = out.set_index("id")["previous_value"].to_dict()
    assert pd.isna(by_id[1])
    assert by_id[2] == 10.0
    assert by_id[3] == 20.0
    assert pd.isna(by_id[4])
    assert by_id[6] == 100.0
    assert by_id[5] == 200.0
    assert operation["params"]["group_by"] == ["group"]


def test_rolling_feature_grouped_and_ordered():
    out, operation = apply_operation(
        _frame(),
        {
            "type": "rolling_feature",
            "column": "value",
            "new_name": "rolling_2",
            "window": 2,
            "min_periods": 1,
            "function": "mean",
            "group_by": ["group"],
            "order_by": "time",
        },
    )
    by_id = out.set_index("id")["rolling_2"].to_dict()
    assert by_id[1] == 10.0
    assert by_id[2] == 15.0
    assert by_id[3] == 25.0
    assert by_id[4] == 100.0
    assert by_id[6] == 150.0
    assert by_id[5] == 250.0
    assert operation["params"]["function"] == "mean"


def test_groupby_supports_multiple_aggregations():
    out, _ = apply_operation(
        _frame(),
        {
            "type": "groupby_aggregate",
            "group_by": ["group"],
            "aggregations": [
                {"column": "value", "function": "sum", "alias": "value_sum"},
                {"column": "score", "function": "mean", "alias": "score_mean"},
            ],
        },
    )
    row_a = out.set_index("group").loc["A"]
    assert row_a["value_sum"] == 60.0
    assert row_a["score_mean"] == 2.0


def test_multikey_merge_and_concat_are_deterministic():
    left = pd.DataFrame({"id": [1, 1, 2], "period": [1, 2, 1], "x": [10, 20, 30]})
    right = pd.DataFrame({"id": [1, 1, 2], "period": [1, 2, 1], "y": [100, 200, 300]})
    merged, operation = combine_dataframes(
        left,
        right,
        {"type": "merge", "left_on": ["id", "period"], "right_on": ["id", "period"], "how": "inner"},
    )
    assert merged["y"].tolist() == [100, 200, 300]
    assert operation["params"]["left_on"] == ["id", "period"]
    rows, _ = combine_dataframes(left, right.rename(columns={"y": "x"}), {"type": "concat_rows", "join": "outer"})
    assert len(rows) == 6


def test_feature_engineering_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        apply_operation(_frame(), {"type": "bin_numeric", "column": "value", "bins": 1})
    with pytest.raises(ValueError):
        apply_operation(_frame(), {"type": "lag_feature", "column": "value", "periods": 0})
    with pytest.raises(ValueError):
        apply_operation(_frame(), {"type": "rolling_feature", "column": "value", "window": 1})
