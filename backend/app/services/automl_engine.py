from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import Birch, KMeans, MiniBatchKMeans
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.services.modeling import automl_train, benchmark_models
from app.services.ml_guardrails import audit_supervised_ml


CLUSTER_ALGORITHMS = {
    "kmeans": "K-Means",
    "minibatch_kmeans": "MiniBatch K-Means",
    "birch": "BIRCH",
}
CLUSTER_METRICS = {"silhouette", "calinski_harabasz", "davies_bouldin"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _experiments_root() -> Path:
    root = get_settings().model_dir / "experiments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _experiment_path(experiment_id: str) -> Path:
    return _experiments_root() / f"{experiment_id}.json"


def _save_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    _experiment_path(str(payload["experiment_id"])).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return payload


def get_automl_experiment(experiment_id: str) -> dict[str, Any]:
    path = _experiment_path(experiment_id)
    if not path.exists():
        raise FileNotFoundError(experiment_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_automl_experiments(dataset_id: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _experiments_root().glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if dataset_id and str((item.get("dataset") or {}).get("id") or "") != dataset_id:
            continue
        rows.append(item)
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return rows


def _rank_leaderboard(rows: list[dict[str, Any]], metric: str, minimize: bool = False) -> list[dict[str, Any]]:
    successful = [r for r in rows if r.get("status") == "ok"]
    failed = [r for r in rows if r.get("status") != "ok"]
    def score(row: dict[str, Any]) -> float:
        raw = row.get("selection_value")
        try:
            val = float(raw)
        except Exception:
            return float("inf") if minimize else -float("inf")
        if math.isnan(val):
            return float("inf") if minimize else -float("inf")
        return val
    successful.sort(key=score, reverse=not minimize)
    ranked: list[dict[str, Any]] = []
    for idx, row in enumerate(successful, 1):
        item = dict(row)
        item["rank"] = idx
        item["selection_metric"] = metric
        ranked.append(item)
    for row in failed:
        item = dict(row)
        item["rank"] = None
        item["selection_metric"] = metric
        ranked.append(item)
    return ranked


def _supervised_experiment(
    result: dict[str, Any], *, dataset_context: dict[str, Any] | None, requested_task: str,
    requested_metric: str, cv_folds: int, tune: bool, max_candidates: int,
) -> dict[str, Any]:
    experiment_id = str(uuid.uuid4())
    primary = str(result.get("primary_metric") or requested_metric or "auto")
    minimize = primary in {"rmse", "mae"}
    leaderboard = _rank_leaderboard(list(result.get("benchmark") or []), primary, minimize=minimize)
    best = next((row for row in leaderboard if row.get("rank") == 1), None)
    experiment = {
        "experiment_id": experiment_id,
        "created_at": _utcnow(),
        "dataset": dataset_context or {},
        "task": result.get("task") or requested_task,
        "target": (result.get("model_card") or {}).get("target"),
        "primary_metric": primary,
        "metric_direction": "minimize" if minimize else "maximize",
        "validation_policy": {
            "strategy": (result.get("split_audit") or {}).get("strategy", "random"),
            "time_column": (result.get("split_audit") or {}).get("time_column"),
            "cv_folds": cv_folds,
            "final_test_isolated": True,
            "selection_uses_test": False,
            "tuning_uses_test": False,
            "tuning": bool(tune),
            "split_audit": result.get("split_audit") or {},
        },
        "safety_audit": result.get("safety_audit") or {},
        "overfitting_assessment": result.get("overfitting_assessment") or {},
        "max_candidates": max_candidates,
        "leaderboard": leaderboard,
        "selected": {
            "model_id": result.get("model_id"),
            "algorithm": result.get("algorithm"),
            "rank": 1,
            "validation_score": (best or {}).get("validation_score"),
            "final_test_metrics": result.get("metrics") or {},
        },
        "selection_rationale": (
            f"Candidat classé premier sur la métrique de validation {primary}; "
            "le jeu de test final est resté isolé jusqu'après la sélection et le tuning."
        ),
        "status": "completed",
    }
    _save_experiment(experiment)
    result = dict(result)
    result["experiment_id"] = experiment_id
    result["leaderboard"] = leaderboard
    result["selection_rationale"] = experiment["selection_rationale"]
    return result


def _cluster_frame(df: pd.DataFrame, features: list[str] | None) -> tuple[pd.DataFrame, list[str], list[str]]:
    numeric = list(df.select_dtypes(include=np.number).columns)
    requested = list(features or numeric)
    missing = [c for c in requested if c not in df.columns]
    if missing:
        raise ValueError(f"Variables inconnues: {', '.join(missing)}")
    non_numeric = [c for c in requested if c not in numeric]
    if non_numeric:
        raise ValueError("Le clustering AutoML v2.50 accepte uniquement des variables numériques.")
    excluded: list[str] = []
    usable: list[str] = []
    for col in requested:
        s = df[col]
        if s.nunique(dropna=True) <= 1:
            excluded.append(col)
            continue
        unique_ratio = float(s.nunique(dropna=True) / max(1, s.notna().sum()))
        name = col.lower()
        if unique_ratio > 0.98 and (name == "id" or name.endswith("_id") or "uuid" in name or "identifiant" in name):
            excluded.append(col)
            continue
        usable.append(col)
    if len(usable) < 2:
        raise ValueError("Le clustering AutoML requiert au moins deux variables numériques exploitables.")
    work = df[usable].copy()
    if len(work) < 20:
        raise ValueError("Le clustering AutoML requiert au moins 20 observations.")
    return work, usable, excluded


def _cluster_estimator(algorithm: str, k: int):
    if algorithm == "kmeans":
        return KMeans(n_clusters=k, n_init=10, random_state=42)
    if algorithm == "minibatch_kmeans":
        return MiniBatchKMeans(n_clusters=k, n_init=10, random_state=42, batch_size=256)
    if algorithm == "birch":
        return Birch(n_clusters=k)
    raise ValueError(f"Algorithme de clustering inconnu: {algorithm}")


def _cluster_metrics(matrix: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    unique = np.unique(labels)
    if len(unique) < 2 or len(unique) >= len(matrix):
        raise ValueError("La partition ne permet pas de calculer des métriques internes valides.")
    return {
        "silhouette": round(float(silhouette_score(matrix, labels)), 6),
        "calinski_harabasz": round(float(calinski_harabasz_score(matrix, labels)), 6),
        "davies_bouldin": round(float(davies_bouldin_score(matrix, labels)), 6),
    }


def _cluster_search(
    df: pd.DataFrame, *, features: list[str] | None, primary_metric: str, max_candidates: int,
) -> tuple[pd.DataFrame, list[str], list[str], str, bool, list[dict[str, Any]], np.ndarray]:
    work, usable, excluded = _cluster_frame(df, features)
    metric = primary_metric if primary_metric in CLUSTER_METRICS else "silhouette"
    minimize = metric == "davies_bouldin"
    max_k = max(2, min(8, len(work) - 1))
    configs: list[tuple[str, int]] = []
    for k in range(2, max_k + 1):
        for algo in CLUSTER_ALGORITHMS:
            configs.append((algo, k))
    configs = configs[: max(1, min(int(max_candidates), len(configs)))]
    prep = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), usable)
    ], remainder="drop")
    matrix = prep.fit_transform(work)
    rows: list[dict[str, Any]] = []
    for algorithm, k in configs:
        row: dict[str, Any] = {
            "algorithm": algorithm, "label": f"{CLUSTER_ALGORITHMS[algorithm]} · k={k}", "k": k,
            "engine": "scikit-learn", "status": "ok", "primary_metric": metric,
        }
        try:
            estimator = _cluster_estimator(algorithm, k)
            labels = estimator.fit_predict(matrix)
            metrics = _cluster_metrics(np.asarray(matrix), np.asarray(labels))
            row.update({"validation_metrics": metrics, "validation_score": metrics[metric], "selection_value": metrics[metric],
                        "cluster_sizes": {str(key): int(value) for key, value in pd.Series(labels).value_counts().sort_index().items()}})
        except Exception as exc:
            row.update({"status": "error", "validation_metrics": {}, "validation_score": None, "selection_value": None,
                        "error": f"{type(exc).__name__}: {str(exc)[:400]}"})
        rows.append(row)
    return work, usable, excluded, metric, minimize, _rank_leaderboard(rows, metric, minimize=minimize), np.asarray(matrix)


def clustering_automl(
    df: pd.DataFrame, *, features: list[str] | None = None, primary_metric: str = "auto",
    max_candidates: int = 8, dataset_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work, usable, excluded, metric, minimize, leaderboard, _matrix = _cluster_search(
        df, features=features, primary_metric=primary_metric, max_candidates=max_candidates
    )
    best = next((row for row in leaderboard if row.get("rank") == 1), None)
    if not best:
        raise RuntimeError("Aucun candidat de clustering n'a pu être entraîné.")

    final_prep = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), usable)
    ], remainder="drop")
    final_est = _cluster_estimator(str(best["algorithm"]), int(best["k"]))
    final_pipe = Pipeline([("preprocess", final_prep), ("model", final_est)])
    labels = final_pipe.fit_predict(work)
    transformed = final_pipe.named_steps["preprocess"].transform(work)
    metrics = _cluster_metrics(np.asarray(transformed), np.asarray(labels))
    model_id = str(uuid.uuid4())
    experiment_id = str(uuid.uuid4())
    card = {
        "model_id": model_id,
        "created_at": _utcnow(),
        "dataset": dataset_context or {},
        "target": None,
        "task": "clustering",
        "algorithm": str(best["algorithm"]),
        "features": usable,
        "primary_metric": metric,
        "metrics_final_test": metrics,
        "metrics_validation": metrics,
        "rows": {"train": len(work), "validation": len(work), "test": 0},
        "validation_strategy": {
            "split": "unsupervised_full_dataset_internal_validation",
            "cross_validation": {"folds": 0, "status": "not_applicable"},
            "test_policy": "Le clustering non supervisé est sélectionné sur métriques internes; aucun label cible ni test supervisé n'est utilisé.",
        },
        "best_params": {"n_clusters": int(best["k"])},
        "guardrails": [{"code": "unsupervised_validation", "severity": "info", "message": "Comparer les clusters à la connaissance métier avant usage décisionnel."}],
        "feature_importance": [],
        "known_limitations": ["Les métriques internes ne garantissent pas une segmentation métier utile.", "Le scaling et le choix des variables influencent fortement les clusters."],
        "fairness": {"status": "not_evaluated"},
        "responsible_ai": {"status": "not_evaluated"},
        "explainability": {"cluster_profiles": True, "feature_importance": False},
        "experiment_id": experiment_id,
    }
    root = get_settings().model_dir
    joblib.dump({"pipeline": final_pipe, "target": None, "features": usable, "task": "clustering", "algorithm": best["algorithm"], "model_card": card, "evaluation_indices": work.index.tolist()}, root / f"{model_id}.joblib")
    (root / f"{model_id}.card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    profiles = work.assign(__cluster=labels).groupby("__cluster")[usable].mean(numeric_only=True).round(6).reset_index().to_dict(orient="records")
    rationale = f"Partition classée première sur {metric} parmi {len([r for r in leaderboard if r.get('status') == 'ok'])} candidats valides."
    experiment = {
        "experiment_id": experiment_id, "created_at": _utcnow(), "dataset": dataset_context or {}, "task": "clustering",
        "target": None, "primary_metric": metric, "metric_direction": "minimize" if minimize else "maximize",
        "validation_policy": {"strategy": "internal_cluster_validation", "final_test_isolated": False, "supervised_target_used": False},
        "max_candidates": max_candidates, "leaderboard": leaderboard,
        "selected": {"model_id": model_id, "algorithm": best["algorithm"], "k": best["k"], "rank": 1, "metrics": metrics},
        "selection_rationale": rationale, "status": "completed",
    }
    _save_experiment(experiment)
    return {
        "model_id": model_id, "experiment_id": experiment_id, "task": "clustering", "algorithm": best["algorithm"],
        "target": None, "primary_metric": metric, "metrics": metrics, "validation_metrics": metrics,
        "rows_train": len(work), "rows_validation": len(work), "rows_test": 0, "leaderboard": leaderboard, "benchmark": leaderboard,
        "best_params": {"n_clusters": int(best["k"])}, "guardrails": card["guardrails"], "excluded_features": excluded,
        "feature_importance": [], "cluster_profiles": profiles, "cluster_sizes": {str(k): int(v) for k, v in pd.Series(labels).value_counts().sort_index().items()},
        "model_card": card, "selection_rationale": rationale,
    }



def audit_automl_safety(
    df: pd.DataFrame, *, target: str | None, task: str = "auto", features: list[str] | None = None,
    primary_metric: str = "auto", split_strategy: str = "auto", time_column: str | None = None,
) -> dict[str, Any]:
    if task == "clustering":
        work, usable, excluded = _cluster_frame(df, features)
        return {
            "status": "pass", "task": "clustering", "target": None, "rows": len(work),
            "metric_policy": {"requested": primary_metric, "effective": primary_metric if primary_metric in CLUSTER_METRICS else "silhouette", "overridden": False},
            "split_policy": {"strategy": "unsupervised_full_dataset", "time_column": None, "temporal_candidates": []},
            "excluded_features": [{"column": c, "reason": "identifier_or_constant"} for c in excluded],
            "usable_features": usable,
            "findings": [{"code": "unsupervised_validation", "severity": "info", "message": "Le clustering utilise des métriques internes et ne consomme aucun test supervisé."}],
            "blocking_findings": 0,
            "test_policy": {"final_test_isolated": False, "selection_uses_test": False, "tuning_uses_test": False},
        }
    if not target or target not in df.columns:
        raise ValueError("Une variable cible valide est requise pour l'audit ML supervisé.")
    work = df
    if features:
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise ValueError(f"Variables inconnues: {', '.join(missing)}")
        if target in features:
            raise ValueError("La cible ne doit pas figurer dans les features.")
        cols = list(features)
        if time_column and time_column not in cols:
            if time_column not in df.columns:
                raise ValueError(f"Colonne temporelle inconnue: {time_column}")
            cols.append(time_column)
        work = df[[*cols, target]].copy()
    y = work[target].dropna()
    resolved_task = task
    if task == "auto":
        resolved_task = "regression" if pd.api.types.is_numeric_dtype(y) and y.nunique(dropna=True) > max(20, int(len(y) * 0.05)) else "classification"
    return audit_supervised_ml(
        work, target=target, task=resolved_task, requested_metric=primary_metric,
        split_strategy=split_strategy, time_column=time_column,
    )

def run_automl_experiment(
    df: pd.DataFrame, *, target: str | None = None, task: str = "auto", features: list[str] | None = None,
    primary_metric: str = "auto", cv_folds: int = 5, tune: bool = True, max_candidates: int = 7,
    dataset_context: dict[str, Any] | None = None, split_strategy: str = "auto", time_column: str | None = None,
) -> dict[str, Any]:
    if task == "clustering":
        return clustering_automl(df, features=features, primary_metric=primary_metric, max_candidates=max_candidates, dataset_context=dataset_context)
    if not target:
        raise ValueError("Une variable cible est requise pour la classification ou la régression.")
    work = df
    if features:
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise ValueError(f"Variables inconnues: {', '.join(missing)}")
        if target in features:
            raise ValueError("La cible ne doit pas figurer dans les features.")
        cols = list(features)
        if time_column and time_column not in cols:
            if time_column not in df.columns:
                raise ValueError(f"Colonne temporelle inconnue: {time_column}")
            cols.append(time_column)
        work = df[[*cols, target]].copy()
    result = automl_train(
        work, target=target, task=task, primary_metric=primary_metric, cv_folds=cv_folds, tune=tune,
        max_candidates=max_candidates, dataset_context=dataset_context, split_strategy=split_strategy, time_column=time_column,
    )
    return _supervised_experiment(result, dataset_context=dataset_context, requested_task=task, requested_metric=primary_metric, cv_folds=cv_folds, tune=tune, max_candidates=max_candidates)


def run_automl_benchmark(
    df: pd.DataFrame, *, target: str | None = None, task: str = "auto", features: list[str] | None = None,
    primary_metric: str = "auto", cv_folds: int = 5, max_candidates: int = 10,
    split_strategy: str = "auto", time_column: str | None = None,
) -> dict[str, Any]:
    if task == "clustering":
        work, usable, excluded, metric, minimize, leaderboard, _matrix = _cluster_search(
            df, features=features, primary_metric=primary_metric, max_candidates=max_candidates
        )
        best = next((row for row in leaderboard if row.get("rank") == 1), None)
        return {
            "task": "clustering", "target": None, "primary_metric": metric, "metric_direction": "minimize" if minimize else "maximize",
            "rows": len(work), "features": usable, "excluded_features": excluded, "cv_folds": 0,
            "benchmark": leaderboard, "leaderboard": leaderboard, "best": best,
            "selection_policy": "Classement sur métriques internes de clustering; aucun modèle final n'est persisté par le benchmark seul.",
        }
    if not target:
        raise ValueError("Une variable cible est requise pour le benchmark supervisé.")
    work = df
    if features:
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise ValueError(f"Variables inconnues: {', '.join(missing)}")
        if target in features:
            raise ValueError("La cible ne doit pas figurer dans les features.")
        cols = list(features)
        if time_column and time_column not in cols:
            if time_column not in df.columns:
                raise ValueError(f"Colonne temporelle inconnue: {time_column}")
            cols.append(time_column)
        work = df[[*cols, target]].copy()
    result = benchmark_models(
        work, target=target, task=task, primary_metric=primary_metric, cv_folds=cv_folds, max_candidates=max_candidates,
        split_strategy=split_strategy, time_column=time_column,
    )
    result["leaderboard"] = _rank_leaderboard(list(result.get("benchmark") or []), str(result.get("primary_metric") or primary_metric), minimize=str(result.get("primary_metric")) in {"rmse", "mae"})
    return result
