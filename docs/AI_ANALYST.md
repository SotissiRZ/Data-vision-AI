# AI Analyst — v0.9

## Objectif

Le module AI Analyst orchestre les moteurs analytiques existants à partir d'une demande en langage naturel. Il ne remplace pas les moteurs statistiques et ne calcule aucun résultat numérique lui-même.

## Flux

```text
Question utilisateur
  ↓
Intent Router
  ↓
Dataset inspection
  ↓
Analytic Plan
  ↓
Tool Registry
  ↓
Python / Statistics / ML / Forecasting
  ↓
Computed Results
  ↓
Critic Validation
  ↓
Findings + Provenance + Technical Artifacts
```

## Intentions v0.9

- `overview`
- `quality`
- `correlation`
- `regression`
- `anova`
- `clustering`
- `automl`
- `forecast`
- `anomaly`
- `decision`

## Sélection de variables

Le routeur utilise dans cet ordre :

1. paramètres explicites envoyés par l'interface ;
2. colonnes mentionnées textuellement dans la question ;
3. heuristiques basées sur le type des colonnes.

Les identifiants quasi uniques sont évités lorsque possible dans les sélections automatiques.

## Critic

Le Critic contrôle :

- l'état de chaque outil ;
- la provenance des constats ;
- la règle `deterministic_tools_only`.

Il ne masque pas les erreurs : un outil en échec apparaît dans `executions` et dans les artefacts techniques.

## Couche LLM

Aucun fournisseur LLM n'est requis pour v0.9. Le champ de configuration `AI_PROVIDER` est conservé pour une future Model Gateway. L'intégration fournisseur est distincte du moteur de calcul et ne devra jamais recevoir automatiquement des données privées sans configuration explicite.
