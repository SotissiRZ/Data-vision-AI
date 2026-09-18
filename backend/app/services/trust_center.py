from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.semantic_layer import get_semantic_model, validate_semantic_model
from app.services.storage import get_lineage, get_meta


def trust_center(dataset_id: str, df: pd.DataFrame) -> dict[str, Any]:
    profile = profile_dataframe(df)
    quality = quality_report(df)
    semantic = get_semantic_model(dataset_id, df)
    lineage = get_lineage(dataset_id)
    meta = get_meta(dataset_id)

    data_score = int(max(0, min(100, quality.get("score", 0))))
    metric_count = len(semantic.get("metrics", []))
    certified = sum(1 for m in semantic.get("metrics", []) if m.get("certified"))
    described = sum(1 for m in semantic.get("metrics", []) if m.get("description"))
    semantic_validation = validate_semantic_model(dataset_id, df, semantic)
    base_semantics = int(semantic_validation.get("score", 20))
    hierarchy_bonus = min(5, 2 * len(semantic.get("hierarchies", [])))
    relation_bonus = min(5, 2 * len(semantic.get("relationships", []))) if semantic_validation.get("valid") else 0
    semantics_score = int(max(0, min(100, base_semantics + hierarchy_bonus + relation_bonus)))

    lineage_score = 100 if lineage else 55
    if len(lineage) == 1 and meta.get("operation", {}).get("type") == "upload":
        lineage_score = 82
    reproducibility_score = int(min(100, 72 + min(28, 7 * max(1, len(lineage)))))

    columns = profile.get("columns", [])
    possible_ids = []
    for c in columns:
        name = str(c.get("name", "")).lower()
        if name == "id" or name.endswith("_id") or any(t in name for t in ("uuid", "identifier", "identifiant")):
            possible_ids.append(c.get("name"))
    privacy_score = 88 if not possible_ids else max(45, 88 - 8 * len(possible_ids))

    overall = round(data_score * .35 + semantics_score * .25 + reproducibility_score * .25 + privacy_score * .15)
    checks = [
        {"area": "Données", "status": "pass" if data_score >= 80 else "warn" if data_score >= 60 else "fail", "score": data_score, "evidence": f"Score qualité {data_score}/100"},
        {"area": "Sémantique", "status": "pass" if semantics_score >= 80 and semantic_validation.get("valid") else "warn" if semantics_score >= 55 else "fail", "score": semantics_score, "evidence": f"{certified}/{metric_count or 0} métriques certifiées · {semantic_validation.get('relationships',0)} relation(s) · {semantic_validation.get('hierarchies',0)} hiérarchie(s)"},
        {"area": "Reproductibilité", "status": "pass" if reproducibility_score >= 80 else "warn", "score": reproducibility_score, "evidence": f"{len(lineage)} étape(s) de lineage disponible(s)"},
        {"area": "Confidentialité", "status": "pass" if privacy_score >= 80 else "warn", "score": privacy_score, "evidence": "Aucun identifiant évident" if not possible_ids else f"Colonnes potentiellement identifiantes: {', '.join(map(str, possible_ids[:5]))}"},
    ]
    warnings = []
    if quality.get("issues_count", 0): warnings.append(f"{quality['issues_count']} alerte(s) qualité à examiner.")
    if not certified: warnings.append("Aucune métrique métier n'est certifiée dans la couche sémantique.")
    if semantic_validation.get("errors"): warnings.append(f"Le modèle sémantique contient {len(semantic_validation['errors'])} erreur(s) de validation.")
    if possible_ids: warnings.append("Des colonnes potentiellement identifiantes doivent être revues avant partage externe.")
    return {
        "dataset_id": dataset_id,
        "root_id": meta.get("root_id") or dataset_id,
        "overall_score": overall,
        "grade": "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "E",
        "checks": checks,
        "warnings": warnings,
        "policy": {
            "numeric_results": "deterministic_engines_only",
            "raw_data_to_external_llm": False,
            "dataset_version": int(meta.get("version", 1)),
        },
    }
