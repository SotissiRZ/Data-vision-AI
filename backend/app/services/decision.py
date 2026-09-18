from __future__ import annotations


def decision_support(profile: dict, quality: dict) -> dict:
    actions = []
    if quality["score"] < 70:
        actions.append({"priority": "critical", "action": "Traiter les problèmes de qualité avant toute modélisation.", "evidence": f"Score qualité: {quality['score']}/100"})
    elif quality["issues_count"]:
        actions.append({"priority": "high", "action": "Revoir les anomalies qualité avant la phase de modèle.", "evidence": f"{quality['issues_count']} problème(s) détecté(s)"})
    else:
        actions.append({"priority": "medium", "action": "Les contrôles de base sont satisfaisants; poursuivre l'exploration et la sélection de la cible.", "evidence": "Aucun problème détecté par les règles de base."})

    if profile["rows"] < 100:
        actions.append({"priority": "high", "action": "Interpréter prudemment les modèles prédictifs et privilégier une validation adaptée au petit échantillon.", "evidence": f"{profile['rows']} lignes"})
    if profile["duplicates"]:
        actions.append({"priority": "high", "action": "Définir la clé métier avant déduplication.", "evidence": f"{profile['duplicates']} doublon(s)"})
    return {"status": "decision_support", "automatic_decision": False, "actions": actions}
