from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.automl_engine import (
    get_automl_experiment,
    list_automl_experiments,
    run_automl_benchmark,
    run_automl_experiment,
)


def _classification_frame(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    target = np.where(x1 + 0.7 * x2 > 0, "yes", "no")
    return pd.DataFrame({"x1": x1, "x2": x2, "target": target})


def _cluster_frame(n: int = 90) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    centers = np.array([[-4.0, -4.0], [0.0, 4.0], [4.0, -2.0]])
    chunks = [rng.normal(loc=c, scale=0.45, size=(n // 3, 2)) for c in centers]
    arr = np.vstack(chunks)
    return pd.DataFrame({"x": arr[:, 0], "y": arr[:, 1], "id": np.arange(len(arr))})


def test_v250_supervised_automl_persists_ranked_experiment(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = _classification_frame()
    out = run_automl_experiment(
        df, target="target", task="classification", primary_metric="balanced_accuracy",
        cv_folds=3, tune=False, max_candidates=3,
        dataset_context={"id": "ds-1", "version": 4, "name": "train.csv"},
    )
    assert out["experiment_id"]
    assert out["leaderboard"][0]["rank"] == 1
    assert out["leaderboard"][0]["selection_metric"] == "balanced_accuracy"
    exp = get_automl_experiment(out["experiment_id"])
    assert exp["dataset"]["id"] == "ds-1"
    assert exp["validation_policy"]["final_test_isolated"] is True
    assert exp["selected"]["model_id"] == out["model_id"]
    assert list_automl_experiments("ds-1")[0]["experiment_id"] == out["experiment_id"]


def test_v250_clustering_automl_selects_and_persists_model(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = _cluster_frame()
    out = run_automl_experiment(
        df, task="clustering", features=["x", "y"], primary_metric="silhouette",
        max_candidates=9, dataset_context={"id": "cluster-ds", "version": 1},
    )
    assert out["task"] == "clustering"
    assert out["target"] is None
    assert out["metrics"]["silhouette"] > 0.5
    assert out["leaderboard"][0]["rank"] == 1
    assert out["best_params"]["n_clusters"] in {2, 3, 4}
    assert len(out["cluster_profiles"]) >= 2
    assert (tmp_path / "models" / f"{out['model_id']}.joblib").exists()
    exp = get_automl_experiment(out["experiment_id"])
    assert exp["validation_policy"]["supervised_target_used"] is False


def test_v250_cluster_benchmark_does_not_persist_final_model(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = _cluster_frame()
    before = set((tmp_path / "models").glob("*.joblib")) if (tmp_path / "models").exists() else set()
    out = run_automl_benchmark(df, task="clustering", features=["x", "y"], primary_metric="davies_bouldin", max_candidates=6)
    after = set((tmp_path / "models").glob("*.joblib")) if (tmp_path / "models").exists() else set()
    assert before == after
    assert out["metric_direction"] == "minimize"
    ok = [r for r in out["leaderboard"] if r["status"] == "ok"]
    assert ok and ok[0]["rank"] == 1
    assert ok[0]["validation_score"] <= ok[-1]["validation_score"]


def test_v250_feature_selection_is_explicit_and_target_cannot_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = _classification_frame()
    try:
        run_automl_experiment(df, target="target", task="classification", features=["x1", "target"], max_candidates=2, tune=False)
    except ValueError as exc:
        assert "cible" in str(exc).lower()
    else:
        raise AssertionError("La cible ne doit jamais être acceptée comme feature")


def test_v250_api_contract_exposes_clustering_and_experiments():
    from app.api.routes.datasets import AutoMLRequest, BenchmarkRequest
    a = AutoMLRequest.model_json_schema()
    b = BenchmarkRequest.model_json_schema()
    assert "clustering" in str(a)
    assert "silhouette" in str(a)
    assert "features" in a["properties"]
    assert "clustering" in str(b)
    route_source = __import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "datasets.py"
    text = route_source.read_text(encoding="utf-8")
    assert '/models/experiments' in text
    assert 'run_automl_experiment' in text


def test_v250_assistant_ml_bridge_supports_clustering():
    import inspect
    from app.assistant.host_v212 import V212MLBridge
    source = inspect.getsource(V212MLBridge.run_automl)
    assert '"clustering"' in source
    assert "run_automl_experiment" in source


def test_v250_assistant_contract_and_planner_allow_clustering_without_target():
    from app.assistant.contracts import AutoMLArgs
    assert AutoMLArgs(task="clustering", target=None, features=["x", "y"]).task == "clustering"
    schema = AutoMLArgs.model_json_schema()
    assert "forecasting" not in str(schema)
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "assistant" / "planner_runtime.py").read_text(encoding="utf-8")
    assert 'task != "clustering" and not target' in source


def test_v250_supervised_benchmark_rejects_target_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = _classification_frame()
    try:
        run_automl_benchmark(df, target="target", task="classification", features=["x1", "target"], max_candidates=2)
    except ValueError as exc:
        assert "cible" in str(exc).lower()
    else:
        raise AssertionError("Le benchmark ne doit jamais accepter la cible comme feature")
