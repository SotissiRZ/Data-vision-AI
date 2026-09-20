from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import numpy as np
import pandas as pd

CLASSIFICATION_METRICS = {"accuracy", "balanced_accuracy", "f1_weighted", "roc_auc"}
REGRESSION_METRICS = {"rmse", "mae", "r2"}

_ID_PATTERN = re.compile(r"(^id$|_id$|^id_|uuid|identifier|identifiant|numero|number|key$)", re.I)
_TIME_PATTERN = re.compile(r"date|time|timestamp|datetime|annee|year|mois|month", re.I)


def _finding(code: str, severity: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    payload.update(extra)
    return payload


def _normalized_equal_ratio(a: pd.Series, b: pd.Series) -> float:
    pair = pd.concat([a, b], axis=1).dropna()
    if len(pair) < 10:
        return 0.0
    left = pair.iloc[:, 0]
    right = pair.iloc[:, 1]
    if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
        lv = pd.to_numeric(left, errors="coerce")
        rv = pd.to_numeric(right, errors="coerce")
        valid = lv.notna() & rv.notna()
        if int(valid.sum()) < 10:
            return 0.0
        return float(np.isclose(lv[valid].to_numpy(), rv[valid].to_numpy(), rtol=1e-9, atol=1e-12).mean())
    ls = left.astype(str).str.strip().str.casefold()
    rs = right.astype(str).str.strip().str.casefold()
    return float((ls == rs).mean())


def _numeric_corr(a: pd.Series, b: pd.Series) -> float | None:
    if not (pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)):
        return None
    pair = pd.concat([a, b], axis=1).dropna()
    if len(pair) < 10 or pair.iloc[:, 0].nunique() <= 1 or pair.iloc[:, 1].nunique() <= 1:
        return None
    value = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    return value if np.isfinite(value) else None


def _deterministic_proxy(a: pd.Series, target: pd.Series) -> bool:
    pair = pd.concat([a.rename("x"), target.rename("y")], axis=1).dropna()
    if len(pair) < 20:
        return False
    cardinality = int(pair["x"].nunique())
    if cardinality < 2 or cardinality > min(100, max(20, int(len(pair) * 0.25))):
        return False
    mapping = pair.groupby("x", dropna=False)["y"].nunique(dropna=True)
    return bool(len(mapping) and int(mapping.max()) <= 1)


def _parse_temporal(series: pd.Series) -> tuple[pd.Series | None, float]:
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        return parsed, float(parsed.notna().mean())
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    ratio = float(parsed.notna().mean())
    return (parsed if ratio >= 0.9 else None), ratio


def detect_time_columns(frame: pd.DataFrame) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for col in frame.columns:
        series = frame[col]
        name_match = bool(_TIME_PATTERN.search(str(col)))
        parsed, ratio = _parse_temporal(series) if name_match or pd.api.types.is_datetime64_any_dtype(series) else (None, 0.0)
        if parsed is not None and int(parsed.nunique(dropna=True)) >= 4:
            found.append({
                "column": str(col),
                "parse_ratio": round(ratio, 6),
                "unique": int(parsed.nunique(dropna=True)),
            })
    found.sort(key=lambda item: (item["parse_ratio"], item["unique"]), reverse=True)
    return found


def govern_metric(task: str, y: pd.Series, requested: str) -> dict[str, Any]:
    requested = requested or "auto"
    if task == "classification":
        counts = y.value_counts(dropna=True)
        classes = int(len(counts))
        ratio = float(counts.min() / counts.max()) if classes >= 2 and counts.max() else 1.0
        if requested not in CLASSIFICATION_METRICS and requested != "auto":
            requested = "auto"
        overridden = False
        reason = ""
        if requested == "auto":
            if ratio < 0.5:
                effective = "balanced_accuracy"
                reason = "Déséquilibre détecté : balanced_accuracy est plus robuste que l'accuracy brute."
            else:
                effective = "roc_auc" if classes == 2 else "f1_weighted"
                reason = "Métrique AutoML adaptée au nombre de classes."
        elif requested == "accuracy" and ratio < 0.5:
            effective = "balanced_accuracy"
            overridden = True
            reason = "Accuracy refusée comme métrique de sélection sur une cible déséquilibrée."
        elif requested == "roc_auc" and classes != 2:
            effective = "f1_weighted"
            overridden = True
            reason = "ROC-AUC binaire remplacée par F1 pondéré pour une cible multiclasses."
        else:
            effective = requested
            reason = "Métrique demandée compatible avec la cible."
        return {
            "requested": requested,
            "effective": effective,
            "overridden": overridden,
            "reason": reason,
            "class_imbalance_ratio": round(ratio, 6),
            "classes": classes,
        }
    requested = requested if requested in REGRESSION_METRICS else "auto"
    effective = "rmse" if requested == "auto" else requested
    return {"requested": requested, "effective": effective, "overridden": False, "reason": "Métrique compatible avec une tâche de régression."}


def _index_hash(values: pd.Index | list[Any]) -> str:
    payload = "\n".join(map(str, list(values))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_split_audit(train_index: pd.Index, validation_index: pd.Index, test_index: pd.Index, *, strategy: str, time_column: str | None) -> dict[str, Any]:
    train = set(map(str, train_index.tolist()))
    val = set(map(str, validation_index.tolist()))
    test = set(map(str, test_index.tolist()))
    disjoint = not (train & val or train & test or val & test)
    return {
        "strategy": strategy,
        "time_column": time_column,
        "rows": {"train": len(train_index), "validation": len(validation_index), "test": len(test_index)},
        "index_hashes": {
            "train": _index_hash(train_index),
            "validation": _index_hash(validation_index),
            "test": _index_hash(test_index),
        },
        "disjoint": disjoint,
        "final_test_isolated": True,
        "test_used_for_selection": False,
        "test_used_for_tuning": False,
    }


def assess_overfitting(train_metrics: dict[str, float], validation_metrics: dict[str, float], metric: str) -> dict[str, Any]:
    train_value = float(train_metrics.get(metric, float("nan")))
    val_value = float(validation_metrics.get(metric, float("nan")))
    if not (math.isfinite(train_value) and math.isfinite(val_value)):
        return {"status": "not_available", "metric": metric, "gap": None, "severity": "info"}
    if metric in {"rmse", "mae"}:
        denominator = max(abs(train_value), 1e-9)
        gap = max(0.0, (val_value - train_value) / denominator)
        threshold_medium, threshold_high = 0.25, 0.5
    else:
        gap = max(0.0, train_value - val_value)
        threshold_medium, threshold_high = 0.08, 0.15
    severity = "high" if gap >= threshold_high else "medium" if gap >= threshold_medium else "info"
    status = "risk" if severity in {"medium", "high"} else "ok"
    return {
        "status": status,
        "metric": metric,
        "train_value": round(train_value, 6),
        "validation_value": round(val_value, 6),
        "gap": round(float(gap), 6),
        "severity": severity,
    }


def audit_supervised_ml(
    df: pd.DataFrame,
    *,
    target: str,
    task: str,
    requested_metric: str = "auto",
    split_strategy: str = "auto",
    time_column: str | None = None,
) -> dict[str, Any]:
    if target not in df.columns:
        raise ValueError("Variable cible inconnue")
    work = df.dropna(subset=[target]).copy()
    y = work[target]
    X = work.drop(columns=[target])
    findings: list[dict[str, Any]] = []
    excluded: dict[str, str] = {}

    if len(work) < 40:
        findings.append(_finding("sample_too_small", "blocking", f"Échantillon insuffisant ({len(work)} lignes). AutoML exige au moins 40 observations complètes sur la cible."))
    elif len(work) < 100:
        findings.append(_finding("small_sample", "medium", f"Échantillon limité ({len(work)} lignes). Les métriques peuvent être instables."))

    if task == "classification":
        counts = y.value_counts(dropna=True)
        if len(counts) < 2:
            findings.append(_finding("single_class", "blocking", "La cible de classification doit contenir au moins deux classes."))
        elif int(counts.min()) < 3:
            findings.append(_finding("class_too_small", "blocking", "Chaque classe doit contenir au moins 3 observations pour une validation fiable.", details={str(k): int(v) for k, v in counts.items()}))
        else:
            ratio = float(counts.min() / counts.max())
            if ratio < 0.5:
                findings.append(_finding("class_imbalance", "high" if ratio < 0.2 else "medium", f"Déséquilibre de classes détecté (ratio minoritaire/majoritaire={ratio:.3f}).", ratio=round(ratio, 6), details={str(k): int(v) for k, v in counts.items()}))

    for col in X.columns:
        s = X[col]
        non_null = max(1, int(s.notna().sum()))
        unique = int(s.nunique(dropna=True))
        unique_ratio = float(unique / non_null)
        if unique <= 1:
            excluded[str(col)] = "constant"
            continue
        temporal_like = pd.api.types.is_datetime64_any_dtype(s) or bool(_TIME_PATTERN.search(str(col)))
        if unique_ratio > 0.98 and not temporal_like and (_ID_PATTERN.search(str(col)) or not pd.api.types.is_float_dtype(s)):
            excluded[str(col)] = "identifier_or_quasi_unique"
            continue

        equality = _normalized_equal_ratio(s, y)
        corr = _numeric_corr(s, y)
        if equality >= 0.995:
            excluded[str(col)] = "direct_target_copy"
            findings.append(_finding("target_copy_leakage", "blocking", f"{col} reproduit pratiquement la cible ({equality:.1%} d'égalité).", column=str(col), equality_ratio=round(equality, 6)))
            continue
        if corr is not None and abs(corr) >= 0.995:
            excluded[str(col)] = "near_perfect_target_correlation"
            findings.append(_finding("numeric_target_leakage", "high", f"{col} présente une corrélation quasi parfaite avec la cible ({corr:.4f}).", column=str(col), correlation=round(corr, 6)))
            continue
        if _deterministic_proxy(s, y):
            findings.append(_finding("deterministic_target_proxy", "high", f"{col} détermine parfaitement la cible dans l'échantillon. Vérifier s'il s'agit d'une variable post-résultat.", column=str(col)))

    id_columns = [col for col, reason in excluded.items() if reason == "identifier_or_quasi_unique"]
    if id_columns:
        findings.append(_finding("identifier_features", "medium", "Identifiants/quasi-identifiants exclus automatiquement du modèle.", columns=id_columns[:20]))
    constants = [col for col, reason in excluded.items() if reason == "constant"]
    if constants:
        findings.append(_finding("constant_features", "low", "Variables constantes exclues automatiquement.", columns=constants[:20]))

    temporal = detect_time_columns(X)
    requested_split = split_strategy if split_strategy in {"auto", "random", "temporal"} else "auto"
    selected_time: str | None = None
    effective_split = "random"
    if time_column:
        if time_column not in X.columns:
            findings.append(_finding("invalid_time_column", "blocking", f"La colonne temporelle {time_column!r} n'existe pas parmi les variables explicatives."))
        else:
            parsed, ratio = _parse_temporal(X[time_column])
            if parsed is None:
                findings.append(_finding("invalid_time_column", "blocking", f"La colonne {time_column!r} ne peut pas être interprétée comme date/temps de manière fiable.", parse_ratio=round(ratio, 6)))
            else:
                selected_time = time_column
    elif temporal:
        selected_time = str(temporal[0]["column"])

    if requested_split == "temporal":
        if selected_time:
            effective_split = "temporal"
        else:
            findings.append(_finding("temporal_split_unavailable", "blocking", "Un split temporel a été demandé mais aucune colonne temporelle fiable n'est disponible."))
    elif requested_split == "auto" and selected_time:
        effective_split = "temporal"
    else:
        effective_split = "random"

    if selected_time and effective_split == "temporal":
        excluded.setdefault(selected_time, "split_only_time_column")
        findings.append(_finding("temporal_split_enforced", "info", f"Split chronologique activé sur {selected_time}; le timestamp brut est exclu des features pour éviter la mémorisation temporelle.", column=selected_time))
        if task == "classification":
            parsed, _ = _parse_temporal(work[selected_time])
            if parsed is not None:
                order = parsed.sort_values(kind="stable").index
                n = len(order)
                train_end = max(1, int(n * 0.60))
                val_end = max(train_end + 1, int(n * 0.80))
                val_end = min(val_end, n - 1)
                parts = {
                    "train": y.loc[order[:train_end]],
                    "validation": y.loc[order[train_end:val_end]],
                    "test": y.loc[order[val_end:]],
                }
                insufficient = [name for name, values in parts.items() if int(values.nunique(dropna=True)) < 2]
                if insufficient:
                    findings.append(_finding("temporal_class_coverage", "blocking", "Le split chronologique produit une partition avec moins de deux classes; davantage d'historique est requis avant entraînement.", partitions=insufficient))
    elif temporal:
        findings.append(_finding("temporal_signal_present", "medium", "Variables temporelles détectées mais split aléatoire explicitement demandé.", columns=[x["column"] for x in temporal[:10]]))

    metric_policy = govern_metric(task, y, requested_metric)
    if metric_policy.get("overridden"):
        findings.append(_finding("metric_governance_override", "high", metric_policy["reason"], requested=metric_policy["requested"], effective=metric_policy["effective"]))

    usable = [str(c) for c in X.columns if str(c) not in excluded]
    blocking = [f for f in findings if f.get("severity") == "blocking"]
    if not usable:
        blocking.append(_finding("no_safe_features", "blocking", "Aucune variable explicative sûre ne reste après application des garde-fous."))
        findings.append(blocking[-1])

    status = "blocked" if blocking else "warn" if any(f.get("severity") in {"high", "medium"} for f in findings) else "pass"
    return {
        "status": status,
        "task": task,
        "target": target,
        "rows": len(work),
        "requested_metric": requested_metric,
        "metric_policy": metric_policy,
        "requested_split_strategy": requested_split,
        "split_policy": {"strategy": effective_split, "time_column": selected_time, "temporal_candidates": temporal[:10]},
        "excluded_features": [{"column": col, "reason": reason} for col, reason in excluded.items()],
        "usable_features": usable,
        "findings": findings,
        "blocking_findings": len(blocking),
        "test_policy": {
            "final_test_isolated": True,
            "selection_uses_test": False,
            "tuning_uses_test": False,
        },
    }
