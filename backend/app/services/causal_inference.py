from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def _sha(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _smd(values: np.ndarray, treatment: np.ndarray, weights: np.ndarray | None = None) -> float:
    values = np.asarray(values, dtype=float)
    treatment = np.asarray(treatment, dtype=int)
    if weights is None:
        weights = np.ones(len(values), dtype=float)
    else:
        weights = np.asarray(weights, dtype=float)
    out = []
    stats = []
    for group in (1, 0):
        mask = treatment == group
        w = weights[mask]
        x = values[mask]
        if not len(x) or float(w.sum()) <= 0:
            return float("nan")
        mean = float(np.average(x, weights=w))
        var = float(np.average((x - mean) ** 2, weights=w))
        stats.append((mean, var))
    pooled = float(np.sqrt(max((stats[0][1] + stats[1][1]) / 2.0, 0.0)))
    if pooled <= 1e-12:
        return 0.0
    return float((stats[0][0] - stats[1][0]) / pooled)


def estimate_ate(
    df: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    covariates: list[str],
    trim: float = 0.05,
    bootstrap_samples: int = 200,
    random_state: int = 42,
) -> dict[str, Any]:
    if treatment not in df.columns or outcome not in df.columns:
        raise ValueError("Treatment/outcome introuvable dans le dataset")
    covariates = [str(c) for c in covariates if str(c) in df.columns and str(c) not in {treatment, outcome}]
    if not covariates:
        raise ValueError("Au moins une covariable pré-traitement est requise")
    if not 0 <= float(trim) < 0.5:
        raise ValueError("trim doit être compris entre 0 et 0.5")

    work = df[[treatment, outcome, *covariates]].copy()
    work[outcome] = pd.to_numeric(work[outcome], errors="coerce")
    work = work.dropna(subset=[treatment, outcome])
    levels = list(pd.Series(work[treatment]).dropna().unique())
    if len(levels) != 2:
        raise ValueError("Le traitement doit avoir exactement deux modalités")
    levels = sorted(levels, key=lambda x: str(x))
    control_value, treated_value = levels[0], levels[1]
    t = (work[treatment] == treated_value).astype(int).to_numpy()
    if min(int(t.sum()), int((1 - t).sum())) < 5:
        raise ValueError("Au moins 5 observations sont requises dans chaque groupe")

    X = work[covariates]
    numeric = [c for c in covariates if pd.api.types.is_numeric_dtype(X[c])]
    categorical = [c for c in covariates if c not in numeric]
    transformers = []
    if numeric:
        transformers.append(("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric))
    if categorical:
        transformers.append(("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical))
    preprocess = ColumnTransformer(transformers=transformers, remainder="drop")
    model = Pipeline([
        ("preprocess", preprocess),
        ("model", LogisticRegression(max_iter=1000, solver="lbfgs", random_state=random_state)),
    ])
    model.fit(X, t)
    propensity = np.asarray(model.predict_proba(X)[:, 1], dtype=float)
    lower = float(trim)
    upper = 1.0 - lower
    overlap = (propensity >= lower) & (propensity <= upper)
    if int(overlap.sum()) < 10 or len(np.unique(t[overlap])) < 2:
        raise ValueError("Recouvrement de propension insuffisant après trimming")

    t2 = t[overlap]
    y2 = work[outcome].to_numpy(dtype=float)[overlap]
    p2 = np.clip(propensity[overlap], 1e-6, 1 - 1e-6)
    weights = np.where(t2 == 1, 1.0 / p2, 1.0 / (1.0 - p2))
    treated_mean = float(np.average(y2[t2 == 1], weights=weights[t2 == 1]))
    control_mean = float(np.average(y2[t2 == 0], weights=weights[t2 == 0]))
    ate = treated_mean - control_mean

    rng = np.random.default_rng(random_state)
    boot: list[float] = []
    idx_all = np.arange(len(y2))
    for _ in range(max(20, min(int(bootstrap_samples), 2000))):
        idx = rng.choice(idx_all, size=len(idx_all), replace=True)
        bt = t2[idx]
        if len(np.unique(bt)) < 2:
            continue
        by = y2[idx]
        bw = weights[idx]
        boot.append(float(np.average(by[bt == 1], weights=bw[bt == 1]) - np.average(by[bt == 0], weights=bw[bt == 0])))
    ci = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))] if len(boot) >= 20 else [None, None]

    balance_rows = []
    numeric_balance = numeric[:25]
    for column in numeric_balance:
        vals = pd.to_numeric(work[column], errors="coerce").to_numpy(dtype=float)[overlap]
        finite = np.isfinite(vals)
        if finite.sum() < 10 or len(np.unique(t2[finite])) < 2:
            continue
        before = _smd(vals[finite], t2[finite])
        after = _smd(vals[finite], t2[finite], weights[finite])
        balance_rows.append({"column": column, "smd_before": before, "smd_after": after})
    max_after = max((abs(float(x["smd_after"])) for x in balance_rows if np.isfinite(x["smd_after"])), default=None)

    result = {
        "method": "propensity_score_ipw",
        "estimand": "ATE",
        "treatment": treatment,
        "treated_value": treated_value,
        "control_value": control_value,
        "outcome": outcome,
        "covariates": covariates,
        "rows_input": int(len(work)),
        "rows_overlap": int(overlap.sum()),
        "trim": lower,
        "propensity": {"min": float(p2.min()), "max": float(p2.max()), "mean": float(p2.mean())},
        "weighted_outcome_means": {"treated": treated_mean, "control": control_mean},
        "effect_estimate": float(ate),
        "confidence_interval_95": ci,
        "bootstrap_samples_used": int(len(boot)),
        "balance": {"numeric_covariates": balance_rows, "max_abs_smd_after": max_after},
        "assumptions": [
            "consistency/SUTVA",
            "conditional exchangeability given supplied pre-treatment covariates",
            "positivity/overlap after trimming",
            "correct propensity model specification",
            "no material unmeasured confounding",
        ],
        "causal_claim_allowed": False,
        "interpretation_guardrail": "Estimation observationnelle. DataVision ne transforme pas automatiquement cette association ajustée en preuve causale; la validité dépend des hypothèses et du design de l'étude.",
    }
    result["analysis_sha256"] = _sha(result)
    return result
