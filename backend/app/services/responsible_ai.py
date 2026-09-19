from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

from app.core.config import get_settings


MISSING_GROUP = "__MISSING__"
MAX_PROTECTED_COLUMNS = 3
MAX_GROUPS_PER_VIEW = 40


@dataclass(frozen=True)
class EvaluationSlice:
    frame: pd.DataFrame
    source: str


def _payload(model_id: str) -> dict[str, Any]:
    path = get_settings().model_dir / f"{model_id}.joblib"
    if not path.exists():
        raise FileNotFoundError(model_id)
    payload = joblib.load(path)
    if not isinstance(payload, dict) or "pipeline" not in payload:
        raise ValueError("Artefact modèle invalide.")
    return payload


def _card_path(model_id: str) -> Path:
    return get_settings().model_dir / f"{model_id}.card.json"


def _scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return _scalar(value)


def _evaluation_slice(
    payload: dict[str, Any],
    df: pd.DataFrame,
    *,
    scope: str = "holdout",
) -> EvaluationSlice:
    target = payload.get("target")
    features = list(payload.get("features") or [])
    if not target or target not in df.columns:
        raise ValueError("La cible du modèle est absente du dataset d'évaluation.")
    missing_features = [feature for feature in features if feature not in df.columns]
    if missing_features:
        raise ValueError(
            "Variables du modèle absentes du dataset: " + ", ".join(missing_features[:20])
        )

    work = df.dropna(subset=[target]).copy()
    if scope == "holdout":
        indices = payload.get("evaluation_indices") or []
        if indices:
            try:
                subset = work.loc[work.index.intersection(indices)]
                if len(subset) >= 5:
                    work = subset
                    return EvaluationSlice(work, "final_test_holdout")
            except Exception:
                pass
        return EvaluationSlice(work, "reference_dataset_fallback")
    if scope == "all_labeled":
        return EvaluationSlice(work, "all_labeled_rows")
    raise ValueError("scope doit être holdout ou all_labeled.")


def _validate_protected_columns(
    df: pd.DataFrame,
    protected_columns: Iterable[str],
) -> list[str]:
    columns: list[str] = []
    for raw in protected_columns:
        column = str(raw).strip()
        if column and column not in columns:
            columns.append(column)
    if not columns:
        raise ValueError(
            "Sélectionnez au moins une variable de groupe à auditer. "
            "DataVision ne devine pas automatiquement les caractéristiques sensibles."
        )
    if len(columns) > MAX_PROTECTED_COLUMNS:
        raise ValueError(
            f"Maximum {MAX_PROTECTED_COLUMNS} variables de groupe par audit."
        )
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(
            "Variables de groupe absentes du dataset: " + ", ".join(missing)
        )
    return columns


def _normalise_group_value(value: Any) -> str:
    if pd.isna(value):
        return MISSING_GROUP
    return str(_scalar(value))


def _group_specs(
    protected_columns: list[str],
    mode: str,
) -> list[tuple[str, ...]]:
    if mode not in {"separate", "intersectional", "both"}:
        raise ValueError("mode doit être separate, intersectional ou both.")
    specs: list[tuple[str, ...]] = []
    if mode in {"separate", "both"}:
        specs.extend((column,) for column in protected_columns)
    if mode in {"intersectional", "both"} and len(protected_columns) > 1:
        specs.append(tuple(protected_columns))
    return specs


def _safe_ratio(low: float | None, high: float | None) -> float | None:
    if low is None or high is None or not math.isfinite(low) or not math.isfinite(high):
        return None
    if abs(high) <= 1e-12:
        return None
    return low / high


def _metric_range(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    values = [
        (row["group"], float(row[key]))
        for row in rows
        if row.get(key) is not None and math.isfinite(float(row[key]))
    ]
    if len(values) < 2:
        return None
    low_group, low = min(values, key=lambda item: item[1])
    high_group, high = max(values, key=lambda item: item[1])
    return {
        "metric": key,
        "min": round(low, 8),
        "min_group": low_group,
        "max": round(high, 8),
        "max_group": high_group,
        "difference": round(high - low, 8),
        "ratio": (
            None
            if _safe_ratio(low, high) is None
            else round(float(_safe_ratio(low, high)), 8)
        ),
    }


def _classification_metrics(
    y_true: pd.Series,
    y_pred: np.ndarray,
    *,
    positive_label: Any | None,
    positive_probability: np.ndarray | None,
) -> dict[str, Any]:
    true = np.asarray(y_true)
    pred = np.asarray(y_pred)
    unique_true = np.unique(true)
    result: dict[str, Any] = {
        "accuracy": round(float(accuracy_score(true, pred)), 8),
        "balanced_accuracy": (
            round(float(balanced_accuracy_score(true, pred)), 8)
            if len(unique_true) >= 2
            else None
        ),
        "f1_weighted": round(
            float(f1_score(true, pred, average="weighted", zero_division=0)), 8
        ),
    }
    if positive_label is None:
        return result

    true_pos = true == positive_label
    pred_pos = pred == positive_label
    tp = int(np.sum(true_pos & pred_pos))
    fp = int(np.sum(~true_pos & pred_pos))
    fn = int(np.sum(true_pos & ~pred_pos))
    tn = int(np.sum(~true_pos & ~pred_pos))
    positive_support = tp + fn
    negative_support = tn + fp

    result.update(
        {
            "positive_label": _jsonable(positive_label),
            "base_rate": round(float(np.mean(true_pos)), 8),
            "selection_rate": round(float(np.mean(pred_pos)), 8),
            "true_positive_rate": (
                None if positive_support == 0 else round(tp / positive_support, 8)
            ),
            "false_positive_rate": (
                None if negative_support == 0 else round(fp / negative_support, 8)
            ),
            "precision_positive": (
                None if tp + fp == 0 else round(tp / (tp + fp), 8)
            ),
            "recall_positive": (
                None if positive_support == 0 else round(tp / positive_support, 8)
            ),
            "f1_positive": round(
                float(
                    f1_score(
                        true_pos.astype(int),
                        pred_pos.astype(int),
                        zero_division=0,
                    )
                ),
                8,
            ),
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        }
    )
    if positive_probability is not None and len(positive_probability) == len(true):
        probs = np.asarray(positive_probability, dtype=float)
        y_binary = true_pos.astype(float)
        brier = float(np.mean((probs - y_binary) ** 2))
        result.update(
            {
                "mean_positive_probability": round(float(np.mean(probs)), 8),
                "brier_score": round(brier, 8),
                "calibration_gap": round(
                    float(np.mean(probs) - np.mean(y_binary)), 8
                ),
            }
        )
    return result


def _regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, Any]:
    observed = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    residual = predicted - observed
    result = {
        "mae": round(float(mean_absolute_error(observed, predicted)), 8),
        "rmse": round(float(mean_squared_error(observed, predicted) ** 0.5), 8),
        "mean_error": round(float(np.mean(residual)), 8),
        "mean_absolute_error": round(float(np.mean(np.abs(residual))), 8),
    }
    if len(observed) >= 2 and np.unique(observed).size >= 2:
        result["r2"] = round(float(r2_score(observed, predicted)), 8)
    else:
        result["r2"] = None
    return result


def _group_report(
    payload: dict[str, Any],
    frame: pd.DataFrame,
    protected_columns: list[str],
    *,
    mode: str,
    min_group_size: int,
    positive_label: Any | None,
    max_groups: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    pipeline = payload["pipeline"]
    target = payload["target"]
    features = list(payload["features"])
    task = payload["task"]
    X = frame[features]
    y = frame[target]
    predictions = np.asarray(pipeline.predict(X))

    classes = [_scalar(value) for value in getattr(pipeline, "classes_", [])]
    resolved_positive = positive_label
    if task == "classification":
        if resolved_positive is None and len(classes) == 2:
            resolved_positive = classes[-1]
        if resolved_positive is not None and resolved_positive not in classes:
            # Accept string representation from JSON/UI when underlying labels are numeric/bool.
            by_text = {str(value): value for value in classes}
            by_fold = {str(value).casefold(): value for value in classes}
            if str(resolved_positive) in by_text:
                resolved_positive = by_text[str(resolved_positive)]
            elif str(resolved_positive).casefold() in by_fold:
                resolved_positive = by_fold[str(resolved_positive).casefold()]
            else:
                raise ValueError(
                    f"Classe positive inconnue: {resolved_positive}. Classes: {classes}"
                )

    probability = None
    if (
        task == "classification"
        and resolved_positive is not None
        and hasattr(pipeline, "predict_proba")
        and resolved_positive in classes
    ):
        class_index = classes.index(resolved_positive)
        probability = np.asarray(pipeline.predict_proba(X)[:, class_index], dtype=float)

    working = frame.copy()
    working["__dv_prediction__"] = predictions
    if probability is not None:
        working["__dv_positive_probability__"] = probability

    reports: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    specs = _group_specs(protected_columns, mode)

    for spec in specs:
        view_name = " × ".join(spec)
        group_keys = working[list(spec)].copy()
        for column in spec:
            group_keys[column] = group_keys[column].map(_normalise_group_value)
        if len(spec) == 1:
            keys = group_keys[spec[0]].astype(str)
        else:
            keys = group_keys.apply(
                lambda row: " | ".join(f"{col}={row[col]}" for col in spec), axis=1
            )
        counts = keys.value_counts(dropna=False)
        if len(counts) > max_groups:
            keep = set(counts.head(max_groups).index.astype(str))
        else:
            keep = set(counts.index.astype(str))

        rows: list[dict[str, Any]] = []
        for group_name, count in counts.items():
            group_name = str(group_name)
            if group_name not in keep:
                excluded.append(
                    {
                        "view": view_name,
                        "group": group_name,
                        "support": int(count),
                        "reason": "group_limit",
                    }
                )
                continue
            mask = keys.astype(str) == group_name
            support = int(mask.sum())
            if support < min_group_size:
                excluded.append(
                    {
                        "view": view_name,
                        "group": group_name,
                        "support": support,
                        "reason": "below_min_group_size",
                    }
                )
                continue

            part = working.loc[mask]
            y_true = part[target]
            y_pred = np.asarray(part["__dv_prediction__"])
            if task == "classification":
                probs = (
                    np.asarray(part["__dv_positive_probability__"], dtype=float)
                    if "__dv_positive_probability__" in part
                    else None
                )
                metrics = _classification_metrics(
                    y_true,
                    y_pred,
                    positive_label=resolved_positive,
                    positive_probability=probs,
                )
            else:
                metrics = _regression_metrics(y_true, y_pred)

            rows.append(
                {
                    "group": group_name,
                    "support": support,
                    "share": round(support / max(len(working), 1), 8),
                    **metrics,
                }
            )

        if task == "classification":
            metric_keys = [
                "accuracy",
                "balanced_accuracy",
                "selection_rate",
                "true_positive_rate",
                "false_positive_rate",
                "precision_positive",
                "brier_score",
                "calibration_gap",
            ]
        else:
            metric_keys = ["mae", "rmse", "mean_error", "r2"]

        ranges = {
            key: value
            for key in metric_keys
            if (value := _metric_range(rows, key)) is not None
        }
        parity: dict[str, Any] = {}
        if task == "classification" and resolved_positive is not None:
            selection = ranges.get("selection_rate")
            tpr = ranges.get("true_positive_rate")
            fpr = ranges.get("false_positive_rate")
            parity = {
                "demographic_parity_difference": (
                    selection.get("difference") if selection else None
                ),
                "selection_rate_ratio": (
                    selection.get("ratio") if selection else None
                ),
                "equal_opportunity_difference": (
                    tpr.get("difference") if tpr else None
                ),
                "false_positive_rate_difference": (
                    fpr.get("difference") if fpr else None
                ),
                "equalized_odds_difference": (
                    max(
                        [
                            value
                            for value in [
                                tpr.get("difference") if tpr else None,
                                fpr.get("difference") if fpr else None,
                            ]
                            if value is not None
                        ],
                        default=None,
                    )
                ),
            }
        elif task == "regression":
            mae = ranges.get("mae")
            rmse = ranges.get("rmse")
            parity = {
                "mae_difference": mae.get("difference") if mae else None,
                "mae_ratio": (
                    None
                    if not mae or abs(float(mae.get("min", 0.0))) <= 1e-12
                    else round(float(mae["max"]) / float(mae["min"]), 8)
                ),
                "rmse_difference": rmse.get("difference") if rmse else None,
                "rmse_ratio": (
                    None
                    if not rmse or abs(float(rmse.get("min", 0.0))) <= 1e-12
                    else round(float(rmse["max"]) / float(rmse["min"]), 8)
                ),
            }

        reports.append(
            {
                "view": view_name,
                "columns": list(spec),
                "groups": rows,
                "disparity_ranges": ranges,
                "parity_metrics": parity,
            }
        )

    meta = {
        "classes": classes,
        "positive_label": _jsonable(resolved_positive),
    }
    return reports, excluded, meta


def fairness_report(
    model_id: str,
    df: pd.DataFrame,
    *,
    protected_columns: list[str],
    positive_label: Any | None = None,
    mode: str = "both",
    min_group_size: int = 20,
    max_groups: int = MAX_GROUPS_PER_VIEW,
    scope: str = "holdout",
) -> dict[str, Any]:
    payload = _payload(model_id)
    slice_ = _evaluation_slice(payload, df, scope=scope)
    columns = _validate_protected_columns(slice_.frame, protected_columns)
    min_group_size = max(2, min(int(min_group_size), 100000))
    max_groups = max(2, min(int(max_groups), MAX_GROUPS_PER_VIEW))

    reports, excluded, meta = _group_report(
        payload,
        slice_.frame,
        columns,
        mode=mode,
        min_group_size=min_group_size,
        positive_label=positive_label,
        max_groups=max_groups,
    )

    protected_feature_usage = [
        column for column in columns if column in set(payload.get("features") or [])
    ]
    missing_count = {
        column: int(slice_.frame[column].isna().sum()) for column in columns
    }
    warnings: list[dict[str, Any]] = []
    if protected_feature_usage:
        warnings.append(
            {
                "code": "protected_attribute_used_as_feature",
                "severity": "high",
                "columns": protected_feature_usage,
                "message": (
                    "Au moins une variable sélectionnée pour l'audit de groupe est "
                    "également utilisée comme feature du modèle. Une revue humaine et "
                    "métier est requise avant publication."
                ),
            }
        )
    if excluded:
        warnings.append(
            {
                "code": "small_or_excess_groups_excluded",
                "severity": "medium",
                "count": len(excluded),
                "message": (
                    "Certains groupes ne sont pas comparés parce que leur effectif est "
                    "trop faible ou que la cardinalité dépasse la limite d'affichage."
                ),
            }
        )
    if any(value > 0 for value in missing_count.values()):
        warnings.append(
            {
                "code": "missing_group_values",
                "severity": "low",
                "counts": missing_count,
                "message": "Des valeurs de groupe manquantes sont auditées sous __MISSING__.",
            }
        )
    if payload.get("task") == "classification" and meta.get("positive_label") is None:
        warnings.append(
            {
                "code": "positive_label_not_resolved",
                "severity": "medium",
                "message": (
                    "Les métriques de parité binaire ne sont pas calculées tant qu'une "
                    "classe positive n'est pas définie."
                ),
            }
        )

    return {
        "model_id": model_id,
        "task": payload.get("task"),
        "algorithm": payload.get("algorithm"),
        "target": payload.get("target"),
        "evaluation_source": slice_.source,
        "rows_evaluated": len(slice_.frame),
        "protected_columns": columns,
        "protected_feature_usage": protected_feature_usage,
        "mode": mode,
        "min_group_size": min_group_size,
        "classes": meta.get("classes") or [],
        "positive_label": meta.get("positive_label"),
        "reports": reports,
        "excluded_groups": excluded,
        "warnings": warnings,
        "interpretation_policy": (
            "group_metrics_are_diagnostics_not_a_universal_fairness_verdict"
        ),
        "threshold_policy": (
            "No universal fairness threshold is applied by this report. "
            "Blocking thresholds belong to the organization's publication policy."
        ),
        "selection_policy": (
            "Protected/group columns are explicitly selected by the user; DataVision "
            "does not infer sensitive attributes from column names."
        ),
    }


def _find_report_metric(
    report: dict[str, Any],
    metric: str,
) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for view in report.get("reports") or []:
        value = (view.get("parity_metrics") or {}).get(metric)
        if value is not None and math.isfinite(float(value)):
            values.append((str(view.get("view")), float(value)))
    return values


def responsible_ai_gate(
    model_id: str,
    df: pd.DataFrame,
    *,
    protected_columns: list[str],
    positive_label: Any | None = None,
    mode: str = "both",
    min_group_size: int = 20,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = dict(policy or {})
    report = fairness_report(
        model_id,
        df,
        protected_columns=protected_columns,
        positive_label=positive_label,
        mode=mode,
        min_group_size=min_group_size,
    )
    blockers: list[dict[str, Any]] = []
    warnings = list(report.get("warnings") or [])

    comparable_views = [
        view for view in (report.get("reports") or [])
        if len(view.get("groups") or []) >= 2
    ]
    if not comparable_views:
        blockers.append(
            {
                "code": "no_comparable_groups",
                "message": (
                    "Aucune vue ne contient au moins deux groupes avec un effectif "
                    "suffisant pour appliquer un publication gate Responsible AI."
                ),
            }
        )
    elif len(comparable_views) < len(report.get("reports") or []):
        warnings.append(
            {
                "code": "partially_comparable_group_views",
                "severity": "medium",
                "message": (
                    "Certaines vues de groupe ne contiennent pas deux groupes "
                    "suffisamment documentés et ne participent pas au gate."
                ),
            }
        )

    if policy.get("block_on_protected_feature_usage") and report.get(
        "protected_feature_usage"
    ):
        blockers.append(
            {
                "code": "protected_feature_usage",
                "columns": report["protected_feature_usage"],
                "message": (
                    "La politique de publication interdit l'utilisation des variables "
                    "d'audit sélectionnées comme features du modèle."
                ),
            }
        )

    upper_limits = {
        "demographic_parity_difference": "max_demographic_parity_difference",
        "equal_opportunity_difference": "max_equal_opportunity_difference",
        "false_positive_rate_difference": "max_false_positive_rate_difference",
        "equalized_odds_difference": "max_equalized_odds_difference",
        "mae_difference": "max_mae_difference",
        "rmse_difference": "max_rmse_difference",
        "mae_ratio": "max_mae_ratio",
        "rmse_ratio": "max_rmse_ratio",
    }
    lower_limits = {
        "selection_rate_ratio": "min_selection_rate_ratio",
    }

    checks: list[dict[str, Any]] = []
    for metric, policy_key in upper_limits.items():
        threshold = policy.get(policy_key)
        if threshold is None:
            continue
        for view, value in _find_report_metric(report, metric):
            passed = value <= float(threshold)
            check = {
                "metric": metric,
                "view": view,
                "operator": "<=",
                "threshold": float(threshold),
                "value": round(value, 8),
                "passed": passed,
            }
            checks.append(check)
            if not passed:
                blockers.append(
                    {
                        "code": f"threshold_failed:{metric}",
                        **check,
                    }
                )

    for metric, policy_key in lower_limits.items():
        threshold = policy.get(policy_key)
        if threshold is None:
            continue
        for view, value in _find_report_metric(report, metric):
            passed = value >= float(threshold)
            check = {
                "metric": metric,
                "view": view,
                "operator": ">=",
                "threshold": float(threshold),
                "value": round(value, 8),
                "passed": passed,
            }
            checks.append(check)
            if not passed:
                blockers.append(
                    {
                        "code": f"threshold_failed:{metric}",
                        **check,
                    }
                )

    return {
        "model_id": model_id,
        "allowed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "fairness": report,
        "policy": policy,
        "policy_source": "organization_defined_thresholds",
        "policy_note": (
            "DataVision does not treat any single statistical fairness criterion as "
            "universally correct. Publication thresholds must be chosen for the model's "
            "legal, operational and domain context."
        ),
    }


def model_risk_assessment(
    model_id: str,
    *,
    fairness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _payload(model_id)
    card = payload.get("model_card") or {}
    factors: list[dict[str, Any]] = []

    test_rows = int((card.get("rows") or {}).get("test") or 0)
    if test_rows and test_rows < 30:
        factors.append(
            {
                "code": "small_final_test",
                "severity": "high",
                "message": f"Jeu de test final limité ({test_rows} lignes).",
            }
        )
    elif test_rows and test_rows < 100:
        factors.append(
            {
                "code": "limited_final_test",
                "severity": "medium",
                "message": f"Jeu de test final relativement limité ({test_rows} lignes).",
            }
        )

    for guardrail in card.get("guardrails") or []:
        severity = str(guardrail.get("severity") or "info")
        if severity in {"high", "medium"}:
            factors.append(
                {
                    "code": f"training_guardrail:{guardrail.get('code')}",
                    "severity": severity,
                    "message": guardrail.get("message"),
                }
            )

    if fairness is not None:
        if fairness.get("protected_feature_usage"):
            factors.append(
                {
                    "code": "protected_feature_usage",
                    "severity": "high",
                    "columns": fairness["protected_feature_usage"],
                    "message": "Une variable de groupe auditée est utilisée comme feature.",
                }
            )
        if fairness.get("excluded_groups"):
            factors.append(
                {
                    "code": "insufficient_group_support",
                    "severity": "medium",
                    "message": (
                        "Certains groupes n'ont pas un effectif suffisant pour une comparaison fiable."
                    ),
                }
            )
    else:
        factors.append(
            {
                "code": "fairness_not_reviewed",
                "severity": "medium",
                "message": (
                    "Aucun audit de performance par groupe n'a été fourni à cette évaluation."
                ),
            }
        )

    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    max_score = max((order.get(str(item.get("severity")), 0) for item in factors), default=0)
    risk_level = {0: "low", 1: "low", 2: "medium", 3: "high", 4: "critical"}[max_score]

    return {
        "model_id": model_id,
        "task": payload.get("task"),
        "algorithm": payload.get("algorithm"),
        "risk_level": risk_level,
        "review_required": bool(factors),
        "factors": factors,
        "interpretation": (
            "This is a model-governance risk assessment, not a judgment about any "
            "person or protected group. Human/domain review remains authoritative."
        ),
    }


def _representation_table(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    min_group_size: int,
) -> list[dict[str, Any]]:
    if len(columns) == 1:
        keys = frame[columns[0]].map(_normalise_group_value)
    else:
        parts = frame[columns].copy()
        for column in columns:
            parts[column] = parts[column].map(_normalise_group_value)
        keys = parts.apply(
            lambda row: " | ".join(f"{col}={row[col]}" for col in columns), axis=1
        )
    counts = keys.value_counts(dropna=False)
    total = max(len(frame), 1)
    return [
        {
            "group": str(group),
            "support": int(count),
            "share": round(int(count) / total, 8),
        }
        for group, count in counts.items()
        if int(count) >= min_group_size
    ][:MAX_GROUPS_PER_VIEW]


def population_drift(
    model_id: str,
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    *,
    protected_columns: list[str],
    positive_label: Any | None = None,
    mode: str = "both",
    min_group_size: int = 20,
) -> dict[str, Any]:
    payload = _payload(model_id)
    columns = _validate_protected_columns(reference_df, protected_columns)
    _validate_protected_columns(current_df, columns)
    views = _group_specs(columns, mode)

    representation: list[dict[str, Any]] = []
    for spec in views:
        ref_rows = _representation_table(
            reference_df, list(spec), min_group_size=min_group_size
        )
        cur_rows = _representation_table(
            current_df, list(spec), min_group_size=min_group_size
        )
        ref_map = {row["group"]: row for row in ref_rows}
        cur_map = {row["group"]: row for row in cur_rows}
        groups = sorted(set(ref_map) | set(cur_map))
        rows = []
        for group in groups:
            ref = ref_map.get(group, {"support": 0, "share": 0.0})
            cur = cur_map.get(group, {"support": 0, "share": 0.0})
            rows.append(
                {
                    "group": group,
                    "reference_support": ref["support"],
                    "current_support": cur["support"],
                    "reference_share": ref["share"],
                    "current_share": cur["share"],
                    "share_delta": round(cur["share"] - ref["share"], 8),
                }
            )
        representation.append(
            {
                "view": " × ".join(spec),
                "columns": list(spec),
                "groups": rows,
                "max_absolute_share_shift": round(
                    max((abs(row["share_delta"]) for row in rows), default=0.0), 8
                ),
            }
        )

    reference_performance = fairness_report(
        model_id,
        reference_df,
        protected_columns=columns,
        positive_label=positive_label,
        mode=mode,
        min_group_size=min_group_size,
        scope="holdout",
    )

    current_performance = None
    target = payload.get("target")
    if target in current_df.columns and current_df[target].notna().sum() >= min_group_size:
        current_performance = fairness_report(
            model_id,
            current_df,
            protected_columns=columns,
            positive_label=positive_label,
            mode=mode,
            min_group_size=min_group_size,
            scope="all_labeled",
        )

    return {
        "model_id": model_id,
        "protected_columns": columns,
        "representation_drift": representation,
        "reference_performance": reference_performance,
        "current_performance": current_performance,
        "labels_available_in_current": current_performance is not None,
        "interpretation_policy": (
            "population_and_performance_drift_are_monitoring_signals_not_causal_claims"
        ),
    }


def persist_responsible_ai_summary(
    model_id: str,
    *,
    fairness: dict[str, Any] | None = None,
    gate: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _payload(model_id)
    card = dict(payload.get("model_card") or {})
    if not card:
        raise ValueError("Model Card absente de l'artefact.")

    summary = dict(card.get("responsible_ai") or {})
    if fairness is not None:
        summary["fairness"] = {
            "status": "evaluated",
            "protected_columns": fairness.get("protected_columns") or [],
            "evaluation_source": fairness.get("evaluation_source"),
            "rows_evaluated": fairness.get("rows_evaluated"),
            "positive_label": fairness.get("positive_label"),
            "warnings": fairness.get("warnings") or [],
        }
    if gate is not None:
        summary["publication_gate"] = {
            "allowed": bool(gate.get("allowed")),
            "blockers": gate.get("blockers") or [],
            "checks": gate.get("checks") or [],
            "policy": gate.get("policy") or {},
        }
    if risk is not None:
        summary["risk"] = risk

    card["responsible_ai"] = _jsonable(summary)
    card["fairness"] = card["responsible_ai"].get(
        "fairness", {"status": "not_evaluated"}
    )
    payload["model_card"] = card

    root = get_settings().model_dir
    joblib.dump(payload, root / f"{model_id}.joblib")
    _card_path(model_id).write_text(
        json.dumps(card, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return card
