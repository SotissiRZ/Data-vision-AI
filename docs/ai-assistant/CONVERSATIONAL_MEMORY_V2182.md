# DataVision v2.18.2 — Mémoire conversationnelle et coréférence

## Principe

Le contexte actif ne suffit pas pour comprendre :

```text
Et pourquoi ?
Fais pareil avec Profit.
Montre-moi ça en graphique.
Compare-le avec l'autre.
```

v2.18.2 ajoute un `Reference Resolver` entre l'Intent Resolver et le Planner.

```text
Message
  ↓
Intent déterministe
  ↓
Session Memory
  ↓
Reference Resolver
  ↓
Hybrid NLU si encore nécessaire
  ↓
Planner
```

## Mémoire courte

La mémoire conserve seulement des états sémantiques compacts :

- `last_intent` ;
- `last_entities` ;
- `recent_columns` ;
- `last_result_summary` ;
- `recent_intents` ;
- décisions.

La conversation brute n'est pas archivée par cette couche.

## Priorité de grounding

1. objet actuellement sélectionné ;
2. colonne explicitement nommée dans la nouvelle demande ;
3. colonnes récemment focalisées ;
4. dernières entités ;
5. clarification.

## Règle de sécurité

Une coréférence ambiguë ne déclenche jamais une action par supposition.

Si `l'autre` n'est pas déterminable, DataVision demande une précision.

## LLM

Le Model Gateway reste disponible après ce resolver. Les références simples
sont donc résolues localement sans coût ni latence de modèle.
