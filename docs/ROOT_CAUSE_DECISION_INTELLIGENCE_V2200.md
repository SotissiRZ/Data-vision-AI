# DataVision v2.20.0 — Root Cause Analysis & Decision Intelligence

## 1. Objectif

Cette version couvre un écart important du CDC :

```text
mesurer un changement
        ↓
identifier où se trouve l'écart
        ↓
chercher les facteurs associés
        ↓
tester des scénarios
        ↓
aider la décision sans automatiser la décision humaine
```

## 2. Root Cause Analysis

Endpoint :

```text
POST /api/v1/datasets/{dataset_id}/root-cause
```

Entrées :
- `target` ;
- `comparison_column` ;
- `baseline_value` optionnel ;
- `current_value` optionnel ;
- `metric` ;
- `dimensions` ;
- `time_grain` ;
- `min_segment_size` ;
- `top_n`.

Si baseline/current sont absents, les deux dernières valeurs ordonnées de la
dimension de comparaison sont utilisées.

## 3. Décomposition d'une moyenne

Pour un segment `i` :

```text
w0 = poids baseline
w1 = poids actuel
m0 = moyenne baseline
m1 = moyenne actuelle

mix_effect  = 0.5 × (w1 - w0) × (m1 + m0)
rate_effect = 0.5 × (m1 - m0) × (w1 + w0)

contribution = mix_effect + rate_effect
```

La somme des contributions de tous les segments réconcilie l'écart global,
sous réserve qu'aucun segment ne soit retiré par `min_segment_size`.

Cette méthode décompose mathématiquement l'écart mais ne prouve pas la causalité.

## 4. Somme et count

Pour une somme :

```text
contribution(segment) =
sum_current(segment) - sum_baseline(segment)
```

Pour un count :

```text
contribution(segment) =
count_current(segment) - count_baseline(segment)
```

## 5. Distribution shift

Numérique :
- moyenne baseline/current ;
- delta ;
- déplacement standardisé.

Catégoriel :
- parts baseline/current ;
- Total Variation Distance ;
- modalités dont la part change le plus.

## 6. Evidence policy

Sortie :

```text
interpretation_policy =
descriptive_root_cause_candidates_not_causal_proof
```

Le moteur n'utilise jamais les termes « cause démontrée » ou « effet causal »
sur la seule base de cette analyse.

## 7. Decision Scenario Optimizer

Endpoint :

```text
POST /api/v1/datasets/models/{model_id}/optimize-scenarios
```

L'optimiseur utilise uniquement le pipeline sauvegardé.

Il ne réentraîne pas le modèle et ne modifie pas le dataset.

Contrôles acceptés :

```json
{
  "price": {"min": 10, "max": 20, "steps": 5},
  "channel": {"values": ["web", "store"]}
}
```

Limites :
- 5 variables contrôlables ;
- 5 000 combinaisons ;
- classement déterministe.

## 8. Assistant

Tool Registry :
- `run_root_cause_analysis` — read-only ;
- `optimize_decision_scenarios` — read-only.

Les deux passent par l'autorisation DataVision.

## 9. AI Analyst

L'intention `root_cause` a priorité sur la régression générique pour les
questions portant explicitement sur une hausse, une baisse ou les causes d'une
variation.

## 10. Limites

v2.20 ne revendique pas :
- inférence causale au sens do-calculus ;
- causal forests ;
- instrumental variables automatiques ;
- causal DAG discovery ;
- optimisation sous contraintes métier non linéaires ;
- prise de décision automatique.

Ces fonctions nécessiteraient des hypothèses causales explicites et des
contrats métier supplémentaires.
