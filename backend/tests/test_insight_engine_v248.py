from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.insight_engine import generate_insights, insight_history
from app.services.storage import save_dataframe_source, save_dataframe_version


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates1 = pd.date_range("2024-01-01", periods=24, freq="MS")
    x1 = np.arange(1, 25, dtype=float)
    v1 = pd.DataFrame({
        "date": dates1,
        "region": ["North"] * 18 + ["South"] * 6,
        "sales": x1 * 10.0,
        "margin": x1 * 5.0 + np.sin(x1),
    })
    dates2 = pd.date_range("2024-01-01", periods=30, freq="MS")
    x2 = np.arange(1, 31, dtype=float)
    sales = x2 * 13.0
    sales[-1] = 2000.0
    v2 = pd.DataFrame({
        "date": dates2,
        "region": ["North"] * 24 + ["South"] * 6,
        "sales": sales,
        "margin": x2 * 6.5 + np.sin(x2),
    })
    return v1, v2


def test_v248_engine_detects_ranked_multicategory_insights(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    v1, v2 = _frames()
    root = save_dataframe_source(v1, "sales.csv")
    current = save_dataframe_version(root["id"], v2, {"type": "test", "label": "Refresh"})

    out = generate_insights(current["id"], v2, max_insights=40, persist=False)
    categories = {row["category"] for row in out["insights"]}
    assert {"trend", "correlation", "segment", "anomaly", "change"}.issubset(categories)
    assert out["engine_version"] == "insight_engine_v1"
    assert out["provenance"]["deterministic"] is True
    assert out["provenance"]["llm_used_for_numeric_calculation"] is False
    scores = [row["priority_score"] for row in out["insights"]]
    assert scores == sorted(scores, reverse=True)
    assert [row["rank"] for row in out["insights"]] == list(range(1, len(out["insights"]) + 1))
    assert all(row["evidence"] for row in out["insights"])
    assert all(row["calculation"]["deterministic"] is True for row in out["insights"])
    assert all(row["causal_claim"] is False for row in out["insights"])


def test_v248_fingerprints_are_stable_for_same_dataset_version(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    v1, _ = _frames()
    meta = save_dataframe_source(v1, "sales.csv")
    first = generate_insights(meta["id"], v1, max_insights=30, persist=False)
    second = generate_insights(meta["id"], v1, max_insights=30, persist=False)
    assert [x["fingerprint"] for x in first["insights"]] == [x["fingerprint"] for x in second["insights"]]


def test_v248_scan_persists_traceable_history(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    v1, _ = _frames()
    meta = save_dataframe_source(v1, "sales.csv")
    out = generate_insights(meta["id"], v1, max_insights=15, persist=True)
    history = insight_history(meta["id"], 10)
    assert history["count"] == 1
    assert history["history"][0]["dataset"]["id"] == meta["id"]
    assert history["history"][0]["summary"]["count"] == out["summary"]["count"]
    assert history["history"][0]["insight_ids"] == [x["id"] for x in out["insights"]]


def test_v248_version_change_contains_previous_version_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    v1, v2 = _frames()
    root = save_dataframe_source(v1, "sales.csv")
    current = save_dataframe_version(root["id"], v2, {"type": "test", "label": "Refresh"})
    out = generate_insights(current["id"], v2, max_insights=40, persist=False)
    changes = [x for x in out["insights"] if x["category"] == "change"]
    assert changes
    assert any(x["evidence"].get("previous_version") == 1 for x in changes)


def test_v248_assistant_registry_exposes_real_insight_tool():
    from app.assistant.tools import build_default_registry
    from app.assistant.host_v212 import bind_v212_host
    from app.assistant.agents import role_for_spec
    registry = build_default_registry()
    bind_v212_host(registry)
    spec = registry.get("generate_dataset_insights")
    assert spec is not None
    assert registry.has_handler("generate_dataset_insights") is True
    assert spec.deterministic is True
    assert role_for_spec(spec) == "statistics_agent"
