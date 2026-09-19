# DataVision v2.28.0 — AI Analyst Performance & Streaming

## Architecture

```text
POST analyze/run
      ↓
ai_analysis_runs
      ↓
thread daemon borné (max 4)
      ↓
analyze_dataset(progress_callback, cancel_check)
      ↓
SSE events
      ↓
UI progression
```

## Cache

La clé SHA256 est dérivée de :

- version du runtime ;
- dataset id/version ;
- révision sémantique ;
- requête analytique normalisée.

Le cache ne contourne pas le contexte tenant : une exécution cached est créée
dans le contexte actif et les accès au run sont contrôlés par workspace/user.

## Déduplication

Les requêtes identiques en cours sont dédupliquées par `cache_key` et contexte
workspace/user.

## Annulation

La cancellation est volontairement coopérative. `analyze_dataset` vérifie
`cancel_check` avant et après les outils. Les bibliothèques statistiques ne
sont pas interrompues de force au milieu d'une opération native.

## Streaming

Le flux SSE émet seulement lorsque l'état change et se termine après :

- completed ;
- failed ;
- cancelled.

Le résultat complet n'est inclus que dans l'événement final `completed`.
