from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _numeric(df: pd.DataFrame, col: str | None) -> bool:
    return bool(col and col in df.columns and pd.api.types.is_numeric_dtype(df[col]))


def recommend_visualizations(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    cols = [c for c in columns if c in df.columns]
    if not cols:
        cols = list(df.columns[:8])
    numeric = [c for c in cols if _numeric(df, c)]
    categorical = [c for c in cols if c not in numeric]
    recs: list[dict] = []
    if len(numeric) == 1:
        recs += [{"type": "histogram", "x": numeric[0], "reason": "Distribution d'une variable numérique"}, {"type": "box", "y": numeric[0], "reason": "Dispersion et valeurs aberrantes"}]
    if len(numeric) >= 2:
        recs.append({"type": "scatter", "x": numeric[0], "y": numeric[1], "reason": "Relation entre deux variables numériques"})
    if categorical and numeric:
        recs += [{"type": "box", "x": categorical[0], "y": numeric[0], "reason": "Comparer une mesure entre catégories"}, {"type": "bar", "x": categorical[0], "y": numeric[0], "aggregation": "mean", "reason": "Comparer les moyennes par catégorie"}]
    if categorical and not numeric:
        recs.append({"type": "bar", "x": categorical[0], "aggregation": "count", "reason": "Fréquences par catégorie"})
    return recs[:6]


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

    if chart_type in {"bar", "line"}:
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
        out = out.sort_values("value", ascending=False).head(100) if chart_type == "bar" else out.head(500)
        data=[{"label": str(r[x]), "value": float(r["value"])} for _,r in out.iterrows() if pd.notna(r["value"])]
        return {"type":chart_type,"x":x,"y":y,"aggregation":aggregation,"data":data,"value_label":y_name,"title":f"{y_name} par {x}"}

    raise ValueError("Type de graphique non supporté")
