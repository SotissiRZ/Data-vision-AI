from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def _f(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _numeric(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _shapiro(values: np.ndarray) -> dict:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return {"statistic": None, "p_value": None, "n": int(len(arr)), "valid": False}
    sampled = False
    if len(arr) > 5000:
        rng = np.random.default_rng(42)
        arr = rng.choice(arr, 5000, replace=False)
        sampled = True
    s, p = stats.shapiro(arr)
    return {"statistic": _f(s), "p_value": _f(p), "n": int(len(arr)), "valid": True, "sampled": sampled}


def correlation_analysis(df: pd.DataFrame, columns: list[str], method: str = "pearson") -> dict:
    if method not in {"pearson", "spearman"}:
        raise ValueError("Méthode de corrélation non supportée")
    cols = [c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if len(cols) < 2:
        raise ValueError("Sélectionnez au moins deux variables numériques")
    if len(cols) > 40:
        raise ValueError("Limitez la matrice à 40 variables")
    work = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = work.corr(method=method)
    matrix = [{"variable": r, **{c: _f(corr.loc[r, c]) for c in cols}} for r in cols]
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            pair = work[[a, b]].dropna()
            if len(pair) < 3:
                continue
            if method == "pearson":
                stat, p = stats.pearsonr(pair[a], pair[b])
            else:
                stat, p = stats.spearmanr(pair[a], pair[b])
            pairs.append({"x": a, "y": b, "coefficient": _f(stat), "p_value": _f(p), "n": int(len(pair)), "abs": abs(float(stat)) if math.isfinite(float(stat)) else None})
    pairs.sort(key=lambda x: x["abs"] if x["abs"] is not None else -1, reverse=True)
    return {"method": method, "columns": cols, "matrix": matrix, "pairs": pairs}


def _group_values(df: pd.DataFrame, value: str, group: str) -> tuple[list[str], list[np.ndarray]]:
    if value not in df.columns or group not in df.columns:
        raise ValueError("Variable inconnue")
    if not pd.api.types.is_numeric_dtype(df[value]):
        raise ValueError("La variable mesurée doit être numérique")
    levels = [str(x) for x in df[group].dropna().astype(str).unique().tolist()]
    if len(levels) < 2:
        raise ValueError("La variable de groupe doit contenir au moins deux groupes")
    if len(levels) > 30:
        raise ValueError("Trop de groupes pour ce test")
    arrays = [_numeric(df.loc[df[group].astype(str) == level, value]) for level in levels]
    keep = [(l, a) for l, a in zip(levels, arrays) if len(a) > 0]
    return [x[0] for x in keep], [x[1] for x in keep]


def statistical_test(df: pd.DataFrame, test: str, *, value: str | None = None, group: str | None = None,
                     x: str | None = None, y: str | None = None, paired: bool = False) -> dict:
    test = test.lower()
    base = {"test": test, "alpha": 0.05}

    if test in {"pearson", "spearman"}:
        if not x or not y or x not in df.columns or y not in df.columns:
            raise ValueError("Sélectionnez deux variables")
        pair = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) < 3:
            raise ValueError("Échantillon insuffisant")
        stat, p = (stats.pearsonr(pair[x], pair[y]) if test == "pearson" else stats.spearmanr(pair[x], pair[y]))
        return {**base, "statistic": _f(stat), "p_value": _f(p), "n": int(len(pair)), "variables": [x, y], "significant": bool(p < 0.05)}

    if test in {"chi_square", "fisher"}:
        if not x or not y or x not in df.columns or y not in df.columns:
            raise ValueError("Sélectionnez deux variables catégorielles")
        table = pd.crosstab(df[x], df[y])
        if table.shape[0] < 2 or table.shape[1] < 2:
            raise ValueError("Table de contingence insuffisante")
        if table.shape[0] > 30 or table.shape[1] > 30:
            raise ValueError("Table de contingence trop grande")
        if test == "fisher":
            if table.shape != (2, 2):
                raise ValueError("Le test exact de Fisher est limité aux tables 2×2")
            odds, p = stats.fisher_exact(table.to_numpy())
            return {**base, "statistic": _f(odds), "statistic_name": "odds_ratio", "p_value": _f(p), "significant": bool(p < 0.05), "contingency": _table_rows(table)}
        chi2, p, dof, expected = stats.chi2_contingency(table)
        expected_arr = np.asarray(expected)
        return {**base, "statistic": _f(chi2), "p_value": _f(p), "dof": int(dof), "significant": bool(p < 0.05), "min_expected": _f(expected_arr.min()), "pct_expected_lt5": _f((expected_arr < 5).mean() * 100), "contingency": _table_rows(table)}

    if test in {"paired_t", "wilcoxon"}:
        if not x or not y or x not in df.columns or y not in df.columns:
            raise ValueError("Sélectionnez deux variables numériques appariées")
        pair = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) < 3:
            raise ValueError("Échantillon apparié insuffisant")
        if test == "paired_t":
            stat, p = stats.ttest_rel(pair[x], pair[y])
        else:
            stat, p = stats.wilcoxon(pair[x], pair[y])
        return {**base, "statistic": _f(stat), "p_value": _f(p), "n": int(len(pair)), "significant": bool(p < 0.05), "normality_difference": _shapiro((pair[x] - pair[y]).to_numpy())}

    if not value or not group:
        raise ValueError("Sélectionnez une variable mesurée et une variable de groupe")
    levels, arrays = _group_values(df, value, group)
    sizes = {levels[i]: int(len(arrays[i])) for i in range(len(levels))}
    normality = [{"group": levels[i], **_shapiro(arrays[i])} for i in range(len(levels))]
    levene_stat, levene_p = stats.levene(*arrays, center="median") if len(arrays) >= 2 else (np.nan, np.nan)
    diagnostics = {"groups": sizes, "normality": normality, "levene": {"statistic": _f(levene_stat), "p_value": _f(levene_p)}}

    if test in {"student_t", "welch_t", "mann_whitney"}:
        if len(arrays) != 2:
            raise ValueError("Ce test nécessite exactement deux groupes")
        if test == "student_t":
            stat, p = stats.ttest_ind(arrays[0], arrays[1], equal_var=True)
        elif test == "welch_t":
            stat, p = stats.ttest_ind(arrays[0], arrays[1], equal_var=False)
        else:
            stat, p = stats.mannwhitneyu(arrays[0], arrays[1], alternative="two-sided")
    elif test == "anova_oneway":
        stat, p = stats.f_oneway(*arrays)
    elif test == "kruskal_wallis":
        stat, p = stats.kruskal(*arrays)
    else:
        raise ValueError("Test statistique non supporté")

    return {**base, "statistic": _f(stat), "p_value": _f(p), "significant": bool(p < 0.05), "value": value, "group": group, "levels": levels, "diagnostics": diagnostics}


def _table_rows(table: pd.DataFrame) -> list[dict]:
    cols = [str(c) for c in table.columns]
    rows = []
    for idx, row in table.iterrows():
        rows.append({"row": str(idx), **{cols[i]: int(row.iloc[i]) for i in range(len(cols))}})
    return rows


def test_advisor(df: pd.DataFrame, *, value: str | None = None, group: str | None = None,
                 x: str | None = None, y: str | None = None, paired: bool = False) -> dict:
    """Deterministic advisor based on variable types and diagnostics; no LLM is used."""
    if paired:
        if not x or not y or x not in df.columns or y not in df.columns:
            raise ValueError("Sélectionnez deux variables appariées")
        pair = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
        normality = _shapiro((pair[x] - pair[y]).to_numpy())
        recommended = "paired_t" if normality.get("p_value") is not None and normality["p_value"] >= 0.05 else "wilcoxon"
        return {"recommended": recommended, "reason": "Normalité des différences évaluée par Shapiro-Wilk.", "diagnostics": {"n": int(len(pair)), "normality_difference": normality}, "alternatives": ["paired_t", "wilcoxon"]}

    if x and y and x in df.columns and y in df.columns and not value and not group:
        xnum = pd.api.types.is_numeric_dtype(df[x]); ynum = pd.api.types.is_numeric_dtype(df[y])
        if xnum and ynum:
            pair = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
            nx, ny = _shapiro(pair[x].to_numpy()), _shapiro(pair[y].to_numpy())
            rec = "pearson" if all(z.get("p_value") is not None and z["p_value"] >= 0.05 for z in (nx, ny)) else "spearman"
            return {"recommended": rec, "reason": "Deux variables numériques; choix Pearson/Spearman selon la normalité marginale.", "diagnostics": {"n": int(len(pair)), "normality_x": nx, "normality_y": ny}, "alternatives": ["pearson", "spearman"]}
        table = pd.crosstab(df[x], df[y])
        rec = "fisher" if table.shape == (2, 2) and (table.to_numpy() < 5).any() else "chi_square"
        return {"recommended": rec, "reason": "Deux variables catégorielles; Fisher si table 2×2 avec faibles effectifs, sinon χ².", "diagnostics": {"shape": list(table.shape), "min_cell": int(table.to_numpy().min()) if table.size else 0}, "alternatives": ["chi_square", "fisher"]}

    if not value or not group:
        raise ValueError("Indiquez soit value/group, soit x/y")
    levels, arrays = _group_values(df, value, group)
    normality = [{"group": levels[i], **_shapiro(arrays[i])} for i in range(len(arrays))]
    lev_stat, lev_p = stats.levene(*arrays, center="median")
    normal = all(x.get("p_value") is not None and x["p_value"] >= 0.05 for x in normality)
    if len(arrays) == 2:
        if normal:
            rec = "student_t" if lev_p >= 0.05 else "welch_t"
            reason = "Deux groupes et normalité acceptable; Levene détermine l'hypothèse d'égalité des variances."
        else:
            rec, reason = "mann_whitney", "Deux groupes avec normalité non satisfaite; test non paramétrique recommandé."
        alternatives = ["student_t", "welch_t", "mann_whitney"]
    else:
        if normal and lev_p >= 0.05:
            rec, reason = "anova_oneway", "Au moins trois groupes, normalité acceptable et variances homogènes."
        else:
            rec, reason = "kruskal_wallis", "Au moins trois groupes avec hypothèses paramétriques fragiles; Kruskal-Wallis recommandé."
        alternatives = ["anova_oneway", "kruskal_wallis"]
    return {"recommended": rec, "reason": reason, "diagnostics": {"groups": {levels[i]: int(len(arrays[i])) for i in range(len(arrays))}, "normality": normality, "levene": {"statistic": _f(lev_stat), "p_value": _f(lev_p)}}, "alternatives": alternatives}
