from __future__ import annotations

from typing import Any
import math

import numpy as np
import pandas as pd

from app.services.decision import decision_support
from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.visualization import recommend_visualizations


def _is_identifier(name: str, unique: int, rows: int) -> bool:
    n = name.lower()
    by_name = n in {"id", "index", "row", "record", "patient_id", "customer_id", "user_id"} or n.endswith("_id")
    high_unique = rows > 20 and unique / max(rows, 1) > 0.98
    id_token = any(token in n for token in ("uuid", "identifier", "identifiant", "code", "key", "numero", "number", "record_no", "record_number"))
    return by_name or (high_unique and id_token)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def dashboard_overview(df: pd.DataFrame) -> dict[str, Any]:
    profile = profile_dataframe(df)
    quality = quality_report(df)
    decision = decision_support(profile, quality)
    rows = int(profile["rows"])
    columns = profile.get("columns", [])

    missing = [
        {"name": c["name"], "missing_pct": float(c.get("missing_pct") or 0), "missing": int(c.get("missing") or 0)}
        for c in columns if float(c.get("missing_pct") or 0) > 0
    ]
    missing.sort(key=lambda x: x["missing_pct"], reverse=True)

    type_counts: dict[str, int] = {}
    meaningful_numeric: list[str] = []
    for c in columns:
        dtype = str(c.get("dtype", "")).lower()
        if any(k in dtype for k in ["int", "float", "double", "decimal"]):
            label = "Numérique"
            if not _is_identifier(str(c["name"]), int(c.get("unique") or 0), rows):
                meaningful_numeric.append(str(c["name"]))
        elif any(k in dtype for k in ["date", "time"]):
            label = "Date / heure"
        elif "bool" in dtype:
            label = "Booléen"
        elif "category" in dtype:
            label = "Catégorie"
        else:
            label = "Texte / autre"
        type_counts[label] = type_counts.get(label, 0) + 1

    correlation_pairs: list[dict[str, Any]] = []
    if len(meaningful_numeric) >= 2:
        corr_cols = meaningful_numeric[:12]
        corr = df[corr_cols].apply(pd.to_numeric, errors="coerce").corr(method="pearson", min_periods=3)
        for i, a in enumerate(corr_cols):
            for b in corr_cols[i + 1:]:
                value = _safe_float(corr.loc[a, b])
                if value is not None:
                    correlation_pairs.append({"x": a, "y": b, "coefficient": value, "abs": abs(value)})
        correlation_pairs.sort(key=lambda x: x["abs"], reverse=True)

    skewed: list[dict[str, Any]] = []
    for col in meaningful_numeric[:20]:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) >= 8 and s.nunique() > 2:
            value = _safe_float(s.skew())
            if value is not None and abs(value) >= 1:
                skewed.append({"column": col, "skewness": value, "magnitude": abs(value)})
    skewed.sort(key=lambda x: x["magnitude"], reverse=True)

    insights: list[dict[str, Any]] = []
    if quality["score"] < 70:
        insights.append({"severity": "critical", "title": "Qualité à traiter en priorité", "statement": f"Le score qualité est de {quality['score']}/100 avec {quality['issues_count']} alerte(s).", "action": "Ouvrir Qualité des données"})
    elif quality["issues_count"]:
        insights.append({"severity": "high", "title": "Contrôles qualité recommandés", "statement": f"{quality['issues_count']} anomalie(s) de qualité ont été détectées avant modélisation.", "action": "Ouvrir Qualité des données"})
    else:
        insights.append({"severity": "info", "title": "Qualité de base satisfaisante", "statement": "Aucune anomalie n'a été détectée par les règles de qualité actuellement actives.", "action": "Poursuivre l'exploration"})

    if missing:
        top = missing[0]
        insights.append({"severity": "high" if top["missing_pct"] >= 30 else "medium", "title": "Valeurs manquantes", "statement": f"{top['name']} contient {top['missing_pct']:.1f}% de valeurs manquantes.", "action": "Ouvrir Préparation"})
    if correlation_pairs:
        top = correlation_pairs[0]
        if top["abs"] >= 0.6:
            insights.append({"severity": "info", "title": "Relation forte détectée", "statement": f"{top['x']} et {top['y']} ont une corrélation de {top['coefficient']:.3f}.", "action": "Ouvrir Tests & corrélations"})
    if skewed:
        top = skewed[0]
        insights.append({"severity": "medium", "title": "Distribution asymétrique", "statement": f"{top['column']} présente une asymétrie marquée (skewness {top['skewness']:.2f}).", "action": "Ouvrir Statistiques descriptives"})
    if rows < 100:
        insights.append({"severity": "high", "title": "Petit échantillon", "statement": f"Le dataset contient {rows} lignes; les performances ML doivent être interprétées avec prudence.", "action": "Adapter la validation"})

    recommended = recommend_visualizations(df, list(df.columns[:12]))

    return {
        "metrics": {
            "rows": rows,
            "columns": int(profile.get("columns_count") or 0),
            "quality_score": int(quality.get("score") or 0),
            "issues": int(quality.get("issues_count") or 0),
            "duplicates": int(profile.get("duplicates") or 0),
            "missing_cells": int(df.isna().sum().sum()),
        },
        "missing": missing[:12],
        "types": [{"type": k, "count": v} for k, v in type_counts.items()],
        "strong_correlations": correlation_pairs[:10],
        "skewed": skewed[:8],
        "insights": insights[:8],
        "recommended_visualizations": recommended[:6],
        "decision_actions": decision.get("actions", [])[:5],
        "calculation_policy": "deterministic_engines_only",
    }
