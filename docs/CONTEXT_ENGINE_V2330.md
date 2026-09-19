# DataVision AI v2.33.0 — Context Engine v3

## Objectif
Permettre aux relances conversationnelles de viser un résultat analytique précis
sans perdre le contexte déterministe de la session.

## Artefacts mémorisés
- résultat statistique ;
- graphique ;
- modèle ;
- rapport ;
- explication XAI ;
- analyse de causes ;
- scénario de décision.

## Garde-fous
- maximum 12 artefacts récents ;
- invalidation lors d'un changement de dataset ;
- aucun dump brut illimité ;
- le LLM ne reçoit que les résumés gouvernés ;
- aucune comparaison numérique n'est inventée quand les métriques communes manquent.
