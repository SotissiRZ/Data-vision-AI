# DataVision v2.16.2 — Compréhension conversationnelle

## Problème corrigé

Avant v2.16.2 :

```text
question inconnue + dataset actif
        ↓
intent = analyze_dataset
        ↓
profile_dataset
inspect_missing_values
```

Cela provoquait des réponses absurdes pour des questions comme :

```text
Où sont les résultats ?
Tu as accès à internet ?
```

## Nouvelle règle

Un dataset actif est du **contexte**, jamais une instruction implicite.

```text
question
  ↓
Intent Resolver
  ├── show_results
  ├── capabilities
  ├── conversation
  ├── intents analytiques
  └── unknown → clarification
```

## Follow-up results

`show_results` lit le dernier `AgentTurnRun` de la même session et compose une
réponse depuis les sorties déterministes déjà calculées.

Aucun recalcul n'est nécessaire.

## Résultats visibles

Après profilage + missing-values, l'assistant peut maintenant répondre :

```text
Résultats : le dataset contient 700 lignes et 8 variables;
aucun doublon; aucune cellule manquante.
```

## Internet

La réponse `capabilities` ne prétend pas disposer d'un navigateur général.
DataVision peut utiliser :
- les moteurs internes ;
- les providers IA configurés ;
- les connecteurs externes autorisés.

La navigation Web générale n'est pas exposée comme outil DataVision dans cette version.
