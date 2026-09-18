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


def _box_stats_array(values: np.ndarray) -> dict[str, float | None]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"min": None, "q1": None, "median": None, "q3": None, "max": None, "whisker_low": None, "whisker_high": None}
    q1, med, q3 = np.quantile(arr, [0.25, 0.5, 0.75])
    iqr = q3 - q1
    low = arr[arr >= q1 - 1.5 * iqr]
    high = arr[arr <= q3 + 1.5 * iqr]
    return {
        "min": _f(np.min(arr)), "q1": _f(q1), "median": _f(med), "q3": _f(q3), "max": _f(np.max(arr)),
        "whisker_low": _f(np.min(low) if len(low) else np.min(arr)),
        "whisker_high": _f(np.max(high) if len(high) else np.max(arr)),
    }


def _group_summary(levels: list[str], arrays: list[np.ndarray]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for level, arr in zip(levels, arrays):
        rows.append({
            "group": level, "n": int(len(arr)), "mean": _f(np.mean(arr)) if len(arr) else None,
            "median": _f(np.median(arr)) if len(arr) else None,
            "std": _f(np.std(arr, ddof=1)) if len(arr) > 1 else None,
            "boxplot": _box_stats_array(arr),
        })
    return rows


def _magnitude(value: float | None, thresholds: tuple[float, float, float] = (0.1, 0.3, 0.5)) -> str | None:
    if value is None or not math.isfinite(float(value)):
        return None
    a = abs(float(value))
    if a < thresholds[0]: return "négligeable"
    if a < thresholds[1]: return "faible"
    if a < thresholds[2]: return "modéré"
    return "fort"


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
        if len(pair) > 500:
            idx = np.linspace(0, len(pair) - 1, 500).astype(int)
            plot_pair = pair.iloc[idx]
        else:
            plot_pair = pair
        return {
            **base, "statistic": _f(stat), "p_value": _f(p), "n": int(len(pair)), "variables": [x, y],
            "significant": bool(p < 0.05),
            "effect_size": {"name": "r" if test == "pearson" else "rho", "value": _f(stat), "magnitude": _magnitude(_f(stat))},
            "scatter_points": [{"x": _f(a), "y": _f(b)} for a, b in plot_pair.itertuples(index=False, name=None)],
        }

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
            return {
                **base, "statistic": _f(odds), "statistic_name": "odds_ratio", "p_value": _f(p),
                "significant": bool(p < 0.05), "contingency": _table_rows(table),
                "contingency_columns": [str(c) for c in table.columns],
                "effect_size": {"name": "Odds ratio", "value": _f(odds), "magnitude": None},
            }
        chi2, p, dof, expected = stats.chi2_contingency(table)
        expected_arr = np.asarray(expected)
        n = float(table.to_numpy().sum())
        denom = n * max(1, min(table.shape[0] - 1, table.shape[1] - 1))
        cramers_v = math.sqrt(float(chi2) / denom) if denom > 0 else np.nan
        return {
            **base, "statistic": _f(chi2), "p_value": _f(p), "dof": int(dof), "significant": bool(p < 0.05),
            "min_expected": _f(expected_arr.min()), "pct_expected_lt5": _f((expected_arr < 5).mean() * 100),
            "contingency": _table_rows(table), "contingency_columns": [str(c) for c in table.columns],
            "effect_size": {"name": "V de Cramér", "value": _f(cramers_v), "magnitude": _magnitude(_f(cramers_v))},
        }

    if test in {"paired_t", "wilcoxon"}:
        if not x or not y or x not in df.columns or y not in df.columns:
            raise ValueError("Sélectionnez deux variables numériques appariées")
        pair = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) < 3:
            raise ValueError("Échantillon apparié insuffisant")
        diff = pair[x] - pair[y]
        if test == "paired_t":
            stat, p = stats.ttest_rel(pair[x], pair[y])
            sd = float(diff.std(ddof=1))
            es = float(diff.mean() / sd) if sd > 1e-12 else np.nan
            effect = {"name": "Cohen dz", "value": _f(es), "magnitude": _magnitude(_f(es), (0.2, 0.5, 0.8))}
        else:
            stat, p = stats.wilcoxon(pair[x], pair[y])
            effect = None
        plot_pair = pair.iloc[np.linspace(0, len(pair)-1, min(500, len(pair))).astype(int)]
        return {
            **base, "statistic": _f(stat), "p_value": _f(p), "n": int(len(pair)), "significant": bool(p < 0.05),
            "normality_difference": _shapiro(diff.to_numpy()), "effect_size": effect,
            "scatter_points": [{"x": _f(a), "y": _f(b)} for a, b in plot_pair.itertuples(index=False, name=None)],
        }

    if not value or not group:
        raise ValueError("Sélectionnez une variable mesurée et une variable de groupe")
    levels, arrays = _group_values(df, value, group)
    sizes = {levels[i]: int(len(arrays[i])) for i in range(len(levels))}
    normality = [{"group": levels[i], **_shapiro(arrays[i])} for i in range(len(levels))]
    levene_stat, levene_p = stats.levene(*arrays, center="median") if len(arrays) >= 2 else (np.nan, np.nan)
    diagnostics = {"groups": sizes, "normality": normality, "levene": {"statistic": _f(levene_stat), "p_value": _f(levene_p)}}
    summary = _group_summary(levels, arrays)
    effect: dict[str, Any] | None = None

    if test in {"student_t", "welch_t", "mann_whitney"}:
        if len(arrays) != 2:
            raise ValueError("Ce test nécessite exactement deux groupes")
        if test == "student_t":
            stat, p = stats.ttest_ind(arrays[0], arrays[1], equal_var=True)
            n1, n2 = len(arrays[0]), len(arrays[1])
            s1, s2 = np.var(arrays[0], ddof=1), np.var(arrays[1], ddof=1)
            pooled = math.sqrt(((n1-1)*s1 + (n2-1)*s2) / max(1, n1+n2-2))
            d = (float(np.mean(arrays[0])) - float(np.mean(arrays[1]))) / pooled if pooled > 1e-12 else np.nan
            effect = {"name": "Cohen d", "value": _f(d), "magnitude": _magnitude(_f(d), (0.2, 0.5, 0.8))}
        elif test == "welch_t":
            stat, p = stats.ttest_ind(arrays[0], arrays[1], equal_var=False)
            pooled = math.sqrt((np.var(arrays[0], ddof=1) + np.var(arrays[1], ddof=1)) / 2)
            d = (float(np.mean(arrays[0])) - float(np.mean(arrays[1]))) / pooled if pooled > 1e-12 else np.nan
            effect = {"name": "Cohen d", "value": _f(d), "magnitude": _magnitude(_f(d), (0.2, 0.5, 0.8))}
        else:
            stat, p = stats.mannwhitneyu(arrays[0], arrays[1], alternative="two-sided")
            rb = 1 - (2 * float(stat)) / max(1, len(arrays[0]) * len(arrays[1]))
            effect = {"name": "Corrélation bisériale de rang", "value": _f(rb), "magnitude": _magnitude(_f(rb))}
    elif test == "anova_oneway":
        stat, p = stats.f_oneway(*arrays)
        all_values = np.concatenate(arrays)
        grand = float(np.mean(all_values))
        ss_between = sum(len(a) * (float(np.mean(a)) - grand) ** 2 for a in arrays)
        ss_total = float(np.sum((all_values - grand) ** 2))
        eta2 = ss_between / ss_total if ss_total > 1e-12 else np.nan
        effect = {"name": "Eta²", "value": _f(eta2), "magnitude": _magnitude(_f(eta2), (0.01, 0.06, 0.14))}
    elif test == "kruskal_wallis":
        stat, p = stats.kruskal(*arrays)
        n = sum(len(a) for a in arrays); k = len(arrays)
        eps2 = (float(stat) - k + 1) / max(1, n-k)
        effect = {"name": "Epsilon²", "value": _f(max(0.0, eps2)), "magnitude": _magnitude(_f(max(0.0, eps2)), (0.01, 0.06, 0.14))}
    else:
        raise ValueError("Test statistique non supporté")

    return {
        **base, "statistic": _f(stat), "p_value": _f(p), "significant": bool(p < 0.05), "value": value,
        "group": group, "levels": levels, "diagnostics": diagnostics, "group_summary": summary, "effect_size": effect,
    }

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
