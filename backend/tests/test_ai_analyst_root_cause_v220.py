import pandas as pd

from app.services.ai_analyst import (
    AnalystContext,
    analyze_dataset,
    detect_intent,
    tool_registry,
)


def dataset():
    return pd.DataFrame(
        {
            "period": ["2026-01"] * 30 + ["2026-02"] * 30,
            "region": ["North"] * 15 + ["South"] * 15
            + ["North"] * 15 + ["South"] * 15,
            "sales": [10.0] * 15 + [20.0] * 15
            + [14.0] * 15 + [24.0] * 15,
            "cost": [4.0] * 30 + [5.0] * 30,
        }
    )


def test_ai_analyst_detects_root_cause_before_regression():
    assert detect_intent(
        "Pourquoi sales a augmenté ? Analyse les causes."
    ) == "root_cause"


def test_ai_analyst_root_cause_executes_deterministic_tool():
    df = dataset()
    result = analyze_dataset(
        df,
        AnalystContext(
            dataset={
                "id": "ds1",
                "name": "sales.csv",
                "version": 1,
            },
            question=(
                "Pourquoi sales a augmenté entre les périodes ? "
                "Analyse les causes."
            ),
            target="sales",
            date_column="period",
        ),
    )

    assert result["intent"] == "root_cause"
    assert "root_cause" in result["artifacts"]
    assert any(
        item["tool"] == "root_cause"
        and item["status"] == "ok"
        for item in result["executions"]
    )
    assert result["provenance"]["llm_used_for_numeric_calculation"] is False


def test_ai_analyst_registry_lists_root_cause():
    rows = tool_registry()
    assert any(
        item["name"] == "root_cause"
        and item["status"] == "implemented"
        for item in rows
    )
