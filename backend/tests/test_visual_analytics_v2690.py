from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.visualization import (
    build_visualization,
    build_visualization_composition,
    edit_visualization,
    recommend_visualizations,
)


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 120
    return pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "Region": np.resize(np.array(["Nord", "Sud", "Est", "Ouest"]), n),
        "Canal": np.resize(np.array(["Web", "Agence", "Partenaire"]), n),
        "CA": rng.normal(1000, 180, n).round(2),
        "Marge": rng.normal(250, 60, n).round(2),
        "Volume": rng.integers(10, 100, n),
        "Latitude": rng.uniform(30.0, 36.0, n),
        "Longitude": rng.uniform(-9.0, -2.0, n),
    })


def test_recommendations_are_ranked_and_explained():
    recs = recommend_visualizations(frame(), ["Date", "Region", "CA", "Marge", "Volume"])
    assert recs
    assert all("score" in r and "confidence" in r and "reason" in r for r in recs)
    assert [r["score"] for r in recs] == sorted([r["score"] for r in recs], reverse=True)
    assert any(r["type"] == "line" for r in recs)
    assert any(r["type"] == "bubble" for r in recs)


def test_violin_and_bubble_are_real_payloads():
    df = frame()
    violin = build_visualization(df, chart_type="violin", x="Region", y="CA")
    bubble = build_visualization(df, chart_type="bubble", x="CA", y="Marge", size="Volume", color="Region")
    assert violin["type"] == "violin" and len(violin["data"]) == 4
    assert violin["data"][0]["density"]
    assert bubble["type"] == "bubble" and bubble["data"]
    assert all("radius" in p for p in bubble["data"][:10])


def test_treemap_and_sankey_are_aggregated():
    df = frame()
    tree = build_visualization(df, chart_type="treemap", x="Region", y="CA", aggregation="sum")
    sankey = build_visualization(df, chart_type="sankey", x="Region", y="Canal", size="Volume")
    assert tree["type"] == "treemap" and len(tree["data"]) == 4
    assert sum(x["value"] for x in tree["data"]) > 0
    assert sankey["type"] == "sankey" and sankey["nodes"] and sankey["data"]
    assert all(x["value"] > 0 for x in sankey["data"])


def test_map_pca_and_cluster_payloads():
    df = frame()
    geo = build_visualization(df, chart_type="map", x="Longitude", y="Latitude", color="Region")
    pca = build_visualization(df, chart_type="pca", columns=["CA", "Marge", "Volume"])
    cluster = build_visualization(df, chart_type="cluster", columns=["CA", "Marge", "Volume"], cluster_k=4)
    assert geo["coordinate_system"] == "geographic" and len(geo["data"]) == len(df)
    assert pca["type"] == "pca" and len(pca["explained_variance_pct"]) == 2
    assert len(pca["loadings"]) == 3
    assert cluster["type"] == "cluster" and cluster["k"] == 4 and sum(cluster["counts"]) == len(cluster["data"])


def test_conversational_edit_changes_existing_visualization():
    df = frame()
    original = build_visualization(df, chart_type="scatter", x="CA", y="Marge")
    edited = edit_visualization(df, original, "transforme en bubble, taille=Volume, couleur=Region, titre=Performance commerciale")
    assert edited["applied"] is True
    assert edited["visualization"]["type"] == "bubble"
    assert edited["visualization"]["size"] == "Volume"
    assert edited["visualization"]["title"] == "Performance commerciale"


def test_composition_builds_distinct_views():
    comp = build_visualization_composition(frame(), columns=["Date", "Region", "CA", "Marge", "Volume"], max_views=4)
    assert comp["type"] == "composition"
    assert 2 <= comp["view_count"] <= 4
    kinds = [v["visualization"]["type"] for v in comp["views"]]
    assert len(kinds) == len(set(kinds))


def test_auto_uses_ranked_recommendation():
    df = frame()
    out = build_visualization(df, chart_type="auto", x="Date", y="CA")
    assert out["type"] in {"line", "area", "scatter", "bar"}
    assert out["data"]


def test_invalid_bubble_requires_numeric_size():
    df = frame()
    try:
        build_visualization(df, chart_type="bubble", x="CA", y="Marge", size="Region")
    except ValueError as exc:
        assert "taille numérique" in str(exc)
    else:
        raise AssertionError("bubble must reject a non-numeric size")
