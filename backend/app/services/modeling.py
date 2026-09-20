from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, KFold, TimeSeriesSplit, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.svm import SVC, SVR

from app.core.config import get_settings
from app.services.ml_guardrails import audit_supervised_ml, assess_overfitting, build_split_audit, govern_metric


try:
    from xgboost import XGBClassifier, XGBRegressor
    HAS_XGBOOST = True
except Exception:
    XGBClassifier = XGBRegressor = None
    HAS_XGBOOST = False

try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    HAS_LIGHTGBM = True
except Exception:
    LGBMClassifier = LGBMRegressor = None
    HAS_LIGHTGBM = False

try:
    from catboost import CatBoostClassifier, CatBoostRegressor
    HAS_CATBOOST = True
except Exception:
    CatBoostClassifier = CatBoostRegressor = None
    HAS_CATBOOST = False


class LabelEncodedClassifier(BaseEstimator, ClassifierMixin):
    """
    Adapter for classifiers that require integer encoded class labels.

    The external estimator still participates in sklearn cloning/CV while
    DataVision preserves the original user-facing class labels.
    """

    def __init__(self, estimator):
        self.estimator = estimator

    def fit(self, X, y):
        self.encoder_ = LabelEncoder().fit(y)
        self.estimator_ = clone(self.estimator)
        encoded = self.encoder_.transform(y)
        self.estimator_.fit(X, encoded)
        self.classes_ = self.encoder_.classes_
        return self

    def predict(self, X):
        encoded = np.asarray(
            self.estimator_.predict(X),
            dtype=int,
        )
        return self.encoder_.inverse_transform(encoded)

    def predict_proba(self, X):
        return self.estimator_.predict_proba(X)



@dataclass
class TrainingResult:
    model_id: str
    task: str
    algorithm: str
    metrics: dict[str, float]
    rows_train: int
    rows_test: int
    rows_validation: int = 0
    validation_metrics: dict[str, float] | None = None
    guardrails: list[dict[str, Any]] | None = None
    feature_importance: list[dict[str, Any]] | None = None
    model_card: dict[str, Any] | None = None


CLASSIFICATION_ALGORITHMS = {
    "logistic_regression": "Régression logistique",
    "random_forest": "Random Forest",
    "extra_trees": "Extra Trees",
    "gradient_boosting": "Gradient Boosting",
    "hist_gradient_boosting": "Histogram Gradient Boosting",
    "svm": "SVM",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
}

REGRESSION_ALGORITHMS = {
    "linear_regression": "Régression linéaire",
    "ridge": "Ridge",
    "random_forest": "Random Forest",
    "extra_trees": "Extra Trees",
    "gradient_boosting": "Gradient Boosting",
    "hist_gradient_boosting": "Histogram Gradient Boosting",
    "svm": "SVM",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_for_target(y: pd.Series, requested: str) -> str:
    if requested in {"classification", "regression"}:
        return requested
    if pd.api.types.is_numeric_dtype(y) and y.nunique(dropna=True) > max(20, int(len(y) * 0.05)):
        return "regression"
    return "classification"


def _build_preprocessor(X: pd.DataFrame) -> tuple[ColumnTransformer, list[str], list[str]]:
    numeric = list(X.select_dtypes(include=np.number).columns)
    categorical = [c for c in X.columns if c not in numeric]
    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if numeric:
        transformers.append(("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric))
    if categorical:
        transformers.append(("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical))
    if not transformers:
        raise ValueError("Aucune variable explicative exploitable.")
    return ColumnTransformer(transformers=transformers, remainder="drop"), numeric, categorical


def algorithm_availability() -> dict[str, dict[str, Any]]:
    return {
        "logistic_regression": {"available": True, "engine": "scikit-learn"},
        "linear_regression": {"available": True, "engine": "scikit-learn"},
        "ridge": {"available": True, "engine": "scikit-learn"},
        "random_forest": {"available": True, "engine": "scikit-learn"},
        "extra_trees": {"available": True, "engine": "scikit-learn"},
        "gradient_boosting": {"available": True, "engine": "scikit-learn"},
        "hist_gradient_boosting": {"available": True, "engine": "scikit-learn"},
        "svm": {"available": True, "engine": "scikit-learn"},
        "xgboost": {"available": HAS_XGBOOST, "engine": "xgboost"},
        "lightgbm": {"available": HAS_LIGHTGBM, "engine": "lightgbm"},
        "catboost": {"available": HAS_CATBOOST, "engine": "catboost"},
    }


def available_algorithms(task: str) -> list[str]:
    catalog = (
        CLASSIFICATION_ALGORITHMS
        if task == "classification"
        else REGRESSION_ALGORITHMS
    )
    availability = algorithm_availability()
    return [
        name
        for name in catalog
        if availability.get(name, {}).get("available", False)
    ]


def _estimator(task: str, algorithm: str):
    if task == "classification":
        if algorithm == "logistic_regression":
            return LogisticRegression(
                max_iter=2500,
                class_weight="balanced",
                random_state=42,
            )
        if algorithm == "random_forest":
            return RandomForestClassifier(
                n_estimators=300,
                random_state=42,
                class_weight="balanced",
                n_jobs=-1,
            )
        if algorithm == "extra_trees":
            return ExtraTreesClassifier(
                n_estimators=300,
                random_state=42,
                class_weight="balanced",
                n_jobs=-1,
            )
        if algorithm == "gradient_boosting":
            return GradientBoostingClassifier(random_state=42)
        if algorithm == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(random_state=42)
        if algorithm == "svm":
            return SVC(
                C=1.0,
                kernel="rbf",
                probability=True,
                class_weight="balanced",
                random_state=42,
            )
        if algorithm == "xgboost":
            if not HAS_XGBOOST:
                raise RuntimeError("XGBoost n'est pas installé.")
            return LabelEncodedClassifier(
                XGBClassifier(
                    n_estimators=300,
                    max_depth=6,
                    learning_rate=0.05,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    random_state=42,
                    n_jobs=1,
                    tree_method="hist",
                    eval_metric="logloss",
                )
            )
        if algorithm == "lightgbm":
            if not HAS_LIGHTGBM:
                raise RuntimeError("LightGBM n'est pas installé.")
            return LGBMClassifier(
                n_estimators=300,
                learning_rate=0.05,
                num_leaves=31,
                random_state=42,
                n_jobs=1,
                class_weight="balanced",
                verbosity=-1,
            )
        if algorithm == "catboost":
            if not HAS_CATBOOST:
                raise RuntimeError("CatBoost n'est pas installé.")
            return CatBoostClassifier(
                iterations=300,
                depth=6,
                learning_rate=0.05,
                random_seed=42,
                verbose=False,
                allow_writing_files=False,
                thread_count=1,
            )
        raise ValueError(
            f"Algorithme de classification non supporté: {algorithm}"
        )

    if algorithm == "linear_regression":
        return LinearRegression()
    if algorithm == "ridge":
        return Ridge(alpha=1.0)
    if algorithm == "random_forest":
        return RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1,
        )
    if algorithm == "extra_trees":
        return ExtraTreesRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1,
        )
    if algorithm == "gradient_boosting":
        return GradientBoostingRegressor(random_state=42)
    if algorithm == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(random_state=42)
    if algorithm == "svm":
        return SVR(C=1.0, epsilon=0.1, kernel="rbf")
    if algorithm == "xgboost":
        if not HAS_XGBOOST:
            raise RuntimeError("XGBoost n'est pas installé.")
        return XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=1,
            tree_method="hist",
            objective="reg:squarederror",
        )
    if algorithm == "lightgbm":
        if not HAS_LIGHTGBM:
            raise RuntimeError("LightGBM n'est pas installé.")
        return LGBMRegressor(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            random_state=42,
            n_jobs=1,
            verbosity=-1,
        )
    if algorithm == "catboost":
        if not HAS_CATBOOST:
            raise RuntimeError("CatBoost n'est pas installé.")
        return CatBoostRegressor(
            iterations=300,
            depth=6,
            learning_rate=0.05,
            random_seed=42,
            verbose=False,
            allow_writing_files=False,
            thread_count=1,
        )
    raise ValueError(
        f"Algorithme de régression non supporté: {algorithm}"
    )


def _candidate_algorithms(
    task: str,
    max_candidates: int = 10,
) -> list[str]:
    values = available_algorithms(task)
    return values[: max(1, min(max_candidates, len(values)))]

def _primary_metric(task: str, y: pd.Series, requested: str) -> str:
    return str(govern_metric(task, y, requested).get("effective"))


def _scoring_name(task: str, metric: str) -> str:
    if task == "classification":
        return {
            "accuracy": "accuracy",
            "balanced_accuracy": "balanced_accuracy",
            "f1_weighted": "f1_weighted",
            "roc_auc": "roc_auc",
        }[metric]
    return {"rmse": "neg_root_mean_squared_error", "mae": "neg_mean_absolute_error", "r2": "r2"}[metric]


def _metric_value(metrics: dict[str, float], metric: str) -> float:
    value = float(metrics.get(metric, float("nan")))
    if math.isnan(value):
        return -float("inf")
    return -value if metric in {"rmse", "mae"} else value


def _evaluate(pipe: Pipeline, X: pd.DataFrame, y: pd.Series, task: str) -> dict[str, float]:
    pred = pipe.predict(X)
    if task == "classification":
        result: dict[str, float] = {
            "accuracy": round(float(accuracy_score(y, pred)), 6),
            "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 6),
            "precision_weighted": round(float(precision_score(y, pred, average="weighted", zero_division=0)), 6),
            "recall_weighted": round(float(recall_score(y, pred, average="weighted", zero_division=0)), 6),
            "f1_weighted": round(float(f1_score(y, pred, average="weighted", zero_division=0)), 6),
        }
        if y.nunique() == 2 and hasattr(pipe, "predict_proba"):
            try:
                probs = pipe.predict_proba(X)[:, 1]
                result["roc_auc"] = round(float(roc_auc_score(y, probs)), 6)
            except Exception:
                pass
        return result
    rmse = mean_squared_error(y, pred) ** 0.5
    return {
        "mae": round(float(mean_absolute_error(y, pred)), 6),
        "rmse": round(float(rmse), 6),
        "r2": round(float(r2_score(y, pred)), 6),
    }


def _safe_split(
    X: pd.DataFrame,
    y: pd.Series,
    task: str,
    *,
    split_strategy: str = "random",
    time_values: pd.Series | None = None,
):
    if split_strategy == "temporal":
        if time_values is None:
            raise ValueError("Split temporel demandé sans colonne temporelle.")
        parsed = pd.to_datetime(time_values.reindex(X.index), errors="coerce", utc=True)
        if parsed.isna().any():
            raise ValueError("La colonne temporelle contient des valeurs non interprétables après filtrage.")
        order = parsed.sort_values(kind="stable").index
        n = len(order)
        train_end = max(1, int(n * 0.60))
        val_end = max(train_end + 1, int(n * 0.80))
        if val_end >= n:
            val_end = n - 1
        train_idx = order[:train_end]
        val_idx = order[train_end:val_end]
        test_idx = order[val_end:]
        if min(len(train_idx), len(val_idx), len(test_idx)) < 1:
            raise ValueError("Échantillon insuffisant pour un split temporel 60/20/20.")
        return (
            X.loc[train_idx], X.loc[val_idx], X.loc[test_idx],
            y.loc[train_idx], y.loc[val_idx], y.loc[test_idx],
            build_split_audit(train_idx, val_idx, test_idx, strategy="temporal", time_column=str(time_values.name or "time")),
        )

    stratify = None
    if task == "classification" and y.value_counts().min() >= 3:
        stratify = y
    X_dev, X_test, y_dev, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=stratify
    )
    stratify_dev = None
    if task == "classification" and y_dev.value_counts().min() >= 2:
        stratify_dev = y_dev
    X_train, X_val, y_train, y_val = train_test_split(
        X_dev, y_dev, test_size=0.25, random_state=42, stratify=stratify_dev
    )
    split_audit = build_split_audit(X_train.index, X_val.index, X_test.index, strategy="random", time_column=None)
    return X_train, X_val, X_test, y_train, y_val, y_test, split_audit


def _cv_strategy(task: str, y: pd.Series, requested_folds: int, *, split_strategy: str = "random"):
    folds = max(2, min(int(requested_folds), 10))
    if split_strategy == "temporal":
        folds = min(folds, max(2, len(y) // 10))
        while folds >= 2 and len(y) > folds:
            cv = TimeSeriesSplit(n_splits=folds)
            valid = True
            if task == "classification":
                for train_idx, val_idx in cv.split(np.arange(len(y))):
                    if y.iloc[train_idx].nunique(dropna=True) < 2 or y.iloc[val_idx].nunique(dropna=True) < 2:
                        valid = False
                        break
            if valid:
                return cv, folds
            folds -= 1
        return None, 0
    if task == "classification":
        min_class = int(y.value_counts().min())
        folds = min(folds, min_class)
        if folds < 2:
            return None, 0
        return StratifiedKFold(n_splits=folds, shuffle=True, random_state=42), folds
    folds = min(folds, len(y))
    if folds < 2:
        return None, 0
    return KFold(n_splits=folds, shuffle=True, random_state=42), folds


def _auto_exclusions(X: pd.DataFrame) -> list[str]:
    excluded: list[str] = []
    for col in X.columns:
        s = X[col]
        non_null = max(1, int(s.notna().sum()))
        unique_ratio = float(s.nunique(dropna=True) / non_null)
        name_id = bool(re.search(r"(^id$|_id$|^id_|uuid|identifier|identifiant|numero|number)", col.lower()))
        constant = s.nunique(dropna=True) <= 1
        high_cardinality_identifier = unique_ratio > 0.98 and (name_id or not pd.api.types.is_float_dtype(s))
        if constant or high_cardinality_identifier:
            excluded.append(col)
    return excluded


def _feature_baselines(X: pd.DataFrame) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for col in X.columns:
        s = X[col]
        if pd.api.types.is_numeric_dtype(s):
            value = s.median()
        else:
            mode = s.mode(dropna=True)
            value = mode.iloc[0] if len(mode) else None
        if hasattr(value, "item"):
            value = value.item()
        if pd.isna(value) if not isinstance(value, (list, dict)) else False:
            value = None
        values[col] = value
    return values


def _guardrails(df: pd.DataFrame, target: str, task: str) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    y = df[target]
    X = df.drop(columns=[target])

    if len(df) < 100:
        warnings.append({
            "code": "small_sample", "severity": "medium",
            "message": f"Échantillon limité ({len(df)} lignes). Les métriques peuvent être instables.",
        })

    if task == "classification":
        counts = y.value_counts(dropna=True)
        if len(counts) >= 2:
            ratio = float(counts.min() / counts.max())
            if ratio < 0.5:
                warnings.append({
                    "code": "class_imbalance", "severity": "high" if ratio < 0.2 else "medium",
                    "message": f"Déséquilibre de classes détecté (ratio minoritaire/majoritaire={ratio:.3f}).",
                    "details": {str(k): int(v) for k, v in counts.items()},
                })

    id_like: list[str] = []
    for col in X.columns:
        s = X[col]
        unique_ratio = float(s.nunique(dropna=True) / max(1, s.notna().sum()))
        name_id = bool(re.search(r"(^id$|_id$|^id_|uuid|identifier|identifiant|numero|number)", col.lower()))
        if unique_ratio > 0.98 and (name_id or not pd.api.types.is_float_dtype(s)):
            id_like.append(col)
    if id_like:
        warnings.append({
            "code": "identifier_features", "severity": "medium",
            "message": "Variables potentiellement identifiantes ou quasi uniques détectées.",
            "columns": id_like[:20],
        })

    time_like = [c for c in X.columns if pd.api.types.is_datetime64_any_dtype(X[c]) or re.search(r"date|time|timestamp|annee|year|mois|month", c.lower())]
    if time_like:
        warnings.append({
            "code": "temporal_split", "severity": "medium",
            "message": "Variables temporelles détectées. Un split chronologique peut être préférable à un split aléatoire.",
            "columns": time_like[:20],
        })

    constant = [c for c in X.columns if X[c].nunique(dropna=True) <= 1]
    if constant:
        warnings.append({
            "code": "constant_features", "severity": "low",
            "message": "Variables constantes détectées; elles n'apportent aucun signal prédictif.",
            "columns": constant[:20],
        })

    if pd.api.types.is_numeric_dtype(y):
        leaks: list[dict[str, Any]] = []
        for col in X.select_dtypes(include=np.number).columns:
            pair = pd.concat([X[col], y], axis=1).dropna()
            if len(pair) >= 10 and pair.iloc[:, 0].nunique() > 1:
                corr = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
                if np.isfinite(corr) and abs(corr) >= 0.995:
                    leaks.append({"column": col, "correlation": round(corr, 6)})
        if leaks:
            warnings.append({
                "code": "possible_target_leakage", "severity": "high",
                "message": "Corrélation quasi parfaite avec la cible: vérifier une fuite de cible ou une variable dérivée du résultat.",
                "columns": leaks,
            })

    if not warnings:
        warnings.append({"code": "no_major_guardrail", "severity": "info", "message": "Aucun risque majeur détecté par les contrôles automatiques initiaux."})
    return warnings


def _tuning_grid(task: str, algorithm: str) -> dict[str, list[Any]]:
    prefix = "model__"
    grids: dict[tuple[str, str], dict[str, list[Any]]] = {
        ("classification", "logistic_regression"): {prefix + "C": [0.25, 1.0, 4.0]},
        ("classification", "random_forest"): {prefix + "max_depth": [None, 8, 16], prefix + "min_samples_leaf": [1, 3]},
        ("classification", "extra_trees"): {prefix + "max_depth": [None, 10, 20], prefix + "min_samples_leaf": [1, 2]},
        ("classification", "gradient_boosting"): {prefix + "learning_rate": [0.05, 0.1], prefix + "n_estimators": [100, 200]},
        ("classification", "hist_gradient_boosting"): {prefix + "learning_rate": [0.05, 0.1], prefix + "max_leaf_nodes": [15, 31]},
        ("classification", "svm"): {prefix + "C": [0.5, 1.0, 2.0], prefix + "gamma": ["scale", "auto"]},
        ("classification", "xgboost"): {prefix + "estimator__max_depth": [4, 6], prefix + "estimator__learning_rate": [0.03, 0.08]},
        ("classification", "lightgbm"): {prefix + "num_leaves": [15, 31], prefix + "learning_rate": [0.03, 0.08]},
        ("classification", "catboost"): {prefix + "depth": [4, 6], prefix + "learning_rate": [0.03, 0.08]},
        ("regression", "ridge"): {prefix + "alpha": [0.1, 1.0, 10.0]},
        ("regression", "random_forest"): {prefix + "max_depth": [None, 8, 16], prefix + "min_samples_leaf": [1, 3]},
        ("regression", "extra_trees"): {prefix + "max_depth": [None, 10, 20], prefix + "min_samples_leaf": [1, 2]},
        ("regression", "gradient_boosting"): {prefix + "learning_rate": [0.05, 0.1], prefix + "n_estimators": [100, 200]},
        ("regression", "hist_gradient_boosting"): {prefix + "learning_rate": [0.05, 0.1], prefix + "max_leaf_nodes": [15, 31]},
        ("regression", "svm"): {prefix + "C": [0.5, 1.0, 2.0], prefix + "epsilon": [0.05, 0.1, 0.2]},
        ("regression", "xgboost"): {prefix + "max_depth": [4, 6], prefix + "learning_rate": [0.03, 0.08]},
        ("regression", "lightgbm"): {prefix + "num_leaves": [15, 31], prefix + "learning_rate": [0.03, 0.08]},
        ("regression", "catboost"): {prefix + "depth": [4, 6], prefix + "learning_rate": [0.03, 0.08]},
    }
    return grids.get((task, algorithm), {})


def _feature_importance(pipe: Pipeline, X: pd.DataFrame, y: pd.Series, task: str, metric: str) -> list[dict[str, Any]]:
    if X.empty or len(X.columns) == 0:
        return []
    try:
        scoring = _scoring_name(task, metric)
        perm = permutation_importance(pipe, X, y, scoring=scoring, n_repeats=3, random_state=42, n_jobs=1)
        rows = [
            {"feature": col, "importance": round(float(mean), 8), "std": round(float(std), 8)}
            for col, mean, std in zip(X.columns, perm.importances_mean, perm.importances_std)
        ]
        return sorted(rows, key=lambda r: abs(r["importance"]), reverse=True)
    except Exception:
        return []


def _save_model(payload: dict[str, Any], card: dict[str, Any]) -> str:
    model_id = card["model_id"]
    root = get_settings().model_dir
    joblib.dump(payload, root / f"{model_id}.joblib")
    (root / f"{model_id}.card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return model_id


def _model_card(
    *, model_id: str, dataset_context: dict[str, Any] | None, target: str, task: str, algorithm: str,
    features: list[str], primary_metric: str, metrics: dict[str, float], validation_metrics: dict[str, float],
    rows: dict[str, int], cv: dict[str, Any], guardrails: list[dict[str, Any]], importance: list[dict[str, Any]],
    best_params: dict[str, Any] | None = None,
    safety_audit: dict[str, Any] | None = None,
    split_audit: dict[str, Any] | None = None,
    training_metrics: dict[str, float] | None = None,
    overfitting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "created_at": _utcnow(),
        "dataset": dataset_context or {},
        "target": target,
        "task": task,
        "algorithm": algorithm,
        "features": features,
        "primary_metric": primary_metric,
        "metrics_final_test": metrics,
        "metrics_validation": validation_metrics,
        "rows": rows,
        "validation_strategy": {
            "split": "60% train / 20% validation / 20% final test",
            "strategy": (split_audit or {}).get("strategy", "random"),
            "time_column": (split_audit or {}).get("time_column"),
            "random_state": 42 if (split_audit or {}).get("strategy", "random") == "random" else None,
            "cross_validation": cv,
            "test_policy": "Le jeu de test final n'est pas utilisé pour sélectionner ou optimiser le modèle.",
            "split_audit": split_audit or {},
        },
        "metrics_training": training_metrics or {},
        "overfitting_assessment": overfitting or {},
        "safety_audit": safety_audit or {},
        "best_params": best_params or {},
        "guardrails": guardrails,
        "feature_importance": importance,
        "known_limitations": [
            "Les contrôles de leakage sont heuristiques et ne remplacent pas la connaissance métier.",
            "Les métriques peuvent varier si la distribution future diffère des données d'entraînement.",
            "Les métriques de performance par groupe dépendent des variables d’audit explicitement sélectionnées et de leur effectif.",
        ],
        "fairness": {"status": "not_evaluated", "selection_policy": "explicit_group_columns_only"},
        "responsible_ai": {"status": "not_evaluated", "publication_thresholds": "organization_defined"},
        "explainability": {"permutation_importance": bool(importance), "local_perturbation": True, "diagnostics": True, "partial_dependence": True, "counterfactual_search": True, "shap": "optional_runtime"},
    }


def train_model(
    df: pd.DataFrame,
    target: str,
    task: str = "auto",
    algorithm: str = "auto",
    dataset_context: dict[str, Any] | None = None,
) -> TrainingResult:
    if target not in df.columns:
        raise ValueError("Variable cible inconnue")
    work = df.dropna(subset=[target]).copy()
    if len(work) < 30:
        raise ValueError("Échantillon insuffisant: au moins 30 lignes complètes sur la cible sont requises.")

    y = work[target]
    X = work.drop(columns=[target])
    resolved_task = _task_for_target(y, task)
    if resolved_task == "classification" and y.nunique() < 2:
        raise ValueError("La cible de classification doit contenir au moins deux classes")

    default_algo = "logistic_regression" if resolved_task == "classification" else "linear_regression"
    chosen = default_algo if algorithm == "auto" else algorithm
    valid = CLASSIFICATION_ALGORITHMS if resolved_task == "classification" else REGRESSION_ALGORITHMS
    if chosen not in valid:
        raise ValueError(f"{chosen} n'est pas compatible avec la tâche {resolved_task}")

    prep, _, _ = _build_preprocessor(X)
    X_train, X_val, X_test, y_train, y_val, y_test, split_audit = _safe_split(X, y, resolved_task)
    pipe = Pipeline([("preprocess", prep), ("model", _estimator(resolved_task, chosen))])
    pipe.fit(X_train, y_train)
    validation_metrics = _evaluate(pipe, X_val, y_val, resolved_task)

    # Refit on development data only after validation; final test remains untouched until now.
    X_dev = pd.concat([X_train, X_val], axis=0)
    y_dev = pd.concat([y_train, y_val], axis=0)
    pipe.fit(X_dev, y_dev)
    metrics = _evaluate(pipe, X_test, y_test, resolved_task)
    primary = _primary_metric(resolved_task, y, "auto")
    importance = _feature_importance(pipe, X_test, y_test, resolved_task, primary)
    guardrails = _guardrails(work, target, resolved_task)
    model_id = str(uuid.uuid4())
    card = _model_card(
        model_id=model_id, dataset_context=dataset_context, target=target, task=resolved_task, algorithm=chosen,
        features=list(X.columns), primary_metric=primary, metrics=metrics, validation_metrics=validation_metrics,
        rows={"train": len(X_train), "validation": len(X_val), "test": len(X_test)},
        cv={"folds": 0, "status": "single_model_training"}, guardrails=guardrails, importance=importance, split_audit=split_audit,
    )
    payload = {"pipeline": pipe, "target": target, "features": list(X.columns), "task": resolved_task, "algorithm": chosen, "model_card": card, "feature_baselines": _feature_baselines(X_dev), "evaluation_indices": X_test.index.tolist()}
    _save_model(payload, card)
    return TrainingResult(model_id, resolved_task, chosen, metrics, len(X_train), len(X_test), len(X_val), validation_metrics, guardrails, importance, card)


def automl_train(
    df: pd.DataFrame,
    target: str,
    task: str = "auto",
    primary_metric: str = "auto",
    cv_folds: int = 5,
    tune: bool = True,
    max_candidates: int = 5,
    dataset_context: dict[str, Any] | None = None,
    split_strategy: str = "auto",
    time_column: str | None = None,
) -> dict[str, Any]:
    if target not in df.columns:
        raise ValueError("Variable cible inconnue")
    work = df.dropna(subset=[target]).copy()
    if len(work) < 40:
        raise ValueError("AutoML requiert au moins 40 lignes complètes sur la cible.")

    y = work[target]
    X_all = work.drop(columns=[target])
    resolved_task = _task_for_target(y, task)
    safety_audit = audit_supervised_ml(
        work, target=target, task=resolved_task, requested_metric=primary_metric,
        split_strategy=split_strategy, time_column=time_column,
    )
    if safety_audit.get("status") == "blocked":
        reasons = "; ".join(str(item.get("message")) for item in safety_audit.get("findings", []) if item.get("severity") == "blocking")
        raise ValueError(f"ML Safety bloque l'entraînement: {reasons}")
    primary = str((safety_audit.get("metric_policy") or {}).get("effective") or _primary_metric(resolved_task, y, primary_metric))
    scoring = _scoring_name(resolved_task, primary)
    excluded_features = [str(item.get("column")) for item in safety_audit.get("excluded_features", [])]
    X = X_all.drop(columns=[c for c in excluded_features if c in X_all.columns])
    if X.shape[1] == 0:
        raise ValueError("Toutes les variables explicatives ont été exclues par ML Safety.")
    effective_split = str((safety_audit.get("split_policy") or {}).get("strategy") or "random")
    effective_time = (safety_audit.get("split_policy") or {}).get("time_column")
    time_values = work[str(effective_time)] if effective_time and str(effective_time) in work.columns else None
    X_train, X_val, X_test, y_train, y_val, y_test, split_audit = _safe_split(
        X, y, resolved_task, split_strategy=effective_split, time_values=time_values,
    )
    cv, actual_folds = _cv_strategy(resolved_task, y_train, cv_folds, split_strategy=effective_split)
    guardrails = list(safety_audit.get("findings") or [])
    candidates = _candidate_algorithms(resolved_task, max_candidates)
    benchmark: list[dict[str, Any]] = []

    for algorithm in candidates:
        row: dict[str, Any] = {
            "algorithm": algorithm,
            "label": (
                CLASSIFICATION_ALGORITHMS
                if resolved_task == "classification"
                else REGRESSION_ALGORITHMS
            )[algorithm],
            "primary_metric": primary,
            "cv_folds": actual_folds,
            "status": "ok",
            "engine": algorithm_availability().get(
                algorithm,
                {},
            ).get("engine", "unknown"),
        }
        try:
            prep, _, _ = _build_preprocessor(X_train)
            pipe = Pipeline(
                [
                    ("preprocess", prep),
                    (
                        "model",
                        _estimator(
                            resolved_task,
                            algorithm,
                        ),
                    ),
                ]
            )
            cv_mean = None
            cv_std = None
            if cv is not None:
                scores = cross_val_score(
                    pipe,
                    X_train,
                    y_train,
                    scoring=scoring,
                    cv=cv,
                    n_jobs=1,
                    error_score="raise",
                )
                display_scores = (
                    -scores
                    if primary in {"rmse", "mae"}
                    else scores
                )
                cv_mean = float(
                    np.mean(display_scores)
                )
                cv_std = float(
                    np.std(display_scores)
                )

            pipe.fit(X_train, y_train)
            val_metrics = _evaluate(
                pipe,
                X_val,
                y_val,
                resolved_task,
            )
            row.update(
                {
                    "validation_score": val_metrics.get(
                        primary
                    ),
                    "validation_metrics": val_metrics,
                    "cv_mean": (
                        round(cv_mean, 6)
                        if cv_mean is not None
                        else None
                    ),
                    "cv_std": (
                        round(cv_std, 6)
                        if cv_std is not None
                        else None
                    ),
                }
            )
        except Exception as exc:
            row.update(
                {
                    "status": "error",
                    "validation_score": None,
                    "validation_metrics": {},
                    "cv_mean": None,
                    "cv_std": None,
                    "error": (
                        f"{type(exc).__name__}: "
                        f"{str(exc)[:400]}"
                    ),
                }
            )
        benchmark.append(row)

    benchmark.sort(
        key=lambda row: _metric_value(
            row.get("validation_metrics") or {},
            primary,
        ),
        reverse=True,
    )
    successful = [
        row
        for row in benchmark
        if row.get("status") == "ok"
    ]
    if not successful:
        raise RuntimeError(
            "Aucun candidat AutoML n'a pu être entraîné."
        )
    best_algorithm = successful[0]["algorithm"]

    # Controlled tuning uses train only and never sees validation/test.
    prep, _, _ = _build_preprocessor(X_train)
    base_pipe = Pipeline([("preprocess", prep), ("model", _estimator(resolved_task, best_algorithm))])
    best_params: dict[str, Any] = {}
    tuned_pipe = base_pipe
    grid = _tuning_grid(resolved_task, best_algorithm) if tune else {}
    if grid and cv is not None:
        search = GridSearchCV(base_pipe, grid, scoring=scoring, cv=cv, n_jobs=1, refit=True, error_score="raise")
        search.fit(X_train, y_train)
        tuned_pipe = search.best_estimator_
        best_params = {k.replace("model__", ""): v for k, v in search.best_params_.items()}
    else:
        tuned_pipe.fit(X_train, y_train)

    tuned_training_metrics = _evaluate(tuned_pipe, X_train, y_train, resolved_task)
    tuned_validation_metrics = _evaluate(tuned_pipe, X_val, y_val, resolved_task)
    overfitting = assess_overfitting(tuned_training_metrics, tuned_validation_metrics, primary)
    guardrails.append({
        "code": "overfitting_check",
        "severity": overfitting.get("severity", "info"),
        "message": (
            f"Contrôle surapprentissage {primary}: écart train/validation={overfitting.get('gap')}"
            if overfitting.get("gap") is not None else "Contrôle surapprentissage indisponible pour cette métrique."
        ),
        "details": overfitting,
    })

    # Final refit on train + validation after selection/tuning. Test remains untouched until final evaluation.
    X_dev = pd.concat([X_train, X_val], axis=0)
    y_dev = pd.concat([y_train, y_val], axis=0)
    final_prep, _, _ = _build_preprocessor(X_dev)
    final_model = _estimator(resolved_task, best_algorithm)
    if best_params:
        final_model.set_params(**best_params)
    final_pipe = Pipeline([("preprocess", final_prep), ("model", final_model)])
    final_pipe.fit(X_dev, y_dev)
    final_metrics = _evaluate(final_pipe, X_test, y_test, resolved_task)
    importance = _feature_importance(final_pipe, X_test, y_test, resolved_task, primary)

    model_id = str(uuid.uuid4())
    card = _model_card(
        model_id=model_id, dataset_context=dataset_context, target=target, task=resolved_task, algorithm=best_algorithm,
        features=list(X.columns), primary_metric=primary, metrics=final_metrics, validation_metrics=tuned_validation_metrics,
        rows={"train": len(X_train), "validation": len(X_val), "test": len(X_test)},
        cv={"folds": actual_folds, "scoring": scoring, "selection": "validation after CV on training only"},
        guardrails=guardrails, importance=importance, best_params=best_params,
        safety_audit=safety_audit, split_audit=split_audit, training_metrics=tuned_training_metrics, overfitting=overfitting,
    )
    card["excluded_features"] = excluded_features
    payload = {
        "pipeline": final_pipe, "target": target, "features": list(X.columns), "task": resolved_task,
        "algorithm": best_algorithm, "model_card": card,
        "feature_baselines": _feature_baselines(X_dev), "evaluation_indices": X_test.index.tolist(),
    }
    _save_model(payload, card)

    return {
        "model_id": model_id,
        "task": resolved_task,
        "algorithm": best_algorithm,
        "primary_metric": primary,
        "metrics": final_metrics,
        "validation_metrics": tuned_validation_metrics,
        "rows_train": len(X_train),
        "rows_validation": len(X_val),
        "rows_test": len(X_test),
        "benchmark": benchmark,
        "best_params": best_params,
        "guardrails": guardrails,
        "safety_audit": safety_audit,
        "split_audit": split_audit,
        "training_metrics": tuned_training_metrics,
        "overfitting_assessment": overfitting,
        "excluded_features": excluded_features,
        "feature_importance": importance,
        "model_card": card,
    }



def benchmark_models(
    df: pd.DataFrame,
    target: str,
    task: str = "auto",
    primary_metric: str = "auto",
    cv_folds: int = 5,
    max_candidates: int = 10,
    split_strategy: str = "auto",
    time_column: str | None = None,
) -> dict[str, Any]:
    if target not in df.columns:
        raise ValueError("Variable cible inconnue")

    work = df.dropna(subset=[target]).copy()
    if len(work) < 40:
        raise ValueError(
            "Le benchmark requiert au moins 40 lignes complètes sur la cible."
        )

    y = work[target]
    X_all = work.drop(columns=[target])
    resolved_task = _task_for_target(y, task)
    safety_audit = audit_supervised_ml(
        work, target=target, task=resolved_task, requested_metric=primary_metric,
        split_strategy=split_strategy, time_column=time_column,
    )
    if safety_audit.get("status") == "blocked":
        reasons = "; ".join(str(item.get("message")) for item in safety_audit.get("findings", []) if item.get("severity") == "blocking")
        raise ValueError(f"ML Safety bloque le benchmark: {reasons}")
    primary = str((safety_audit.get("metric_policy") or {}).get("effective") or _primary_metric(resolved_task, y, primary_metric))
    scoring = _scoring_name(resolved_task, primary)
    excluded_features = [str(item.get("column")) for item in safety_audit.get("excluded_features", [])]
    X = X_all.drop(columns=[c for c in excluded_features if c in X_all.columns])
    if X.shape[1] == 0:
        raise ValueError("Toutes les variables explicatives ont été exclues par ML Safety.")
    effective_split = str((safety_audit.get("split_policy") or {}).get("strategy") or "random")
    effective_time = (safety_audit.get("split_policy") or {}).get("time_column")
    time_values = work[str(effective_time)] if effective_time and str(effective_time) in work.columns else None
    X_train, X_val, _X_test, y_train, y_val, _y_test, split_audit = _safe_split(
        X, y, resolved_task, split_strategy=effective_split, time_values=time_values
    )
    cv, actual_folds = _cv_strategy(
        resolved_task, y_train, cv_folds, split_strategy=effective_split
    )
    algorithms = _candidate_algorithms(
        resolved_task,
        max_candidates,
    )
    catalog = (
        CLASSIFICATION_ALGORITHMS
        if resolved_task == "classification"
        else REGRESSION_ALGORITHMS
    )
    availability = algorithm_availability()
    rows: list[dict[str, Any]] = []

    for algorithm in algorithms:
        row: dict[str, Any] = {
            "algorithm": algorithm,
            "label": catalog[algorithm],
            "engine": availability[algorithm]["engine"],
            "status": "ok",
            "primary_metric": primary,
            "cv_folds": actual_folds,
        }
        try:
            prep, _, _ = _build_preprocessor(X_train)
            pipe = Pipeline(
                [
                    ("preprocess", prep),
                    ("model", _estimator(resolved_task, algorithm)),
                ]
            )

            if cv is not None:
                scores = cross_val_score(
                    pipe,
                    X_train,
                    y_train,
                    scoring=scoring,
                    cv=cv,
                    n_jobs=1,
                    error_score="raise",
                )
                display_scores = (
                    -scores if primary in {"rmse", "mae"} else scores
                )
                row["cv_mean"] = round(
                    float(np.mean(display_scores)), 6
                )
                row["cv_std"] = round(
                    float(np.std(display_scores)), 6
                )
            else:
                row["cv_mean"] = None
                row["cv_std"] = None

            pipe.fit(X_train, y_train)
            metrics = _evaluate(
                pipe,
                X_val,
                y_val,
                resolved_task,
            )
            row["validation_metrics"] = metrics
            row["validation_score"] = metrics.get(primary)
            row["selection_value"] = _metric_value(
                metrics,
                primary,
            )
        except Exception as exc:
            row.update(
                {
                    "status": "error",
                    "error": (
                        f"{type(exc).__name__}: {str(exc)[:400]}"
                    ),
                    "validation_metrics": {},
                    "validation_score": None,
                    "selection_value": -float("inf"),
                }
            )
        rows.append(row)

    rows.sort(
        key=lambda item: float(
            item.get("selection_value", -float("inf"))
        ),
        reverse=True,
    )
    successful = [item for item in rows if item["status"] == "ok"]

    return {
        "task": resolved_task,
        "target": target,
        "primary_metric": primary,
        "rows": len(work),
        "features": list(X.columns),
        "excluded_features": excluded_features,
        "safety_audit": safety_audit,
        "split_audit": split_audit,
        "cv_folds": actual_folds,
        "availability": availability,
        "benchmark": rows,
        "best": successful[0] if successful else None,
        "selection_policy": (
            "Classement sur validation; cross-validation exécutée "
            "uniquement sur le sous-ensemble d'entraînement."
        ),
    }

def predict(model_id: str, rows: list[dict]) -> dict:
    path = get_settings().model_dir / f"{model_id}.joblib"
    if not path.exists():
        raise FileNotFoundError(model_id)
    payload = joblib.load(path)
    if not rows:
        raise ValueError("Aucune observation fournie")
    frame = pd.DataFrame(rows)
    missing = [c for c in payload["features"] if c not in frame.columns]
    if missing:
        raise ValueError(f"Variables manquantes: {missing}")
    frame = frame[payload["features"]]
    pipe = payload["pipeline"]
    preds = pipe.predict(frame)
    result = {"model_id": model_id, "predictions": [x.item() if hasattr(x, "item") else x for x in preds]}
    if payload["task"] == "classification" and hasattr(pipe, "predict_proba"):
        result["probabilities"] = pipe.predict_proba(frame).tolist()
        try:
            result["classes"] = [x.item() if hasattr(x, "item") else x for x in pipe.classes_]
        except Exception:
            pass
    return result


def get_model_card(model_id: str) -> dict[str, Any]:
    path = get_settings().model_dir / f"{model_id}.card.json"
    if not path.exists():
        raise FileNotFoundError(model_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_model_cards(dataset_id: str | None = None) -> list[dict[str, Any]]:
    root: Path = get_settings().model_dir
    cards: list[dict[str, Any]] = []
    for path in root.glob("*.card.json"):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if dataset_id and card.get("dataset", {}).get("id") != dataset_id:
            continue
        cards.append(card)
    cards.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return cards
