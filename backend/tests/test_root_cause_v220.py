import numpy as np
import pandas as pd

from app.services.root_cause import root_cause_analysis


def frame():
    return pd.DataFrame(
        {
            "period": ["A"] * 8 + ["B"] * 8,
            "region": (
                ["North"] * 4
                + ["South"] * 4
                + ["North"] * 4
                + ["South"] * 4
            ),
            "channel": [
                "web", "web", "store", "store",
                "web", "web", "store", "store",
                "web", "web", "store", "store",
                "web", "web", "store", "store",
            ],
            "sales": [
                10, 10, 10, 10,
                20, 20, 20, 20,
                15, 15, 15, 15,
                25, 25, 25, 25,
            ],
            "driver": [
                1.0, 1.5, 0.8, 1.2,
                2.0, 1.8, 2.2, 2.1,
                2.0, 2.6, 1.9, 2.3,
                3.2, 3.0, 3.4, 3.1,
            ],
        }
    )


def test_mean_decomposition_reconciles_overall_gap():
    result = root_cause_analysis(
        frame(),
        target="sales",
        comparison_column="period",
        baseline_value="A",
        current_value="B",
        metric="mean",
        dimensions=["region"],
        min_segment_size=1,
    )

    assert result["baseline"]["metric"] == 15.0
    assert result["current"]["metric"] == 20.0
    assert result["delta"] == 5.0

    decomposition = result["dimension_decompositions"][0]
    assert decomposition["dimension"] == "region"
    assert abs(decomposition["net_contribution"] - 5.0) < 1e-8
    assert abs(decomposition["reconciliation_error"]) < 1e-8
    assert len(decomposition["top_segments"]) == 2


def test_sum_decomposition_is_exact_by_segment():
    result = root_cause_analysis(
        frame(),
        target="sales",
        comparison_column="period",
        baseline_value="A",
        current_value="B",
        metric="sum",
        dimensions=["region"],
        min_segment_size=1,
    )
    decomposition = result["dimension_decompositions"][0]
    assert result["delta"] == 40.0
    assert abs(decomposition["net_contribution"] - 40.0) < 1e-8


def test_auto_comparison_uses_last_two_values():
    result = root_cause_analysis(
        frame(),
        target="sales",
        comparison_column="period",
        metric="mean",
        dimensions=["region"],
        min_segment_size=1,
    )
    assert result["baseline"]["value"] == "A"
    assert result["current"]["value"] == "B"


def test_feature_shifts_and_review_priorities_are_reported():
    result = root_cause_analysis(
        frame(),
        target="sales",
        comparison_column="period",
        metric="mean",
        dimensions=["region", "channel"],
        min_segment_size=1,
    )
    names = {row["feature"] for row in result["feature_shifts"]}
    assert "driver" in names
    assert result["review_priorities"]
    assert result["evidence_strength"]["level"] in {"low", "medium", "high"}
    assert result["interpretation_policy"] == (
        "descriptive_root_cause_candidates_not_causal_proof"
    )
    assert "ne démontre pas" in result["caveat"]


def test_unknown_target_is_rejected():
    try:
        root_cause_analysis(
            frame(),
            target="missing",
            comparison_column="period",
        )
    except ValueError as exc:
        assert "Variable cible inconnue" in str(exc)
    else:
        raise AssertionError("Unknown target should fail.")



def test_date_comparison_is_aggregated_by_month():
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    frame_dates = pd.DataFrame(
        {
            "date": dates,
            "segment": ["A", "B"] * 40,
            "sales": (
                [10.0] * 31
                + [20.0] * 28
                + [30.0] * 21
            ),
        }
    )

    result = root_cause_analysis(
        frame_dates,
        target="sales",
        comparison_column="date",
        metric="mean",
        dimensions=["segment"],
        time_grain="month",
        min_segment_size=1,
    )

    assert result["comparison_time_grain"] == "month"
    assert result["baseline"]["value"] == "2026-02"
    assert result["current"]["value"] == "2026-03"
    assert result["baseline"]["rows"] == 28
    assert result["current"]["rows"] == 21
