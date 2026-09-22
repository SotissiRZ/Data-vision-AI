from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


def _numeric(df: pd.DataFrame, col: str | None) -> bool:
    return bool(col and col in df.columns and pd.api.types.is_numeric_dtype(df[col]))


def _datetime_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if series.dtype != object:
        return False
    sample = series.dropna().head(300)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() > 0.8)


def _is_identifier(df: pd.DataFrame, col: str) -> bool:
    name = str(col).lower()
    if re.search(r"(^id$|_id$|uuid|identifier|identifiant|record[_ -]?no|row[_ -]?id)", name):
        return True
    s = df[col]
    if len(s) > 20 and s.notna().sum() and s.nunique(dropna=True) / max(int(s.notna().sum()), 1) > 0.985:
        return bool(re.search(r"id|code|key|numero|number", name))
    return False


def _geo_pair(columns: list[str]) -> tuple[str | None, str | None]:
    lat = next((c for c in columns if re.search(r"(^|_)(lat|latitude)($|_)", c.lower())), None)
    lon = next((c for c in columns if re.search(r"(^|_)(lon|lng|long|longitude)($|_)", c.lower())), None)
    return lat, lon


def _recommendation(*, chart_type: str, score: int, reason: str, x: str | None = None, y: str | None = None,
                    color: str | None = None, size: str | None = None, aggregation: str | None = None,
                    rationale: list[str] | None = None) -> dict[str, Any]:
    confidence = "high" if score >= 85 else "medium" if score >= 70 else "exploratory"
    return {
        "type": chart_type,
        "score": int(max(0, min(100, score))),
        "confidence": confidence,
        "reason": reason,
        "rationale": rationale or [reason],
        "x": x,
        "y": y,
        "color": color,
        "size": size,
        **({"aggregation": aggregation} if aggregation else {}),
    }


def recommend_visualizations(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    """Rank visualization candidates from data semantics.

    The function remains deterministic so it can be used by both the UI and the
    assistant without requiring an LLM. Each recommendation carries a score,
    confidence level and rationale while preserving the historical ``reason``
    field for backwards compatibility.
    """
    requested = [c for c in columns if c in df.columns and not _is_identifier(df, c)]
    cols = requested or [c for c in df.columns if not _is_identifier(df, c)][:14]
    numeric = [c for c in cols if _numeric(df, c)]
    categorical = [c for c in cols if c not in numeric and not _datetime_like(df[c])]
    datetime_cols = [c for c in cols if _datetime_like(df[c])]
    lat, lon = _geo_pair(list(df.columns))

    recs: list[dict[str, Any]] = []
    if len(numeric) == 1:
        recs += [
            _recommendation(chart_type="histogram", score=92, x=numeric[0], reason="Distribution et fréquence d'une variable numérique"),
            _recommendation(chart_type="density", score=84, x=numeric[0], reason="Forme lissée de la distribution"),
            _recommendation(chart_type="box", score=82, y=numeric[0], reason="Dispersion, quartiles et valeurs aberrantes"),
        ]
    if len(numeric) >= 2:
        recs.append(_recommendation(chart_type="scatter", score=92, x=numeric[0], y=numeric[1], reason="Relation entre deux variables numériques"))
        recs.append(_recommendation(chart_type="heatmap", score=78, reason="Vue globale des corrélations entre variables numériques"))
    if len(numeric) >= 3:
        recs.append(_recommendation(chart_type="bubble", score=80, x=numeric[0], y=numeric[1], size=numeric[2], reason="Comparer trois dimensions numériques simultanément"))
        recs.append(_recommendation(chart_type="pca", score=73, reason="Réduire plusieurs dimensions numériques en projection 2D"))
        recs.append(_recommendation(chart_type="cluster", score=68, reason="Explorer des groupes naturels dans plusieurs variables numériques"))
    if categorical and numeric:
        cat = categorical[0]; num = numeric[0]
        cardinality = int(df[cat].nunique(dropna=True))
        recs += [
            _recommendation(chart_type="box", score=90, x=cat, y=num, reason="Comparer une mesure entre catégories"),
            _recommendation(chart_type="violin", score=84, x=cat, y=num, reason="Comparer la forme complète des distributions par catégorie"),
            _recommendation(chart_type="bar", score=88, x=cat, y=num, aggregation="mean", reason="Comparer les moyennes par catégorie"),
        ]
        if cardinality <= 50:
            recs.append(_recommendation(chart_type="treemap", score=76, x=cat, y=num, aggregation="sum", reason="Comparer la contribution relative des catégories"))
    if len(categorical) >= 2:
        recs.append(_recommendation(chart_type="sankey", score=72, x=categorical[0], y=categorical[1], reason="Visualiser les flux entre deux dimensions catégorielles"))
    if categorical and not numeric:
        recs.append(_recommendation(chart_type="bar", score=90, x=categorical[0], aggregation="count", reason="Fréquences par catégorie"))
    if datetime_cols and numeric:
        recs.append(_recommendation(chart_type="line", score=96, x=datetime_cols[0], y=numeric[0], aggregation="mean", reason="Évolution temporelle de la mesure"))
        recs.append(_recommendation(chart_type="area", score=79, x=datetime_cols[0], y=numeric[0], aggregation="sum", reason="Volume cumulé ou contribution au fil du temps"))
    if lat and lon and _numeric(df, lat) and _numeric(df, lon):
        label = categorical[0] if categorical else None
        recs.append(_recommendation(chart_type="map", score=94, x=lon, y=lat, color=label, reason="Les colonnes latitude/longitude permettent une vue géographique"))

    # Keep the strongest unique chart/spec combination and return a stable order.
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for rec in recs:
        key = (rec.get("type"), rec.get("x"), rec.get("y"), rec.get("size"), rec.get("aggregation"))
        if key not in unique or rec["score"] > unique[key]["score"]:
            unique[key] = rec
    return sorted(unique.values(), key=lambda r: (-r["score"], str(r["type"])))[:12]


def _aggregate(df: pd.DataFrame, x: str, y: str | None, aggregation: str) -> tuple[pd.DataFrame, str]:
    work = df[[x] + ([y] if y else [])].copy()
    if aggregation == "count" or not y:
        out = work.groupby(x, dropna=False).size().reset_index(name="value")
        return out, "count"
    if not _numeric(df, y):
        raise ValueError("Y doit être numérique pour cette agrégation")
    if aggregation not in {"mean", "sum", "median", "min", "max"}:
        raise ValueError("Agrégation supportée: mean, sum, median, min, max, count")
    out = work.groupby(x, dropna=False)[y].agg(aggregation).reset_index(name="value")
    return out, f"{aggregation}({y})"


def _numeric_matrix(df: pd.DataFrame, columns: list[str] | None, *, max_columns: int = 10) -> tuple[pd.DataFrame, list[str]]:
    candidates = [c for c in (columns or list(df.columns)) if c in df.columns and _numeric(df, c) and not _is_identifier(df, c)]
    candidates = candidates[:max_columns]
    if len(candidates) < 2:
        raise ValueError("Au moins deux variables numériques sont nécessaires")
    work = df[candidates].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < 3:
        raise ValueError("Au moins trois observations complètes sont nécessaires")
    return work, candidates


def build_visualization(df: pd.DataFrame, *, chart_type: str, x: str | None = None, y: str | None = None,
                        color: str | None = None, size: str | None = None, facet: str | None = None,
                        aggregation: str = "none", bins: int = 20, columns: list[str] | None = None,
                        cluster_k: int = 3, max_points: int = 3000) -> dict:
    chart_type = chart_type.lower().strip()
    aliases = {"boxplot": "box", "correlation_matrix": "heatmap", "time_series": "line", "map_points": "map"}
    chart_type = aliases.get(chart_type, chart_type)
    for c in [x, y, color, size, facet]:
        if c and c not in df.columns:
            raise ValueError(f"Colonne inconnue: {c}")
    if chart_type == "auto":
        recs = recommend_visualizations(df, [c for c in [x, y, color, size] if c])
        if not recs:
            raise ValueError("Impossible de recommander un graphique avec cette sélection")
        first = recs[0]
        chart_type = first["type"]
        x = first.get("x", x); y = first.get("y", y); color = first.get("color", color); size = first.get("size", size)
        aggregation = first.get("aggregation", aggregation)

    common = {"color": color, "size": size, "facet": facet}

    if chart_type == "histogram":
        if not x or not _numeric(df, x):
            raise ValueError("L'histogramme nécessite une variable X numérique")
        s = pd.to_numeric(df[x], errors="coerce").dropna()
        bins = max(5, min(int(bins), 80))
        counts, edges = np.histogram(s, bins=bins)
        data = [{"from": float(edges[i]), "to": float(edges[i+1]), "count": int(counts[i])} for i in range(len(counts))]
        return {"type": "histogram", "x": x, "data": data, "n": int(len(s)), "title": f"Distribution de {x}", **common}

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
            kde = stats.gaussian_kde(s.to_numpy(dtype=float)); dens = kde(grid)
        except Exception:
            counts, edges = np.histogram(s, bins=max(10, min(40, int(np.sqrt(len(s))))), density=True)
            mids = (edges[:-1] + edges[1:]) / 2; dens = np.interp(grid, mids, counts)
        data = [{"x": float(a), "density": float(b)} for a, b in zip(grid, dens)]
        return {"type": "density", "x": x, "data": data, "n": int(len(s)), "title": f"Densité de {x}", **common}

    if chart_type == "heatmap":
        numeric_cols = [c for c in (columns or list(df.columns)) if _numeric(df, c) and not _is_identifier(df, c)][:12]
        if len(numeric_cols) < 2:
            raise ValueError("La heatmap nécessite au moins deux variables numériques")
        corr = df[numeric_cols].corr(method="pearson", min_periods=2)
        matrix = []
        for row in numeric_cols:
            item = {"variable": row}
            for col in numeric_cols:
                value = corr.loc[row, col]; item[col] = None if pd.isna(value) else float(value)
            matrix.append(item)
        return {"type": "heatmap", "columns": numeric_cols, "data": matrix, "title": "Matrice de corrélation — Pearson", **common}

    if chart_type in {"scatter", "bubble", "map"}:
        if not x or not y or not _numeric(df, x) or not _numeric(df, y):
            label = "carte" if chart_type == "map" else "nuage de points"
            raise ValueError(f"Le {label} nécessite X et Y numériques")
        if chart_type == "bubble" and (not size or not _numeric(df, size)):
            raise ValueError("Le bubble chart nécessite une variable de taille numérique")
        cols = [x, y] + ([color] if color else []) + ([size] if size else [])
        cols = list(dict.fromkeys(cols))
        work = df[cols].copy(); work[x] = pd.to_numeric(work[x], errors="coerce"); work[y] = pd.to_numeric(work[y], errors="coerce")
        if size: work[size] = pd.to_numeric(work[size], errors="coerce")
        work = work.dropna(subset=[x, y] + ([size] if size else []))
        if len(work) > max_points: work = work.sample(max_points, random_state=42)
        smin = float(work[size].min()) if size and len(work) else 0.0; smax = float(work[size].max()) if size and len(work) else 1.0
        data = []
        for _, r in work.iterrows():
            item: dict[str, Any] = {"x": float(r[x]), "y": float(r[y])}
            if color: item["color"] = str(r[color])
            if size:
                raw = float(r[size]); item["size"] = raw; item["radius"] = 4.0 + 14.0 * ((raw - smin) / max(smax - smin, 1e-12))
            data.append(item)
        title = f"{y} selon {x}"
        if chart_type == "map": title = f"Points géographiques — {y} / {x}"
        if chart_type == "bubble": title = f"{y} selon {x} · taille {size}"
        return {"type": chart_type, "x": x, "y": y, "color": color, "size": size, "data": data, "n": len(data), "title": title, "coordinate_system": "geographic" if chart_type == "map" else "cartesian", "facet": facet}

    if chart_type == "box":
        value = y or x
        if not value or not _numeric(df, value):
            raise ValueError("Le boxplot nécessite une variable numérique")
        group = x if y else None
        if group and group == value: group = None
        levels = df[group].dropna().astype(str).value_counts().head(30).index.tolist() if group else ["Toutes les observations"]
        data=[]
        for level in levels:
            s = pd.to_numeric(df.loc[df[group].astype(str)==level, value], errors="coerce").dropna() if group else pd.to_numeric(df[value], errors="coerce").dropna()
            if s.empty: continue
            q1, med, q3 = s.quantile([.25,.5,.75]); iqr=q3-q1; lo=q1-1.5*iqr; hi=q3+1.5*iqr
            data.append({"group": level, "min": float(s.min()), "q1": float(q1), "median": float(med), "q3": float(q3), "max": float(s.max()), "whisker_low": float(s[s>=lo].min()), "whisker_high": float(s[s<=hi].max()), "n": int(len(s))})
        return {"type":"box","x":group,"y":value,"data":data,"title":f"Distribution de {value}" + (f" par {group}" if group else ""), **common}

    if chart_type == "violin":
        value = y or x
        group = x if y else None
        if not value or not _numeric(df, value):
            raise ValueError("Le violin plot nécessite une variable numérique")
        levels = df[group].dropna().astype(str).value_counts().head(18).index.tolist() if group else ["Toutes les observations"]
        groups: list[dict[str, Any]] = []
        for level in levels:
            s = pd.to_numeric(df.loc[df[group].astype(str)==level, value], errors="coerce").dropna() if group else pd.to_numeric(df[value], errors="coerce").dropna()
            if len(s) < 3: continue
            lo, hi = float(s.min()), float(s.max())
            if np.isclose(lo, hi):
                density = [{"value": lo, "density": 1.0}]
            else:
                grid = np.linspace(lo, hi, 48)
                try:
                    kde = stats.gaussian_kde(s.to_numpy(dtype=float)); dens = kde(grid); peak = max(float(np.max(dens)), 1e-12)
                    density = [{"value": float(v), "density": float(d/peak)} for v,d in zip(grid,dens)]
                except Exception:
                    counts, edges = np.histogram(s, bins=20); mids=(edges[:-1]+edges[1:])/2; peak=max(float(np.max(counts)),1.0)
                    density=[{"value":float(v),"density":float(d/peak)} for v,d in zip(mids,counts)]
            q1, med, q3 = s.quantile([.25,.5,.75])
            groups.append({"group": level, "density": density, "q1": float(q1), "median": float(med), "q3": float(q3), "n": int(len(s))})
        return {"type":"violin","x":group,"y":value,"data":groups,"title":f"Distribution de {value}" + (f" par {group}" if group else ""), **common}

    if chart_type in {"bar", "line", "area", "treemap"}:
        if not x: raise ValueError("Sélectionnez une variable X")
        effective_agg = aggregation
        if chart_type == "treemap" and effective_agg == "none": effective_agg = "sum" if y else "count"
        if chart_type in {"bar", "line", "area"} and effective_agg == "none" and y: effective_agg = "mean"
        out, y_name = _aggregate(df, x, y, effective_agg)
        if chart_type in {"bar", "treemap"}:
            out = out.sort_values("value", ascending=False).head(100 if chart_type == "bar" else 40)
        else:
            parsed_dates = pd.to_datetime(out[x], errors="coerce", format="mixed")
            if parsed_dates.notna().mean() > 0.8: out = out.assign(__sort=parsed_dates).sort_values("__sort").drop(columns="__sort")
            elif pd.api.types.is_numeric_dtype(out[x]): out = out.sort_values(x)
            out = out.head(500)
        data=[{"label": str(r[x]), "value": float(r["value"])} for _,r in out.iterrows() if pd.notna(r["value"])]
        return {"type":chart_type,"x":x,"y":y,"aggregation":effective_agg,"data":data,"value_label":y_name,"title":f"{y_name} par {x}", **common}

    if chart_type == "sankey":
        if not x or not y: raise ValueError("Le Sankey nécessite une source X et une destination Y")
        work_cols = [x, y] + ([size] if size else [])
        work = df[work_cols].dropna(subset=[x,y]).copy()
        if size:
            if not _numeric(df, size): raise ValueError("La pondération du Sankey doit être numérique")
            work[size] = pd.to_numeric(work[size], errors="coerce").fillna(0)
            links = work.groupby([x,y], dropna=False)[size].sum().reset_index(name="value")
        else:
            links = work.groupby([x,y], dropna=False).size().reset_index(name="value")
        links = links.sort_values("value", ascending=False).head(80)
        data=[{"source":str(r[x]),"target":str(r[y]),"value":float(r["value"])} for _,r in links.iterrows() if float(r["value"])>0]
        nodes=sorted(set([d["source"] for d in data]+[d["target"] for d in data]))
        return {"type":"sankey","x":x,"y":y,"size":size,"nodes":[{"id":n} for n in nodes],"data":data,"title":f"Flux {x} → {y}","facet":facet}

    if chart_type == "pca":
        work, features = _numeric_matrix(df, columns, max_columns=12)
        if len(work) > max_points: work = work.sample(max_points, random_state=42)
        scaled = StandardScaler().fit_transform(work.to_numpy(dtype=float))
        pca = PCA(n_components=2, random_state=42); coords = pca.fit_transform(scaled)
        data=[{"x":float(a),"y":float(b),"row":str(idx)} for idx,(a,b) in zip(work.index,coords)]
        loads=[{"feature":f,"pc1":float(pca.components_[0,i]),"pc2":float(pca.components_[1,i])} for i,f in enumerate(features)]
        return {"type":"pca","x":"PC1","y":"PC2","features":features,"data":data,"loadings":loads,"explained_variance_pct":[float(v*100) for v in pca.explained_variance_ratio_],"title":"Projection PCA — PC1 / PC2", **common}

    if chart_type == "cluster":
        work, features = _numeric_matrix(df, columns, max_columns=10)
        if len(work) > max_points: work = work.sample(max_points, random_state=42)
        cluster_k = max(2, min(int(cluster_k), min(10, len(work)-1)))
        scaled = StandardScaler().fit_transform(work.to_numpy(dtype=float))
        labels = KMeans(n_clusters=cluster_k, random_state=42, n_init=10).fit_predict(scaled)
        coords = PCA(n_components=2, random_state=42).fit_transform(scaled)
        data=[{"x":float(a),"y":float(b),"cluster":int(c),"row":str(idx)} for idx,(a,b),c in zip(work.index,coords,labels)]
        counts=[int(np.sum(labels==i)) for i in range(cluster_k)]
        return {"type":"cluster","x":"PC1","y":"PC2","features":features,"k":cluster_k,"counts":counts,"data":data,"title":f"Projection des clusters · K={cluster_k}", **common}

    raise ValueError("Type de graphique non supporté")


_CHART_ALIASES: list[tuple[str, str]] = [
    (r"\b(histogramme|histogram)\b", "histogram"), (r"\b(densit[eé]|density)\b", "density"),
    (r"\b(nuage|scatter)\b", "scatter"), (r"\b(boxplot|bo[iî]te)\b", "box"),
    (r"\b(violon|violin)\b", "violin"), (r"\b(bulle|bubble)\b", "bubble"),
    (r"\b(treemap|carte arborescente)\b", "treemap"), (r"\b(sankey|flux)\b", "sankey"),
    (r"\b(carte|map)\b", "map"), (r"\b(pca|acp)\b", "pca"), (r"\b(cluster|clustering)\b", "cluster"),
    (r"\b(heatmap|corr[eé]lation)\b", "heatmap"), (r"\b(aire|area)\b", "area"),
    (r"\b(courbe|ligne|line)\b", "line"), (r"\b(barres?|bar chart|bar)\b", "bar"),
]


def _column_from_instruction(instruction: str, df: pd.DataFrame, keys: tuple[str, ...]) -> str | None:
    lower = instruction.lower()
    for key in keys:
        m = re.search(rf"\b{re.escape(key)}\s*[:=]\s*[\"']?([^,;\n\"']+)", lower, flags=re.I)
        if m:
            raw = m.group(1).strip()
            for col in df.columns:
                if raw == str(col).lower():
                    return str(col)
    return None


def edit_visualization(df: pd.DataFrame, current: dict[str, Any], instruction: str) -> dict[str, Any]:
    """Apply a deterministic natural-language edit to an existing visualization."""
    if not instruction or not instruction.strip():
        raise ValueError("Instruction d'édition vide")
    spec = {
        "chart_type": current.get("type", "auto"), "x": current.get("x"), "y": current.get("y"),
        "color": current.get("color"), "size": current.get("size"), "facet": current.get("facet"),
        "aggregation": current.get("aggregation", "none"), "columns": current.get("features") or current.get("columns"),
        "cluster_k": current.get("k", 3),
    }
    text = instruction.lower().strip(); changes: list[dict[str, Any]] = []
    for pattern, chart in _CHART_ALIASES:
        if re.search(pattern, text, flags=re.I) and chart != spec["chart_type"]:
            changes.append({"field":"type","from":spec["chart_type"],"to":chart}); spec["chart_type"] = chart; break
    for field, keys in [("x",("x","axe x")), ("y",("y","axe y")), ("color",("couleur","color")), ("size",("taille","size"))]:
        col = _column_from_instruction(instruction, df, keys)
        if col and col != spec.get(field): changes.append({"field":field,"from":spec.get(field),"to":col}); spec[field]=col
    # Common analytical phrasing: “moyenne de CA par Région”.
    by_match = re.search(r"\bpar\s+([^,;\n]+)", instruction, flags=re.I)
    if by_match:
        raw = by_match.group(1).strip().strip(" \"'")
        for col in df.columns:
            if raw.lower().startswith(str(col).lower()) and str(col) != spec.get("x"):
                changes.append({"field":"x","from":spec.get("x"),"to":str(col)}); spec["x"] = str(col); break
    of_match = re.search(r"\b(?:de|du|des)\s+([^,;\n]+?)\s+par\b", instruction, flags=re.I)
    if of_match:
        raw = of_match.group(1).strip().strip(" \"'")
        for col in df.columns:
            if raw.lower() == str(col).lower() and str(col) != spec.get("y"):
                changes.append({"field":"y","from":spec.get("y"),"to":str(col)}); spec["y"] = str(col); break
    aggregations = {"moyenne":"mean","mean":"mean","somme":"sum","sum":"sum","médiane":"median","mediane":"median","median":"median","compte":"count","count":"count","minimum":"min","maximum":"max"}
    for token, agg in aggregations.items():
        if token in text and agg != spec.get("aggregation"):
            changes.append({"field":"aggregation","from":spec.get("aggregation"),"to":agg}); spec["aggregation"] = agg; break
    km = re.search(r"\bk\s*[:=]?\s*(\d{1,2})\b", text)
    if km:
        k=max(2,min(10,int(km.group(1)))); changes.append({"field":"k","from":spec.get("cluster_k"),"to":k}); spec["cluster_k"] = k
    title = current.get("title")
    tm = re.search(r"(?:titre|title)\s*[:=]\s*[\"']?([^\n\"']+)", instruction, flags=re.I)
    if tm: title=tm.group(1).strip(); changes.append({"field":"title","to":title})
    rebuilt = build_visualization(df, **spec)
    if title: rebuilt["title"] = title
    return {"visualization": rebuilt, "changes": changes, "instruction": instruction, "applied": bool(changes)}


def build_visualization_composition(df: pd.DataFrame, *, columns: list[str] | None = None, intent: str = "overview", max_views: int = 4) -> dict[str, Any]:
    """Build a deterministic multi-view analytical composition."""
    max_views = max(2, min(int(max_views), 6))
    recs = recommend_visualizations(df, columns or [])
    views: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for rec in recs:
        if rec["type"] in seen_types: continue
        try:
            viz = build_visualization(
                df, chart_type=rec["type"], x=rec.get("x"), y=rec.get("y"), color=rec.get("color"),
                size=rec.get("size"), aggregation=rec.get("aggregation", "none"), columns=columns,
            )
        except (ValueError, TypeError):
            continue
        views.append({"score":rec.get("score"),"confidence":rec.get("confidence"),"reason":rec.get("reason"),"visualization":viz})
        seen_types.add(rec["type"])
        if len(views) >= max_views: break
    if not views:
        raise ValueError("Impossible de composer des visualisations avec ce dataset")
    layout = "2x2" if len(views) >= 4 else "2-column" if len(views) > 1 else "single"
    return {"type":"composition","intent":intent,"layout":layout,"view_count":len(views),"views":views,"title":"Composition analytique automatique"}
