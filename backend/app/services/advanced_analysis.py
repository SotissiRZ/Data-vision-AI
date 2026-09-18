from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.multicomp import pairwise_tukeyhsd


def _float(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(value) else value


def _shapiro(values: pd.Series | np.ndarray) -> dict:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return {"statistic": None, "p_value": None, "n": int(len(arr)), "valid": False}
    if len(arr) > 5000:
        # scipy documents the p-value as less accurate for very large n; sample deterministically.
        rng = np.random.default_rng(42)
        arr = rng.choice(arr, size=5000, replace=False)
    stat, p = stats.shapiro(arr)
    return {"statistic": _float(stat), "p_value": _float(p), "n": int(len(arr)), "valid": True}


def _box_stats(values: pd.Series | np.ndarray) -> dict:
    arr = pd.Series(values, dtype="float64").dropna()
    if arr.empty:
        return {"min": None, "q1": None, "median": None, "q3": None, "max": None, "whisker_low": None, "whisker_high": None, "outliers": 0}
    q1, median, q3 = arr.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    low_fence, high_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    wl = arr[arr >= low_fence].min() if (arr >= low_fence).any() else arr.min()
    wh = arr[arr <= high_fence].max() if (arr <= high_fence).any() else arr.max()
    outliers = int(((arr < low_fence) | (arr > high_fence)).sum())
    return {
        "min": _float(arr.min()), "q1": _float(q1), "median": _float(median), "q3": _float(q3), "max": _float(arr.max()),
        "whisker_low": _float(wl), "whisker_high": _float(wh), "outliers": outliers,
    }


def regression_analysis(df: pd.DataFrame, dependent: str, independents: list[str]) -> dict:
    if dependent not in df.columns:
        raise ValueError("Variable dépendante inconnue")
    independents = [c for c in independents if c in df.columns and c != dependent]
    if not independents:
        raise ValueError("Sélectionnez au moins une variable explicative")
    if not pd.api.types.is_numeric_dtype(df[dependent]):
        raise ValueError("La variable dépendante doit être numérique pour la régression linéaire")

    use = df[[dependent] + independents].copy()
    use = use.dropna(subset=[dependent])
    if len(use) < max(8, len(independents) + 3):
        raise ValueError("Échantillon insuffisant pour cette régression")

    y = pd.to_numeric(use[dependent], errors="coerce")
    X = use[independents].copy()
    numeric = [c for c in independents if pd.api.types.is_numeric_dtype(X[c])]
    categorical = [c for c in independents if c not in numeric]
    for c in numeric:
        X[c] = pd.to_numeric(X[c], errors="coerce").fillna(pd.to_numeric(X[c], errors="coerce").median())
    for c in categorical:
        mode = X[c].mode(dropna=True)
        X[c] = X[c].fillna(mode.iloc[0] if not mode.empty else "(manquant)").astype(str)
    for c in categorical:
        if X[c].nunique(dropna=True) > 50:
            raise ValueError(f"La variable catégorielle {c} a trop de modalités pour cette régression")
    X = pd.get_dummies(X, columns=categorical, drop_first=True, dtype=float)
    if X.shape[1] > 100:
        raise ValueError("Trop de paramètres après encodage; réduisez le nombre de variables/modalités")
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median(numeric_only=True))
    y = y.loc[X.index]
    valid = y.notna()
    X, y = X.loc[valid], y.loc[valid]
    if X.shape[1] == 0:
        raise ValueError("Aucune variable explicative exploitable")
    if len(y) <= X.shape[1] + 2:
        raise ValueError("Pas assez d'observations par rapport au nombre de paramètres")

    Xc = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y.astype(float), Xc.astype(float)).fit()
    pred = model.predict(Xc)
    resid = model.resid
    conf = model.conf_int(alpha=0.05)

    coefficients = []
    for name in model.params.index:
        coefficients.append({
            "term": str(name),
            "estimate": _float(model.params[name]),
            "std_error": _float(model.bse[name]),
            "t": _float(model.tvalues[name]),
            "p_value": _float(model.pvalues[name]),
            "ci_low": _float(conf.loc[name, 0]),
            "ci_high": _float(conf.loc[name, 1]),
        })

    shapiro = _shapiro(resid)
    try:
        lm, lm_p, fval, f_p = het_breuschpagan(resid, Xc)
        bp = {"lm_statistic": _float(lm), "lm_p_value": _float(lm_p), "f_statistic": _float(fval), "f_p_value": _float(f_p)}
    except Exception:
        bp = {"lm_statistic": None, "lm_p_value": None, "f_statistic": None, "f_p_value": None}

    order = np.argsort(pred.to_numpy())
    max_points = 700
    if len(order) > max_points:
        take = np.linspace(0, len(order) - 1, max_points).astype(int)
        order = order[take]
    diagnostics = [
        {"predicted": _float(pred.iloc[i]), "residual": _float(resid.iloc[i]), "observed": _float(y.iloc[i])}
        for i in order
    ]

    # Additional visual diagnostics: residual distribution, Q-Q plot and influence.
    bins = min(24, max(8, int(math.sqrt(max(1, len(resid))))))
    hist_counts, hist_edges = np.histogram(np.asarray(resid, dtype=float), bins=bins)
    residual_histogram = [
        {"from": _float(hist_edges[i]), "to": _float(hist_edges[i+1]), "count": int(hist_counts[i])}
        for i in range(len(hist_counts))
    ]
    try:
        (theoretical, ordered_resid), (qq_slope, qq_intercept, qq_r) = stats.probplot(np.asarray(resid, dtype=float), dist="norm", fit=True)
        qq_idx = np.linspace(0, len(theoretical)-1, min(500, len(theoretical))).astype(int)
        qq_points = [{"x": _float(theoretical[i]), "y": _float(ordered_resid[i])} for i in qq_idx]
        qq_line = {"slope": _float(qq_slope), "intercept": _float(qq_intercept), "r": _float(qq_r)}
    except Exception:
        qq_points, qq_line = [], {"slope": None, "intercept": None, "r": None}
    try:
        influence_obj = model.get_influence()
        cooks = np.asarray(influence_obj.cooks_distance[0], dtype=float)
        studentized = np.asarray(influence_obj.resid_studentized_internal, dtype=float)
        labels = list(y.index)
        top = np.argsort(np.nan_to_num(cooks, nan=-1.0))[::-1][:15]
        influence = [
            {"index": str(labels[i]), "cooks_distance": _float(cooks[i]), "studentized_residual": _float(studentized[i])}
            for i in top if math.isfinite(float(cooks[i]))
        ]
    except Exception:
        influence = []

    return {
        "dependent": dependent,
        "independents": independents,
        "n": int(model.nobs),
        "r_squared": _float(model.rsquared),
        "adj_r_squared": _float(model.rsquared_adj),
        "f_statistic": _float(model.fvalue),
        "f_p_value": _float(model.f_pvalue),
        "aic": _float(model.aic),
        "bic": _float(model.bic),
        "rmse": _float(np.sqrt(np.mean(np.square(resid)))),
        "mae": _float(np.mean(np.abs(resid))),
        "coefficients": coefficients,
        "tests": {"shapiro_wilk_residuals": shapiro, "breusch_pagan": bp},
        "diagnostics": diagnostics,
        "residual_histogram": residual_histogram,
        "qq_points": qq_points,
        "qq_line": qq_line,
        "influence": influence,
    }


def _group_summaries(df: pd.DataFrame, value: str, by: list[str]) -> list[dict]:
    rows: list[dict] = []
    grouped = df.groupby(by, dropna=False, observed=True)[value]
    for key, s in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        clean = pd.to_numeric(s, errors="coerce").dropna()
        if clean.empty:
            continue
        item = {str(by[i]): str(key[i]) for i in range(len(by))}
        item.update({"n": int(len(clean)), "mean": _float(clean.mean()), "std": _float(clean.std(ddof=1)) if len(clean)>1 else None, "boxplot": _box_stats(clean)})
        rows.append(item)
    return rows


def anova_analysis(df: pd.DataFrame, response: str, factor1: str, factor2: str | None = None) -> dict:
    for c in [response, factor1] + ([factor2] if factor2 else []):
        if c not in df.columns:
            raise ValueError(f"Variable inconnue: {c}")
    if not pd.api.types.is_numeric_dtype(df[response]):
        raise ValueError("La variable réponse doit être numérique")
    if factor1 == response or (factor2 and factor2 in {response, factor1}):
        raise ValueError("Les facteurs et la variable réponse doivent être distincts")

    cols = [response, factor1] + ([factor2] if factor2 else [])
    work = df[cols].dropna().copy()
    work[response] = pd.to_numeric(work[response], errors="coerce")
    work = work.dropna(subset=[response])
    if len(work) < 6:
        raise ValueError("Échantillon insuffisant pour l'ANOVA")
    n1 = work[factor1].nunique()
    if n1 < 2:
        raise ValueError("Le premier facteur doit contenir au moins deux groupes")
    if n1 > 30:
        raise ValueError("Le premier facteur contient trop de groupes pour une ANOVA lisible (maximum 30)")
    if factor2:
        n2 = work[factor2].nunique()
        if n2 < 2:
            raise ValueError("Le second facteur doit contenir au moins deux groupes")
        if n2 > 20 or n1 * n2 > 60:
            raise ValueError("Trop de combinaisons de groupes pour l'ANOVA à deux facteurs")

    if factor2 is None:
        groups = [g[response].to_numpy(dtype=float) for _, g in work.groupby(factor1, observed=True)]
        f_stat, p_value = stats.f_oneway(*groups)
        all_values = np.concatenate(groups)
        grand_mean = float(np.mean(all_values))
        ss_between = float(sum(len(g) * (float(np.mean(g)) - grand_mean) ** 2 for g in groups))
        ss_within = float(sum(np.sum((g - float(np.mean(g))) ** 2) for g in groups))
        ss_total = ss_between + ss_within
        eta_sq = ss_between / ss_total if ss_total > 1e-15 else np.nan
        try:
            lev_stat, lev_p = stats.levene(*groups, center="median")
        except Exception:
            lev_stat, lev_p = np.nan, np.nan
        normality = []
        for key, g in work.groupby(factor1, observed=True):
            test = _shapiro(g[response])
            normality.append({"group": str(key), **test})
        tukey_obj = pairwise_tukeyhsd(endog=work[response].astype(float), groups=work[factor1].astype(str), alpha=0.05)
        tukey = []
        data = tukey_obj.summary().data
        for row in data[1:]:
            tukey.append({
                "group1": str(row[0]), "group2": str(row[1]), "mean_diff": _float(row[2]), "p_adj": _float(row[3]),
                "ci_low": _float(row[4]), "ci_high": _float(row[5]), "reject": bool(row[6]),
            })
        return {
            "type": "one_way", "response": response, "factor1": factor1, "factor2": None, "n": int(len(work)),
            "anova_table": [
                {"source": factor1, "sum_sq": _float(ss_between), "df": int(len(groups)-1), "f": _float(f_stat), "p_value": _float(p_value), "effect_size": _float(eta_sq)},
                {"source": "Résidus", "sum_sq": _float(ss_within), "df": int(len(work)-len(groups)), "f": None, "p_value": None, "effect_size": None},
            ],
            "levene": {"statistic": _float(lev_stat), "p_value": _float(lev_p)},
            "normality": normality, "tukey": tukey,
            "groups": _group_summaries(work, response, [factor1]),
        }

    # Two-way ANOVA uses neutral internal column names so arbitrary user labels remain safe.
    temp = work.rename(columns={response: "y", factor1: "f1", factor2: "f2"})[["y", "f1", "f2"]]
    model = smf.ols("y ~ C(f1) * C(f2)", data=temp).fit()
    table = anova_lm(model, typ=2)
    source_names = {"C(f1)": factor1, "C(f2)": factor2, "C(f1):C(f2)": f"{factor1} × {factor2}", "Residual": "Résidus"}
    rows = []
    residual_ss = float(table.loc["Residual", "sum_sq"]) if "Residual" in table.index else np.nan
    for idx, row in table.iterrows():
        ss = _float(row.get("sum_sq"))
        partial_eta = None
        if str(idx) != "Residual" and ss is not None and math.isfinite(residual_ss):
            denom = float(ss) + residual_ss
            partial_eta = _float(float(ss) / denom) if denom > 1e-15 else None
        rows.append({
            "source": source_names.get(str(idx), str(idx)), "sum_sq": ss, "df": _float(row.get("df")),
            "f": _float(row.get("F")), "p_value": _float(row.get("PR(>F)")), "effect_size": partial_eta,
        })
    residual_shapiro = _shapiro(model.resid)
    try:
        cell_groups = [g[response].to_numpy(dtype=float) for _, g in work.groupby([factor1, factor2], observed=True) if len(g) >= 2]
        lev_stat, lev_p = stats.levene(*cell_groups, center="median") if len(cell_groups) >= 2 else (np.nan, np.nan)
    except Exception:
        lev_stat, lev_p = np.nan, np.nan

    combined = work[factor1].astype(str) + " · " + work[factor2].astype(str)
    tukey = []
    if combined.nunique() <= 30:
        tukey_obj = pairwise_tukeyhsd(endog=work[response].astype(float), groups=combined, alpha=0.05)
        for row in tukey_obj.summary().data[1:]:
            tukey.append({"group1": str(row[0]), "group2": str(row[1]), "mean_diff": _float(row[2]), "p_adj": _float(row[3]), "ci_low": _float(row[4]), "ci_high": _float(row[5]), "reject": bool(row[6])})

    return {
        "type": "two_way", "response": response, "factor1": factor1, "factor2": factor2, "n": int(len(work)),
        "anova_table": rows,
        "levene": {"statistic": _float(lev_stat), "p_value": _float(lev_p)},
        "normality": [{"group": "Résidus du modèle", **residual_shapiro}],
        "tukey": tukey,
        "groups": _group_summaries(work, response, [factor1, factor2]),
    }


def _kmo_bartlett(x: np.ndarray) -> dict:
    n, p = x.shape
    corr = np.corrcoef(x, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)
    np.fill_diagonal(corr, 1.0)
    try:
        inv = np.linalg.pinv(corr)
        partial = np.zeros_like(corr)
        for i in range(p):
            for j in range(p):
                if i == j:
                    continue
                denom = math.sqrt(max(inv[i, i] * inv[j, j], 1e-15))
                partial[i, j] = -inv[i, j] / denom
        r2 = np.sum(np.triu(corr ** 2, 1))
        p2 = np.sum(np.triu(partial ** 2, 1))
        kmo = r2 / (r2 + p2) if (r2 + p2) > 0 else np.nan
    except Exception:
        kmo = np.nan
    try:
        det = float(np.linalg.det(corr))
        if det <= 0:
            bartlett_chi2, bartlett_p = np.nan, np.nan
        else:
            chi2 = -(n - 1 - (2 * p + 5) / 6) * math.log(det)
            df_b = p * (p - 1) / 2
            bartlett_chi2, bartlett_p = chi2, stats.chi2.sf(chi2, df_b)
    except Exception:
        bartlett_chi2, bartlett_p = np.nan, np.nan
    return {"kmo": _float(kmo), "bartlett_chi2": _float(bartlett_chi2), "bartlett_df": int(p*(p-1)/2), "bartlett_p_value": _float(bartlett_p)}


def pca_analysis(df: pd.DataFrame, columns: list[str], scale: bool = True) -> dict:
    columns = [c for c in columns if c in df.columns]
    if len(columns) < 2:
        raise ValueError("Sélectionnez au moins deux variables numériques")
    if any(not pd.api.types.is_numeric_dtype(df[c]) for c in columns):
        raise ValueError("L'ACP de cette version accepte uniquement des variables numériques")

    raw = df[columns].replace([np.inf, -np.inf], np.nan)
    if len(raw) < 3:
        raise ValueError("Échantillon insuffisant pour l'ACP")
    imputed = SimpleImputer(strategy="median").fit_transform(raw)
    if np.any(np.nanstd(imputed, axis=0) <= 1e-12):
        raise ValueError("Retirez les variables constantes avant l'ACP")
    standardized = StandardScaler().fit_transform(imputed) if scale else imputed
    n_components = min(standardized.shape)
    pca = PCA(n_components=n_components, random_state=42)
    scores = pca.fit_transform(standardized)
    ratios = pca.explained_variance_ratio_
    components = pca.components_

    # Correlation-like loadings for standardized PCA.
    loadings = components.T * np.sqrt(pca.explained_variance_)
    contributions = np.square(components.T)
    contributions = contributions / np.maximum(contributions.sum(axis=0, keepdims=True), 1e-15) * 100

    variance = []
    cum = 0.0
    for i, ratio in enumerate(ratios):
        pct = float(ratio * 100)
        cum += pct
        variance.append({"component": f"PC{i+1}", "explained_pct": pct, "cumulative_pct": cum, "eigenvalue": _float(pca.explained_variance_[i])})

    variable_rows = []
    for j, col in enumerate(columns):
        row = {"variable": col}
        for i in range(min(n_components, 8)):
            row[f"PC{i+1}"] = _float(loadings[j, i])
            row[f"contrib_PC{i+1}"] = _float(contributions[j, i])
        variable_rows.append(row)

    max_points = min(len(scores), 1000)
    idx = np.linspace(0, len(scores)-1, max_points).astype(int) if len(scores) > max_points else np.arange(len(scores))
    score_rows = [{"index": int(i), "PC1": _float(scores[i,0]), "PC2": _float(scores[i,1]) if n_components > 1 else 0.0} for i in idx]
    cov = np.cov(imputed, rowvar=False)
    covariance = [{"variable": columns[i], **{columns[j]: _float(cov[i,j]) for j in range(len(columns))}} for i in range(len(columns))]

    return {
        "columns": columns, "rows": int(len(raw)), "scale": bool(scale), "adequacy": _kmo_bartlett(standardized),
        "variance": variance, "variables": variable_rows, "scores": score_rows, "covariance": covariance,
    }


def clustering_analysis(df: pd.DataFrame, columns: list[str], k: int = 3) -> dict:
    columns = [c for c in columns if c in df.columns]
    if len(columns) < 2:
        raise ValueError("Sélectionnez au moins deux variables numériques")
    if any(not pd.api.types.is_numeric_dtype(df[c]) for c in columns):
        raise ValueError("Le clustering de cette version accepte uniquement des variables numériques")
    if not 2 <= k <= 10:
        raise ValueError("K doit être compris entre 2 et 10")

    raw = df[columns].replace([np.inf, -np.inf], np.nan)
    if len(raw) < max(6, k + 2):
        raise ValueError("Échantillon insuffisant pour ce nombre de clusters")
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x_imp = imputer.fit_transform(raw)
    if np.any(np.nanstd(x_imp, axis=0) <= 1e-12):
        raise ValueError("Retirez les variables constantes avant le clustering")
    x = scaler.fit_transform(x_imp)
    if len(np.unique(x, axis=0)) < k:
        raise ValueError("Le nombre de profils distincts est inférieur à K")

    km = KMeans(n_clusters=k, n_init=20, random_state=42)
    labels = km.fit_predict(x)
    sil = silhouette_score(x, labels) if len(np.unique(labels)) > 1 and len(x) > k else np.nan
    centers_original = scaler.inverse_transform(km.cluster_centers_)

    p2 = PCA(n_components=2, random_state=42).fit_transform(x) if x.shape[1] >= 2 else np.column_stack([x[:,0], np.zeros(len(x))])
    max_points = min(len(x), 1200)
    idx = np.linspace(0, len(x)-1, max_points).astype(int) if len(x) > max_points else np.arange(len(x))
    points = [{"index": int(i), "x": _float(p2[i,0]), "y": _float(p2[i,1]), "cluster": int(labels[i])} for i in idx]

    profiles = []
    counts = np.bincount(labels, minlength=k)
    for cluster_id in range(k):
        mask = labels == cluster_id
        item = {"cluster": cluster_id, "count": int(mask.sum()), "pct": float(mask.mean()*100)}
        for j, col in enumerate(columns):
            item[col] = _float(np.mean(x_imp[mask, j])) if mask.any() else None
        profiles.append(item)

    centers = [{"cluster": i, **{columns[j]: _float(centers_original[i,j]) for j in range(len(columns))}} for i in range(k)]
    comparison = []
    max_k = min(8, len(x)-1, len(np.unique(x, axis=0)))
    for kk in range(2, max_k+1):
        candidate = KMeans(n_clusters=kk, n_init=10, random_state=42).fit(x)
        score = silhouette_score(x, candidate.labels_) if len(np.unique(candidate.labels_)) > 1 else np.nan
        comparison.append({"k": kk, "inertia": _float(candidate.inertia_), "silhouette": _float(score)})

    return {
        "columns": columns, "k": int(k), "rows": int(len(raw)), "inertia": _float(km.inertia_), "silhouette": _float(sil),
        "pca_explained_pct": _float(PCA(n_components=2, random_state=42).fit(x).explained_variance_ratio_.sum()*100) if x.shape[1] >= 2 else None,
        "counts": [int(v) for v in counts], "centers": centers, "profiles": profiles, "points": points, "comparison": comparison,
    }
