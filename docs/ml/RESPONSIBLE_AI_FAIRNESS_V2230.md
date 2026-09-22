# DataVision v2.23.0 — Responsible AI & Fairness

## Objectif

Ajouter une couche de diagnostic et de gouvernance des modèles sans transformer
un critère statistique en verdict automatique.

## Principes

1. les groupes d'audit sont sélectionnés explicitement ;
2. aucune caractéristique sensible n'est inférée depuis le nom d'une colonne ;
3. le holdout final est utilisé par défaut ;
4. les petits groupes sont exclus des comparaisons et signalés ;
5. les seuils de publication appartiennent à la politique de l'organisation ;
6. les métriques de groupe ne sont pas des preuves causales ;
7. la revue humaine/domain reste authoritative.

## Endpoints

```text
POST /api/v1/datasets/models/{model_id}/responsible-ai/fairness
POST /api/v1/datasets/models/{model_id}/responsible-ai/risk
POST /api/v1/datasets/models/{model_id}/responsible-ai/gate
POST /api/v1/datasets/models/{model_id}/responsible-ai/drift
```

## Classification

Une classe positive est requise pour les métriques binaires de parité. Pour une
classification binaire elle est automatiquement résolue si l'utilisateur la
laisse vide. Pour une classification multi-classe, l'utilisateur doit la
préciser pour obtenir les métriques one-vs-rest.

Le moteur produit :

- performance par groupe ;
- taux de sélection ;
- TPR / FPR ;
- precision / recall ;
- Brier et gap de calibration ;
- demographic parity difference ;
- selection rate ratio ;
- equal opportunity difference ;
- equalized odds difference.

## Régression

Le moteur produit :

- MAE ;
- RMSE ;
- mean error ;
- R² ;
- différences et ratios MAE/RMSE.

## Intersectionnalité

Jusqu'à trois colonnes peuvent être combinées en une vue intersectionnelle.
Le nombre de groupes affichés est borné. Les groupes sous le seuil d'effectif
sont explicitement enregistrés dans `excluded_groups`.

## Publication gate

Le report de fairness n'applique aucun seuil par défaut.

Le gate évalue uniquement les seuils fournis par l'organisation et expose :

```text
allowed
blockers
warnings
checks
policy
policy_source = organization_defined_thresholds
```

## Certification

Le Review Center conserve le Data Reliability Gate existant.

Pour un review de type `model`, si une Model Card contient un
`responsible_ai.publication_gate` persisté avec `allowed=false`, la certification
est refusée.

Un ancien modèle sans gate persisté n'est pas automatiquement bloqué afin de ne
pas casser les workflows historiques ; il peut cependant être signalé par le
Model Risk Assessment comme non revu.

## Population drift

La dérive compare :

- la représentation des groupes dans le dataset de référence ;
- la représentation dans le dataset actif/courant ;
- la performance par groupe sur le dataset courant si la cible est présente.

## Model Card

Lorsqu'une revue est persistée :

```text
model_card.responsible_ai.fairness
model_card.responsible_ai.risk
model_card.responsible_ai.publication_gate
```

Le résumé est également recopié dans `model_card.fairness` pour compatibilité.

## Limites explicites

v2.23 ne revendique pas :

- une définition universelle de la fairness ;
- une conformité juridique automatique ;
- une inférence automatique de caractéristiques protégées ;
- une correction automatique des disparités ;
- une preuve de discrimination ou de causalité ;
- une décision automatique de mise en production.
