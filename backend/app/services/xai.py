from __future__ import annotations

import importlib.util
import itertools
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_curve,
    r2_score,
    roc_auc_score,
    roc_curve,
)

from app.core.config import get_settings


def _payload(model_id: str) -> dict[str, Any]:
    path = get_settings().model_dir / f"{model_id}.joblib"
    if not path.exists():
        raise FileNotFoundError(model_id)
    return joblib.load(path)


def _scalar(v: Any) -> Any:
    return v.item() if hasattr(v, "item") else v


def _evaluation_frame(
    payload: dict[str, Any],
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, str]:
    target = payload["target"]
    features = payload["features"]
    if target not in df.columns:
        raise ValueError(
            "La cible du modèle n'existe plus dans le dataset de référence"
        )
    work = df.dropna(subset=[target]).copy()
    indices = payload.get("evaluation_indices") or []
    source = "reference_dataset"
    if indices:
        try:
            subset = work.loc[work.index.intersection(indices)]
            if len(subset) >= 5:
                work = subset
                source = "final_test_holdout"
        except Exception:
            source = "reference_dataset"

    missing = [c for c in features if c not in work.columns]
    if missing:
        raise ValueError(
            f"Variables du modèle absentes du dataset: {missing}"
        )
    return work[features], work[target], source


def _expected_calibration_error(
    y_bin: np.ndarray,
    probs: np.ndarray,
    bins: int = 10,
) -> float:
    if len(y_bin) == 0:
        return float("nan")
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    total = len(y_bin)
    error = 0.0
    for index in range(bins):
        lo, hi = boundaries[index], boundaries[index + 1]
        if index == bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        confidence = float(np.mean(probs[mask]))
        accuracy = float(np.mean(y_bin[mask]))
        error += (count / total) * abs(accuracy - confidence)
    return float(error)


def model_diagnostics(
    model_id: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    payload = _payload(model_id)
    pipe = payload["pipeline"]
    task = payload["task"]
    X, y, source = _evaluation_frame(payload, df)
    pred = pipe.predict(X)

    result: dict[str, Any] = {
        "model_id": model_id,
        "task": task,
        "algorithm": payload.get("algorithm"),
        "evaluation_source": source,
        "rows": len(X),
        "shap": {
            "available": importlib.util.find_spec("shap") is not None,
            "executed": False,
        },
    }

    scoring = (
        "f1_weighted"
        if task == "classification"
        else "neg_root_mean_squared_error"
    )
    try:
        perm = permutation_importance(
            pipe,
            X,
            y,
            scoring=scoring,
            n_repeats=5,
            random_state=42,
            n_jobs=1,
        )
        result["permutation_importance"] = sorted(
            [
                {
                    "feature": c,
                    "importance": round(float(m), 8),
                    "std": round(float(s), 8),
                }
                for c, m, s in zip(
                    X.columns,
                    perm.importances_mean,
                    perm.importances_std,
                )
            ],
            key=lambda row: abs(row["importance"]),
            reverse=True,
        )
    except Exception:
        result["permutation_importance"] = (
            payload.get("model_card", {}).get("feature_importance", [])
        )

    if task == "classification":
        classes = [
            _scalar(x)
            for x in getattr(
                pipe,
                "classes_",
                sorted(pd.unique(y)),
            )
        ]
        matrix = confusion_matrix(y, pred, labels=classes)
        result["classes"] = classes
        result["confusion_matrix"] = matrix.tolist()

        if len(classes) == 2 and hasattr(pipe, "predict_proba"):
            probs = np.asarray(pipe.predict_proba(X)[:, 1], dtype=float)
            positive = classes[1]
            y_bin = (
                pd.Series(y).to_numpy() == positive
            ).astype(int)
            fpr, tpr, thresholds = roc_curve(y_bin, probs)
            precision, recall, _pr_thresholds = precision_recall_curve(
                y_bin,
                probs,
            )
            frac_pos, mean_pred = calibration_curve(
                y_bin,
                probs,
                n_bins=min(10, max(3, len(y_bin) // 10)),
                strategy="quantile",
            )
            result["roc_auc"] = round(
                float(roc_auc_score(y_bin, probs)), 6
            )
            result["brier_score"] = round(
                float(brier_score_loss(y_bin, probs)), 6
            )
            result["expected_calibration_error"] = round(
                _expected_calibration_error(y_bin, probs), 6
            )
            result["roc_curve"] = [
                {
                    "fpr": round(float(a), 6),
                    "tpr": round(float(b), 6),
                    "threshold": (
                        None
                        if not np.isfinite(c)
                        else round(float(c), 6)
                    ),
                }
                for a, b, c in zip(fpr, tpr, thresholds)
            ]
            result["pr_curve"] = [
                {
                    "recall": round(float(r), 6),
                    "precision": round(float(p), 6),
                }
                for r, p in zip(recall, precision)
            ]
            result["calibration"] = [
                {
                    "mean_predicted": round(float(a), 6),
                    "fraction_positive": round(float(b), 6),
                }
                for a, b in zip(mean_pred, frac_pos)
            ]
        return result

    residuals = pd.Series(
        y.to_numpy(dtype=float) - np.asarray(pred, dtype=float)
    )
    result["metrics"] = {
        "mae": round(float(mean_absolute_error(y, pred)), 6),
        "rmse": round(float(mean_squared_error(y, pred) ** 0.5), 6),
        "r2": round(float(r2_score(y, pred)), 6),
        "residual_mean": round(float(residuals.mean()), 6),
        "residual_std": round(float(residuals.std(ddof=1)), 6),
    }
    points = []
    for observed, predicted, residual in list(
        zip(y, pred, residuals)
    )[:500]:
        points.append(
            {
                "observed": round(float(observed), 6),
                "predicted": round(float(predicted), 6),
                "residual": round(float(residual), 6),
            }
        )
    result["residual_points"] = points
    return result


def local_explanation(
    model_id: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    payload = _payload(model_id)
    features = payload["features"]
    missing = [c for c in features if c not in row]
    if missing:
        raise ValueError(f"Variables manquantes: {missing}")

    pipe = payload["pipeline"]
    frame = pd.DataFrame(
        [{c: row[c] for c in features}]
    ).astype(object)
    baseline = payload.get("feature_baselines") or {}
    if not baseline:
        raise ValueError(
            "Ce modèle ne contient pas de baseline XAI. "
            "Réentraînez-le avec une version récente de DataVision."
        )

    task = payload["task"]
    prediction = _scalar(pipe.predict(frame)[0])
    contributions: list[dict[str, Any]] = []

    if task == "classification" and hasattr(
        pipe,
        "predict_proba",
    ):
        classes = [_scalar(x) for x in pipe.classes_]
        probs = pipe.predict_proba(frame)[0]
        class_idx = (
            classes.index(prediction)
            if prediction in classes
            else int(np.argmax(probs))
        )
        base_score = float(probs[class_idx])
        for feature in features:
            altered = frame.copy()
            altered.at[0, feature] = baseline.get(feature)
            alt_prob = float(
                pipe.predict_proba(altered)[0][class_idx]
            )
            contributions.append(
                {
                    "feature": feature,
                    "value": _scalar(row[feature]),
                    "baseline": _scalar(baseline.get(feature)),
                    "effect": round(base_score - alt_prob, 8),
                }
            )
        contributions.sort(
            key=lambda r: abs(r["effect"]),
            reverse=True,
        )
        return {
            "model_id": model_id,
            "task": task,
            "prediction": prediction,
            "classes": classes,
            "probabilities": [
                round(float(x), 8) for x in probs
            ],
            "explained_class": classes[class_idx],
            "explained_probability": round(base_score, 8),
            "method": "one-feature-at-a-time baseline perturbation",
            "contributions": contributions,
            "caveat": (
                "Les effets sont des perturbations locales du modèle, "
                "pas des effets causaux."
            ),
        }

    base_score = float(prediction)
    for feature in features:
        altered = frame.copy()
        altered.at[0, feature] = baseline.get(feature)
        alt = float(pipe.predict(altered)[0])
        contributions.append(
            {
                "feature": feature,
                "value": _scalar(row[feature]),
                "baseline": _scalar(baseline.get(feature)),
                "effect": round(base_score - alt, 8),
            }
        )
    contributions.sort(
        key=lambda r: abs(r["effect"]),
        reverse=True,
    )
    return {
        "model_id": model_id,
        "task": task,
        "prediction": round(base_score, 8),
        "method": "one-feature-at-a-time baseline perturbation",
        "contributions": contributions,
        "caveat": (
            "Les effets sont des perturbations locales du modèle, "
            "pas des effets causaux."
        ),
    }


def xai_capabilities(model_id: str) -> dict[str, Any]:
    payload = _payload(model_id)
    return {
        "model_id": model_id,
        "task": payload.get("task"),
        "algorithm": payload.get("algorithm"),
        "permutation_importance": True,
        "partial_dependence": True,
        "calibration": payload.get("task") == "classification",
        "counterfactual_search": True,
        "local_perturbation": True,
        "shap": {
            "installed": importlib.util.find_spec("shap") is not None,
            "mode": "native_or_permutation",
        },
        "causal_claims": False,
    }


def partial_dependence(
    model_id: str,
    df: pd.DataFrame,
    features: list[str],
    *,
    grid_points: int = 20,
    class_label: Any | None = None,
) -> dict[str, Any]:
    payload = _payload(model_id)
    pipe = payload["pipeline"]
    model_features = list(payload["features"])
    requested = [f for f in features if f in model_features]
    if not requested:
        raise ValueError(
            "Aucune variable PDP valide n'a été fournie."
        )

    X, _y, source = _evaluation_frame(payload, df)
    sample = X.sample(
        n=min(500, len(X)),
        random_state=42,
    ) if len(X) > 500 else X.copy()

    task = payload["task"]
    classes = (
        [_scalar(x) for x in pipe.classes_]
        if task == "classification"
        and hasattr(pipe, "classes_")
        else []
    )

    target_class = class_label
    if task == "classification" and target_class is None and classes:
        target_class = classes[-1]

    curves: list[dict[str, Any]] = []
    for feature in requested[:8]:
        series = X[feature]
        if pd.api.types.is_numeric_dtype(series):
            clean = pd.to_numeric(series, errors="coerce").dropna()
            if clean.empty:
                continue
            quantiles = np.linspace(
                0.05,
                0.95,
                max(3, min(int(grid_points), 40)),
            )
            values = np.unique(
                np.quantile(clean.to_numpy(dtype=float), quantiles)
            ).tolist()
            kind = "numeric"
        else:
            values = (
                series.dropna()
                .astype(str)
                .value_counts()
                .head(min(12, max(3, int(grid_points))))
                .index.tolist()
            )
            kind = "categorical"

        points: list[dict[str, Any]] = []
        for value in values:
            altered = sample.copy()
            altered.loc[:, feature] = value

            if (
                task == "classification"
                and hasattr(pipe, "predict_proba")
            ):
                probabilities = np.asarray(
                    pipe.predict_proba(altered),
                    dtype=float,
                )
                means = probabilities.mean(axis=0)
                class_probs = {
                    str(label): round(float(prob), 8)
                    for label, prob in zip(classes, means)
                }
                if target_class in classes:
                    class_index = classes.index(target_class)
                else:
                    class_index = int(np.argmax(means))
                response = float(means[class_index])
                point = {
                    "value": _scalar(value),
                    "response": round(response, 8),
                    "class_probabilities": class_probs,
                }
            else:
                predictions = np.asarray(
                    pipe.predict(altered),
                    dtype=float,
                )
                point = {
                    "value": _scalar(value),
                    "response": round(
                        float(np.mean(predictions)),
                        8,
                    ),
                }
            points.append(point)

        curves.append(
            {
                "feature": feature,
                "kind": kind,
                "target_class": (
                    _scalar(target_class)
                    if target_class is not None
                    else None
                ),
                "points": points,
            }
        )

    return {
        "model_id": model_id,
        "task": task,
        "evaluation_source": source,
        "rows_sampled": len(sample),
        "curves": curves,
        "method": (
            "manual partial dependence via repeated saved-model inference"
        ),
        "caveat": (
            "La dépendance partielle décrit la réponse moyenne du modèle "
            "lorsqu'une variable est modifiée. Elle ne constitue pas une "
            "preuve d'effet causal."
        ),
    }


def _transformed_feature_mapping(
    transformed_names: list[str],
    original_features: list[str],
) -> list[str]:
    ordered = sorted(
        original_features,
        key=len,
        reverse=True,
    )
    result: list[str] = []
    for transformed in transformed_names:
        token = transformed.split("__", 1)[-1]
        matched = None
        for feature in ordered:
            if (
                token == feature
                or token.startswith(feature + "_")
            ):
                matched = feature
                break
        result.append(matched or token)
    return result


def _aggregate_shap(
    values: np.ndarray,
    mapping: list[str],
    *,
    signed: bool,
) -> list[dict[str, Any]]:
    array = np.asarray(values, dtype=float)
    if array.ndim == 3:
        if signed:
            reduced = np.mean(array, axis=2)
        else:
            reduced = np.mean(np.abs(array), axis=(0, 2))
    elif array.ndim == 2:
        reduced = array if signed else np.mean(np.abs(array), axis=0)
    elif array.ndim == 1:
        reduced = array
    else:
        raise ValueError("Format SHAP non reconnu.")

    if signed and np.asarray(reduced).ndim == 2:
        reduced = np.asarray(reduced)[0]

    totals: dict[str, float] = {}
    for feature, value in zip(mapping, np.asarray(reduced).reshape(-1)):
        totals[feature] = totals.get(feature, 0.0) + float(value)

    rows = [
        {
            "feature": feature,
            "value": round(value, 8),
            "abs_value": round(abs(value), 8),
        }
        for feature, value in totals.items()
    ]
    rows.sort(
        key=lambda row: row["abs_value"],
        reverse=True,
    )
    return rows


def shap_explanation(
    model_id: str,
    df: pd.DataFrame,
    *,
    row: dict[str, Any] | None = None,
    max_rows: int = 80,
) -> dict[str, Any]:
    if importlib.util.find_spec("shap") is None:
        return {
            "model_id": model_id,
            "status": "unavailable",
            "reason": "La bibliothèque SHAP n'est pas installée.",
        }

    import shap

    payload = _payload(model_id)
    pipe = payload["pipeline"]
    features = list(payload["features"])
    X, _y, source = _evaluation_frame(payload, df)

    sample = X.sample(
        n=min(max(10, int(max_rows)), len(X), 80),
        random_state=42,
    ) if len(X) > min(max(10, int(max_rows)), 80) else X.copy()

    preprocess = pipe.named_steps.get("preprocess")
    estimator = pipe.named_steps.get("model")
    if preprocess is None or estimator is None:
        return {
            "model_id": model_id,
            "status": "unavailable",
            "reason": "Pipeline non compatible avec l'explication SHAP.",
        }

    try:
        transformed = preprocess.transform(sample)
        if hasattr(transformed, "toarray"):
            transformed = transformed.toarray()
        transformed = np.asarray(transformed)
        names = [
            str(x)
            for x in preprocess.get_feature_names_out()
        ]
        mapping = _transformed_feature_mapping(names, features)

        if transformed.shape[1] > 250:
            return {
                "model_id": model_id,
                "status": "unavailable",
                "reason": (
                    "Le pipeline génère plus de 250 variables transformées; "
                    "SHAP est désactivé pour éviter un calcul excessif."
                ),
                "transformed_features": int(transformed.shape[1]),
            }

        background = transformed[: min(30, len(transformed))]
        class_name = estimator.__class__.__name__.lower()
        tree_like = any(
            token in class_name
            for token in (
                "forest",
                "tree",
                "boost",
                "xgb",
                "lgbm",
                "catboost",
            )
        )

        method = "generic"
        try:
            if tree_like:
                explainer = shap.TreeExplainer(estimator)
                explanation = explainer(
                    transformed[: min(50, len(transformed))]
                )
                method = "TreeExplainer"
            else:
                model_fn = (
                    estimator.predict_proba
                    if payload["task"] == "classification"
                    and hasattr(estimator, "predict_proba")
                    else estimator.predict
                )
                explainer = shap.Explainer(
                    model_fn,
                    background,
                    algorithm="permutation",
                )
                max_evals = max(
                    2 * transformed.shape[1] + 1,
                    21,
                )
                explanation = explainer(
                    transformed[: min(30, len(transformed))],
                    max_evals=max_evals,
                )
                method = "PermutationExplainer"
        except Exception:
            model_fn = (
                estimator.predict_proba
                if payload["task"] == "classification"
                and hasattr(estimator, "predict_proba")
                else estimator.predict
            )
            explainer = shap.Explainer(
                model_fn,
                background,
                algorithm="permutation",
            )
            max_evals = max(
                2 * transformed.shape[1] + 1,
                21,
            )
            explanation = explainer(
                transformed[: min(20, len(transformed))],
                max_evals=max_evals,
            )
            method = "PermutationExplainer"

        values = np.asarray(explanation.values)
        global_rows = _aggregate_shap(
            values,
            mapping,
            signed=False,
        )

        local_rows = None
        prediction = None
        if row is not None:
            missing = [feature for feature in features if feature not in row]
            if missing:
                raise ValueError(
                    f"Variables manquantes pour SHAP local: {missing}"
                )
            frame = pd.DataFrame(
                [{feature: row[feature] for feature in features}]
            )
            transformed_row = preprocess.transform(frame)
            if hasattr(transformed_row, "toarray"):
                transformed_row = transformed_row.toarray()
            transformed_row = np.asarray(transformed_row)

            local_explanation_obj = explainer(transformed_row)
            local_values = np.asarray(
                local_explanation_obj.values
            )
            if local_values.ndim == 3:
                if (
                    payload["task"] == "classification"
                    and hasattr(estimator, "predict_proba")
                ):
                    probabilities = estimator.predict_proba(
                        transformed_row
                    )[0]
                    output_index = int(np.argmax(probabilities))
                    local_values = local_values[:, :, output_index]
                else:
                    local_values = np.mean(
                        local_values,
                        axis=2,
                    )

            local_rows = _aggregate_shap(
                local_values,
                mapping,
                signed=True,
            )
            prediction = _scalar(pipe.predict(frame)[0])

        return {
            "model_id": model_id,
            "status": "ok",
            "task": payload["task"],
            "algorithm": payload.get("algorithm"),
            "evaluation_source": source,
            "method": method,
            "rows_explained": int(
                min(len(sample), values.shape[0] if values.ndim else 0)
            ),
            "transformed_features": int(transformed.shape[1]),
            "global_importance": global_rows,
            "local": (
                {
                    "prediction": prediction,
                    "contributions": local_rows,
                }
                if local_rows is not None
                else None
            ),
            "caveat": (
                "Les valeurs SHAP expliquent la sortie du modèle; "
                "elles ne démontrent pas une relation causale."
            ),
        }
    except Exception as exc:
        return {
            "model_id": model_id,
            "status": "unavailable",
            "reason": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


def _candidate_values(
    series: pd.Series,
) -> list[Any]:
    if pd.api.types.is_numeric_dtype(series):
        clean = pd.to_numeric(
            series,
            errors="coerce",
        ).dropna()
        if clean.empty:
            return []
        values = np.unique(
            np.quantile(
                clean.to_numpy(dtype=float),
                [0.05, 0.25, 0.5, 0.75, 0.95],
            )
        ).tolist()
        return [_scalar(value) for value in values]

    return (
        series.dropna()
        .astype(object)
        .value_counts()
        .head(5)
        .index.tolist()
    )


def _row_distance(
    original: dict[str, Any],
    candidate: dict[str, Any],
    df: pd.DataFrame,
    changed: list[str],
) -> float:
    distance = float(len(changed))
    for feature in changed:
        if feature not in df.columns:
            continue
        series = df[feature]
        if pd.api.types.is_numeric_dtype(series):
            try:
                q1 = float(series.quantile(0.25))
                q3 = float(series.quantile(0.75))
                scale = max(abs(q3 - q1), 1e-9)
                distance += abs(
                    float(candidate[feature]) - float(original[feature])
                ) / scale
            except Exception:
                distance += 1.0
        else:
            distance += (
                0.0
                if candidate[feature] == original[feature]
                else 1.0
            )
    return float(distance)


def generate_counterfactuals(
    model_id: str,
    df: pd.DataFrame,
    row: dict[str, Any],
    *,
    desired_class: Any | None = None,
    desired_value: float | None = None,
    direction: str | None = None,
    max_changes: int = 2,
    max_results: int = 5,
) -> dict[str, Any]:
    payload = _payload(model_id)
    pipe = payload["pipeline"]
    features = list(payload["features"])
    missing = [feature for feature in features if feature not in row]
    if missing:
        raise ValueError(
            f"Variables manquantes dans l'observation: {missing}"
        )

    reference = df[features].copy()
    base_frame = pd.DataFrame(
        [{feature: row[feature] for feature in features}]
    )
    base_prediction = _scalar(pipe.predict(base_frame)[0])
    task = payload["task"]

    classes: list[Any] = []
    base_probabilities = None
    target_class = desired_class

    if task == "classification":
        if not hasattr(pipe, "predict_proba"):
            raise ValueError(
                "Le modèle de classification ne fournit pas de probabilités."
            )
        classes = [_scalar(value) for value in pipe.classes_]
        base_probabilities = np.asarray(
            pipe.predict_proba(base_frame)[0],
            dtype=float,
        )
        if target_class is None:
            if len(classes) == 2:
                target_class = (
                    classes[1]
                    if base_prediction == classes[0]
                    else classes[0]
                )
            else:
                order = np.argsort(base_probabilities)[::-1]
                target_class = classes[
                    int(order[1] if len(order) > 1 else order[0])
                ]
        if target_class not in classes:
            raise ValueError(
                f"Classe cible inconnue: {target_class}"
            )
        target_index = classes.index(target_class)
        base_objective = float(
            base_probabilities[target_index]
        )
    else:
        if desired_value is None and direction not in {
            "increase",
            "decrease",
        }:
            raise ValueError(
                "Pour une régression, fournissez desired_value ou "
                "direction='increase'/'decrease'."
            )
        base_numeric = float(base_prediction)
        base_objective = (
            -abs(base_numeric - float(desired_value))
            if desired_value is not None
            else base_numeric
            if direction == "increase"
            else -base_numeric
        )

    importance_rows = (
        payload.get("model_card", {}).get("feature_importance", [])
    )
    ordered_features = [
        item["feature"]
        for item in importance_rows
        if item.get("feature") in features
    ]
    ordered_features += [
        feature
        for feature in features
        if feature not in ordered_features
    ]
    ordered_features = ordered_features[:10]

    values_by_feature = {
        feature: [
            value
            for value in _candidate_values(reference[feature])
            if str(value) != str(row.get(feature))
        ][:5]
        for feature in ordered_features
    }

    candidate_rows: list[tuple[dict[str, Any], list[str]]] = []
    for feature in ordered_features:
        for value in values_by_feature[feature]:
            candidate = dict(row)
            candidate[feature] = value
            candidate_rows.append((candidate, [feature]))

    if max_changes >= 2:
        for left, right in itertools.combinations(
            ordered_features[:6],
            2,
        ):
            for left_value in values_by_feature[left][:3]:
                for right_value in values_by_feature[right][:3]:
                    candidate = dict(row)
                    candidate[left] = left_value
                    candidate[right] = right_value
                    candidate_rows.append(
                        (candidate, [left, right])
                    )

    if not candidate_rows:
        return {
            "model_id": model_id,
            "status": "no_candidates",
            "counterfactuals": [],
        }

    frame = pd.DataFrame(
        [
            {feature: candidate[feature] for feature in features}
            for candidate, _changed in candidate_rows
        ]
    )
    predictions = pipe.predict(frame)

    probabilities = None
    if task == "classification":
        probabilities = np.asarray(
            pipe.predict_proba(frame),
            dtype=float,
        )

    ranked: list[dict[str, Any]] = []
    for index, ((candidate, changed), prediction) in enumerate(
        zip(candidate_rows, predictions)
    ):
        pred_value = _scalar(prediction)
        reached = False

        if task == "classification":
            assert probabilities is not None
            objective = float(
                probabilities[index][target_index]
            )
            reached = pred_value == target_class
            improvement = objective - base_objective
            output = {
                "prediction": pred_value,
                "target_probability": round(objective, 8),
                "probabilities": [
                    round(float(value), 8)
                    for value in probabilities[index]
                ],
            }
        else:
            pred_numeric = float(pred_value)
            if desired_value is not None:
                objective = -abs(
                    pred_numeric - float(desired_value)
                )
                reached = abs(
                    pred_numeric - float(desired_value)
                ) <= max(
                    abs(float(desired_value)) * 0.02,
                    1e-6,
                )
            elif direction == "increase":
                objective = pred_numeric
                reached = pred_numeric > float(base_prediction)
            else:
                objective = -pred_numeric
                reached = pred_numeric < float(base_prediction)

            improvement = objective - base_objective
            output = {
                "prediction": round(pred_numeric, 8),
            }

        if improvement <= 0 and not reached:
            continue

        changes = {
            feature: {
                "from": _scalar(row[feature]),
                "to": _scalar(candidate[feature]),
            }
            for feature in changed
        }
        ranked.append(
            {
                "reached": reached,
                "objective_improvement": round(
                    float(improvement), 8
                ),
                "distance": round(
                    _row_distance(
                        row,
                        candidate,
                        reference,
                        changed,
                    ),
                    8,
                ),
                "changes": changes,
                **output,
            }
        )

    ranked.sort(
        key=lambda item: (
            not item["reached"],
            -item["objective_improvement"],
            item["distance"],
            len(item["changes"]),
        )
    )

    return {
        "model_id": model_id,
        "task": task,
        "base_prediction": base_prediction,
        "base_probabilities": (
            [
                round(float(value), 8)
                for value in base_probabilities
            ]
            if base_probabilities is not None
            else None
        ),
        "desired_class": _scalar(target_class)
        if target_class is not None
        else None,
        "desired_value": desired_value,
        "direction": direction,
        "counterfactuals": ranked[: max(1, min(max_results, 10))],
        "searched_candidates": len(candidate_rows),
        "method": "bounded deterministic candidate search",
        "caveat": (
            "Ces contre-factuels décrivent des modifications susceptibles "
            "de changer la sortie du modèle. Ils ne prouvent pas qu'une "
            "intervention réelle produirait le même effet."
        ),
    }
