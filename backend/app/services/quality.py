from __future__ import annotations

import pandas as pd


def quality_report(df: pd.DataFrame) -> dict:
    issues: list[dict] = []
    n = max(len(df), 1)

    dup = int(df.duplicated().sum())
    if dup:
        issues.append({
            "code": "duplicates",
            "severity": "high" if dup / n > 0.05 else "medium",
            "description": f"{dup} ligne(s) dupliquée(s)",
            "impact": "Peut biaiser les statistiques et l'apprentissage.",
            "recommendation": "Vérifier la clé métier puis dédupliquer sur une copie versionnée.",
        })

    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        if missing:
            pct = missing / n
            issues.append({
                "code": "missing_values",
                "column": str(col),
                "severity": "high" if pct >= 0.30 else "medium" if pct >= 0.05 else "low",
                "description": f"{missing} valeur(s) manquante(s) ({pct:.1%})",
                "impact": "Peut invalider certains calculs ou réduire la qualité du modèle.",
                "recommendation": "Choisir suppression, imputation ou conservation selon le mécanisme de manque.",
            })

        if s.nunique(dropna=True) <= 1:
            issues.append({
                "code": "constant_column",
                "column": str(col),
                "severity": "medium",
                "description": "Colonne constante ou vide.",
                "impact": "N'apporte pas d'information pour l'analyse/modélisation.",
                "recommendation": "Exclure de la modélisation sauf justification métier.",
            })

        if pd.api.types.is_numeric_dtype(s):
            clean = s.dropna()
            if len(clean) >= 8:
                q1, q3 = clean.quantile([0.25, 0.75])
                iqr = q3 - q1
                if iqr > 0:
                    mask = (clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)
                    outliers = int(mask.sum())
                    if outliers:
                        pct = outliers / len(clean)
                        issues.append({
                            "code": "iqr_outliers",
                            "column": str(col),
                            "severity": "medium" if pct > 0.05 else "low",
                            "description": f"{outliers} valeur(s) aberrante(s) selon la règle IQR.",
                            "impact": "Peut influencer moyennes, régressions et certains modèles.",
                            "recommendation": "Inspecter avant toute suppression; préférer une transformation ou une méthode robuste si pertinent.",
                        })

    score = max(0, 100 - sum({"low": 2, "medium": 6, "high": 12}[i["severity"]] for i in issues))
    return {"score": score, "issues_count": len(issues), "issues": issues}
