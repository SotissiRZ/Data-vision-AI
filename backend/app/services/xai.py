from __future__ import annotations

import importlib.util
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    brier_score_loss, confusion_matrix, mean_absolute_error, mean_squared_error,
    precision_recall_curve, r2_score, roc_auc_score, roc_curve,
)

from app.core.config import get_settings


def _payload(model_id: str) -> dict[str, Any]:
    path = get_settings().model_dir / f"{model_id}.joblib"
    if not path.exists():
        raise FileNotFoundError(model_id)
    return joblib.load(path)


def _scalar(v: Any) -> Any:
    return v.item() if hasattr(v, "item") else v


def _evaluation_frame(payload: dict[str, Any], df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, str]:
    target = payload["target"]
    features = payload["features"]
    if target not in df.columns:
        raise ValueError("La cible du modèle n'existe plus dans le dataset de référence")
    work = df.dropna(subset=[target]).copy()
    indices = payload.get("evaluation_indices") or []
    if indices:
        try:
            subset = work.loc[work.index.intersection(indices)]
            if len(subset) >= 5:
                work = subset
                source = "final_test_holdout"
            else:
                source = "reference_dataset"
        except Exception:
            source = "reference_dataset"
    else:
        source = "reference_dataset"
    missing = [c for c in features if c not in work.columns]
    if missing:
        raise ValueError(f"Variables du modèle absentes du dataset: {missing}")
    return work[features], work[target], source


def model_diagnostics(model_id: str, df: pd.DataFrame) -> dict[str, Any]:
    payload = _payload(model_id)
    pipe = payload["pipeline"]
    task = payload["task"]
    X, y, source = _evaluation_frame(payload, df)
    pred = pipe.predict(X)
    result: dict[str, Any] = {
        "model_id": model_id,
        "task": task,
        "evaluation_source": source,
        "rows": len(X),
        "shap": {"available": importlib.util.find_spec("shap") is not None, "executed": False},
    }

    # Global importance on the evaluation set. Model Card importance remains the persisted reference.
    scoring = "f1_weighted" if task == "classification" else "neg_root_mean_squared_error"
    try:
        perm = permutation_importance(pipe, X, y, scoring=scoring, n_repeats=3, random_state=42, n_jobs=1)
        result["permutation_importance"] = sorted([
            {"feature": c, "importance": round(float(m), 8), "std": round(float(s), 8)}
            for c, m, s in zip(X.columns, perm.importances_mean, perm.importances_std)
        ], key=lambda r: abs(r["importance"]), reverse=True)
    except Exception:
        result["permutation_importance"] = payload.get("model_card", {}).get("feature_importance", [])

    if task == "classification":
        classes = [_scalar(x) for x in getattr(pipe, "classes_", sorted(pd.unique(y)))]
        matrix = confusion_matrix(y, pred, labels=classes)
        result["classes"] = classes
        result["confusion_matrix"] = matrix.tolist()
        if len(classes) == 2 and hasattr(pipe, "predict_proba"):
            probs = pipe.predict_proba(X)[:, 1]
            positive = classes[1]
            y_bin = (pd.Series(y).to_numpy() == positive).astype(int)
            fpr, tpr, thresholds = roc_curve(y_bin, probs)
            precision, recall, pr_thresholds = precision_recall_curve(y_bin, probs)
            frac_pos, mean_pred = calibration_curve(y_bin, probs, n_bins=min(10, max(3, len(y_bin)//10)), strategy="quantile")
            result["roc_auc"] = round(float(roc_auc_score(y_bin, probs)), 6)
            result["brier_score"] = round(float(brier_score_loss(y_bin, probs)), 6)
            result["roc_curve"] = [{"fpr": round(float(a), 6), "tpr": round(float(b), 6), "threshold": None if not np.isfinite(c) else round(float(c), 6)} for a,b,c in zip(fpr,tpr,thresholds)]
            result["pr_curve"] = [{"recall": round(float(r), 6), "precision": round(float(p), 6)} for r,p in zip(recall,precision)]
            result["calibration"] = [{"mean_predicted": round(float(a), 6), "fraction_positive": round(float(b), 6)} for a,b in zip(mean_pred,frac_pos)]
        return result

    residuals = pd.Series(y.to_numpy(dtype=float) - np.asarray(pred, dtype=float))
    result["metrics"] = {
        "mae": round(float(mean_absolute_error(y, pred)), 6),
        "rmse": round(float(mean_squared_error(y, pred) ** 0.5), 6),
        "r2": round(float(r2_score(y, pred)), 6),
        "residual_mean": round(float(residuals.mean()), 6),
        "residual_std": round(float(residuals.std(ddof=1)), 6),
    }
    points = []
    for observed, predicted, residual in list(zip(y, pred, residuals))[:500]:
        points.append({"observed": round(float(observed), 6), "predicted": round(float(predicted), 6), "residual": round(float(residual), 6)})
    result["residual_points"] = points
    return result


def local_explanation(model_id: str, row: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(model_id)
    features = payload["features"]
    missing = [c for c in features if c not in row]
    if missing:
        raise ValueError(f"Variables manquantes: {missing}")
    pipe = payload["pipeline"]
    frame = pd.DataFrame([{c: row[c] for c in features}]).astype(object)
    baseline = payload.get("feature_baselines") or {}
    if not baseline:
        raise ValueError("Ce modèle ne contient pas encore de baseline XAI. Réentraînez-le avec DataVision v0.8.")

    task = payload["task"]
    prediction = _scalar(pipe.predict(frame)[0])
    contributions: list[dict[str, Any]] = []
    if task == "classification" and hasattr(pipe, "predict_proba"):
        classes = [_scalar(x) for x in pipe.classes_]
        probs = pipe.predict_proba(frame)[0]
        class_idx = classes.index(prediction) if prediction in classes else int(np.argmax(probs))
        base_score = float(probs[class_idx])
        for feature in features:
            altered = frame.copy()
            altered.at[0, feature] = baseline.get(feature)
            alt_prob = float(pipe.predict_proba(altered)[0][class_idx])
            contributions.append({
                "feature": feature, "value": _scalar(row[feature]), "baseline": _scalar(baseline.get(feature)),
                "effect": round(base_score - alt_prob, 8),
            })
        contributions.sort(key=lambda r: abs(r["effect"]), reverse=True)
        return {
            "model_id": model_id, "task": task, "prediction": prediction,
            "classes": classes, "probabilities": [round(float(x), 8) for x in probs],
            "explained_class": classes[class_idx], "explained_probability": round(base_score, 8),
            "method": "one-feature-at-a-time baseline perturbation",
            "contributions": contributions,
            "caveat": "Les effets sont des perturbations locales, pas des contributions additives de type SHAP.",
        }

    base_score = float(prediction)
    for feature in features:
        altered = frame.copy()
        altered.at[0, feature] = baseline.get(feature)
        alt = float(pipe.predict(altered)[0])
        contributions.append({
            "feature": feature, "value": _scalar(row[feature]), "baseline": _scalar(baseline.get(feature)),
            "effect": round(base_score - alt, 8),
        })
    contributions.sort(key=lambda r: abs(r["effect"]), reverse=True)
    return {
        "model_id": model_id, "task": task, "prediction": round(base_score, 8),
        "method": "one-feature-at-a-time baseline perturbation",
        "contributions": contributions,
        "caveat": "Les effets sont des perturbations locales, pas des contributions additives de type SHAP.",
    }
