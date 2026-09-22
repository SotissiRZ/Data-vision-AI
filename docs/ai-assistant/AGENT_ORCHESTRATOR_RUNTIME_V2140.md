# DataVision v2.14.0 — Agent Orchestrator Runtime

## Nouveau pipeline

```text
Message utilisateur
        ↓
Intent Resolver
        ↓
Planner Provider
        ↓
Plan Validator
        ↓
Tool Registry / Contracts
        ↓
Policy / RBAC-RLS
        ↓
Action Lifecycle
        ↓
Host Bridge / Engines
        ↓
Critic
        ↓
Recovery Policy
        ↓
Réponse texte + voix
```

## Intent Resolver

La première implémentation est déterministe et couvre :

```text
analyze_dataset
data_quality
compare_groups
visualize
predict_target
explain_model
geospatial_analysis
report
file_analysis
unknown
```

Cela fournit un fallback local et testable.

## Planner Provider

Le runtime définit une interface `PlannerProvider`.

Un futur provider LLM peut produire des plans, mais ceux-ci ne sont jamais
exécutés directement : ils passent toujours par les mêmes contrôles
déterministes.

Le patch fournit `DeterministicPlanner` pour les scénarios sûrs.

## Règle anti-invention

Le planner local refuse de deviner :

- une variable cible absente ;
- des groupes statistiques non indiqués ;
- des couches SIG non sélectionnées ;
- des colonnes de graphique non connues.

Il renvoie alors `needs_clarification`.

## Critic

Le critic vérifie actuellement :

- étapes échouées ;
- confirmations humaines en attente ;
- résultats vides.

Un Critic LLM futur pourra enrichir cette couche, sans remplacer les invariants.

## Recovery

Seules les erreurs reconnues comme transitoires peuvent être retentées une fois :

```text
timeout
temporarily unavailable
connection reset
rate limit
worker unavailable
```

Les erreurs de données, méthodes statistiques ou schémas ne sont pas rejouées
automatiquement.

## Endpoint principal

```text
POST /ai/assistant/turn
```

Exemple :

```json
{
  "session_id": "s_123",
  "message": "Analyse ce dataset",
  "context": {
    "workspaceId": "ws_1",
    "activeDatasetId": "ds_1",
    "recentEvents": []
  },
  "attachment_ids": [],
  "auto_execute_safe_steps": true
}
```

## Important

Le runtime v2.14 ne prétend pas qu'un fournisseur LLM est déjà branché.
Le provider fourni est déterministe.

Les outils ne deviennent réellement exécutables que lorsque les handlers du
vrai dépôt DataVision sont connectés via `DataVisionHostBridges`.
