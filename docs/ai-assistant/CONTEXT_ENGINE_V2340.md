# DataVision AI v2.34.0 — Context Engine v4

## Objectif

Permettre à l'assistant d'agir sur les artefacts analytiques précédents sans
réinterpréter ou inventer leur identité.

## Résolution déterministe

Une référence comme « ce modèle » est résolue depuis `recent_artifacts`.
Le `model_id` est copié dans `AssistantContext.activeModelId`, puis l'intention
est spécialisée vers le moteur approprié : Model Registry, monitoring,
réentraînement, fairness, model risk ou XAI.

## Séparation résolution / autorisation

La résolution de référence n'accorde aucun droit. Le plan continue de traverser :

1. les contrats typés ;
2. le Tool Registry ;
3. la politique de risque ;
4. RBAC/RLS du host ;
5. la confirmation humaine si nécessaire.

## Human-in-the-loop

Les étapes `waiting_confirmation` exposent maintenant le `risk` validé par le
Tool Registry au frontend. La carte d'action affiche le risque et permet de
confirmer ou refuser. Le refus est envoyé au backend puis le turn run est clos
sans exécuter les étapes restantes.

## Anti-erreur sémantique

La seule présence du mot « production » ne déclenche pas de mutation de stage.
Une transition n'est produite que si un verbe d'action explicite est détecté
(`mettre`, `passer`, `promouvoir`, `déployer`, `publier`, `retirer`, etc.).
