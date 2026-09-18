from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def _numeric(df: pd.DataFrame, col: str | None) -> bool:
    return bool(col and col in df.columns and pd.api.types.is_numeric_dtype(df[col]))


def recommend_visualizations(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    cols = [c for c in columns if c in df.columns]
    if not cols:
        cols = list(df.columns[:10])
    numeric = [c for c in cols if _numeric(df, c)]
    categorical = [c for c in cols if c not in numeric]
    datetime_cols = [c for c in cols if pd.api.types.is_datetime64_any_dtype(df[c]) or (df[c].dtype == object and pd.to_datetime(df[c], errors="coerce", format="mixed").notna().mean() > 0.8)]
    recs: list[dict] = []
    if len(numeric) == 1:
        recs += [
            {"type": "histogram", "x": numeric[0], "reason": "Distribution et fréquence d'une variable numérique"},
            {"type": "density", "x": numeric[0], "reason": "Forme lissée de la distribution"},
            {"type": "box", "y": numeric[0], "reason": "Dispersion et valeurs aberrantes"},
        ]
    if len(numeric) >= 2:
        recs.append({"type": "scatter", "x": numeric[0], "y": numeric[1], "reason": "Relation entre deux variables numériques"})
        recs.append({"type": "heatmap", "reason": "Vue globale des corrélations entre variables numériques"})
    if categorical and numeric:
        recs += [
            {"type": "box", "x": categorical[0], "y": numeric[0], "reason": "Comparer une mesure entre catégories"},
            {"type": "bar", "x": categorical[0], "y": numeric[0], "aggregation": "mean", "reason": "Comparer les moyennes par catégorie"},
        ]
    if categorical and not numeric:
        recs.append({"type": "bar", "x": categorical[0], "aggregation": "count", "reason": "Fréquences par catégorie"})
    if datetime_cols and numeric:
        recs.append({"type": "line", "x": datetime_cols[0], "y": numeric[0], "aggregation": "mean", "reason": "Évolution temporelle de la mesure"})
    return recs[:8]


def build_visualization(df: pd.DataFrame, *, chart_type: str, x: str | None = None, y: str | None = None,
                        color: str | None = None, aggregation: str = "none", bins: int = 20) -> dict:
    chart_type = chart_type.lower()
    for c in [x, y, color]:
        if c and c not in df.columns:
            raise ValueError(f"Colonne inconnue: {c}")
    if chart_type == "auto":
        recs = recommend_visualizations(df, [c for c in [x, y] if c])
        if not recs:
            raise ValueError("Impossible de recommander un graphique avec cette sélection")
        first = recs[0]
        chart_type = first["type"]
        x = first.get("x", x); y = first.get("y", y); aggregation = first.get("aggregation", aggregation)

    if chart_type == "histogram":
        if not x or not _numeric(df, x):
            raise ValueError("L'histogramme nécessite une variable X numérique")
        s = pd.to_numeric(df[x], errors="coerce").dropna()
        bins = max(5, min(int(bins), 80))
        counts, edges = np.histogram(s, bins=bins)
        data = [{"from": float(edges[i]), "to": float(edges[i+1]), "count": int(counts[i])} for i in range(len(counts))]
        return {"type": "histogram", "x": x, "data": data, "n": int(len(s)), "title": f"Distribution de {x}"}

    if chart_type == "density":
        if not x or not _numeric(df, x):
            raise ValueError("La densité nécessite une variable X numérique")
        s = pd.to_numeric(df[x], errors="coerce").dropna()
        if len(s) < 3:
            raise ValueError("Au moins 3 valeurs sont nécessaires pour estimer une densité")
        lo, hi = float(s.min()), float(s.max())
        if np.isclose(lo, hi):
            raise ValueError("La variable est constante; la densité n'est pas informative")
        grid = np.linspace(lo, hi, 120)
        try:
            kde = stats.gaussian_kde(s.to_numpy(dtype=float))
            dens = kde(grid)
        except Exception:
            counts, edges = np.histogram(s, bins=max(10, min(40, int(np.sqrt(len(s))))), density=True)
            mids = (edges[:-1] + edges[1:]) / 2
            dens = np.interp(grid, mids, counts)
        data = [{"x": float(a), "density": float(b)} for a, b in zip(grid, dens)]
        return {"type": "density", "x": x, "data": data, "n": int(len(s)), "title": f"Densité de {x}"}

    if chart_type == "heatmap":
        numeric_cols = [c for c in df.columns if _numeric(df, c)][:12]
        if len(numeric_cols) < 2:
            raise ValueError("La heatmap nécessite au moins deux variables numériques")
        corr = df[numeric_cols].corr(method="pearson", min_periods=2)
        matrix = []
        for row in numeric_cols:
            item = {"variable": row}
            for col in numeric_cols:
                value = corr.loc[row, col]
                item[col] = None if pd.isna(value) else float(value)
            matrix.append(item)
        return {"type": "heatmap", "columns": numeric_cols, "data": matrix, "title": "Matrice de corrélation — Pearson"}

    if chart_type == "scatter":
        if not x or not y or not _numeric(df, x) or not _numeric(df, y):
            raise ValueError("Le nuage de points nécessite X et Y numériques")
        cols = [x, y] + ([color] if color else [])
        work = df[cols].copy(); work[x] = pd.to_numeric(work[x], errors="coerce"); work[y] = pd.to_numeric(work[y], errors="coerce"); work = work.dropna(subset=[x, y])
        if len(work) > 3000:
            work = work.sample(3000, random_state=42)
        data = [{"x": float(r[x]), "y": float(r[y]), **({"color": str(r[color])} if color else {})} for _, r in work.iterrows()]
        return {"type": "scatter", "x": x, "y": y, "color": color, "data": data, "n": int(len(data)), "title": f"{y} selon {x}"}

    if chart_type == "box":
        value = y or x
        if not value or not _numeric(df, value):
            raise ValueError("Le boxplot nécessite une variable numérique")
        group = x if y else None
        if group and group == value:
            group = None
        if group:
            levels = df[group].dropna().astype(str).value_counts().head(30).index.tolist()
        else:
            levels = ["Toutes les observations"]
        data=[]
        for level in levels:
            s = pd.to_numeric(df.loc[df[group].astype(str)==level, value], errors="coerce").dropna() if group else pd.to_numeric(df[value], errors="coerce").dropna()
            if s.empty: continue
            q1, med, q3 = s.quantile([.25,.5,.75]); iqr=q3-q1; lo=q1-1.5*iqr; hi=q3+1.5*iqr
            data.append({"group": level, "min": float(s.min()), "q1": float(q1), "median": float(med), "q3": float(q3), "max": float(s.max()), "whisker_low": float(s[s>=lo].min()), "whisker_high": float(s[s<=hi].max()), "n": int(len(s))})
        return {"type":"box","x":group,"y":value,"data":data,"title":f"Distribution de {value}" + (f" par {group}" if group else "")}

    if chart_type in {"bar", "line", "area"}:
        if not x:
            raise ValueError("Sélectionnez une variable X")
        work = df[[x] + ([y] if y else [])].copy()
        if aggregation == "count" or not y:
            out = work.groupby(x, dropna=False).size().reset_index(name="value")
            y_name = "count"
        else:
            if not _numeric(df, y):
                raise ValueError("Y doit être numérique pour cette agrégation")
            if aggregation not in {"mean","sum","median","min","max"}:
                raise ValueError("Agrégation supportée: mean, sum, median, min, max, count")
            out = work.groupby(x, dropna=False)[y].agg(aggregation).reset_index(name="value")
            y_name = f"{aggregation}({y})"
        if chart_type == "bar":
            out = out.sort_values("value", ascending=False).head(100)
        else:
            parsed_dates = pd.to_datetime(out[x], errors="coerce", format="mixed")
            if parsed_dates.notna().mean() > 0.8:
                out = out.assign(__sort=parsed_dates).sort_values("__sort").drop(columns="__sort")
            elif pd.api.types.is_numeric_dtype(out[x]):
                out = out.sort_values(x)
            out = out.head(500)
        data=[{"label": str(r[x]), "value": float(r["value"])} for _,r in out.iterrows() if pd.notna(r["value"])]
        return {"type":chart_type,"x":x,"y":y,"aggregation":aggregation,"data":data,"value_label":y_name,"title":f"{y_name} par {x}"}

    raise ValueError("Type de graphique non supporté")
