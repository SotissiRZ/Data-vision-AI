# DataVision v2.19.0 — XAI avancé & Model Benchmark

## Benchmark

Le service `benchmark_models` compare plusieurs familles de modèles avec une
même stratégie de préparation et de validation.

Séparation :

```text
60 % train
20 % validation
20 % test final
```

La cross-validation s'exécute sur le train uniquement.

Le classement s'effectue sur la validation. Le test final reste réservé au
modèle retenu par AutoML.

## Moteurs

Toujours disponibles :
- modèles scikit-learn historiques ;
- SVM.

Optionnels/détectés au runtime :
- XGBoost ;
- LightGBM ;
- CatBoost.

Une indisponibilité ou erreur d'un candidat est enregistrée dans la ligne de
benchmark sans interrompre les autres candidats.

## SHAP

DataVision utilise SHAP seulement si la bibliothèque est installée.

Priorité :
1. `TreeExplainer` pour les estimateurs arborescents compatibles ;
2. `PermutationExplainer` comme fallback borné.

Les variables transformées par le préprocesseur sont agrégées vers les
variables métier originales.

Le calcul est volontairement borné en nombre de lignes et de variables
transformées afin d'éviter un coût incontrôlé.

## Partial Dependence

Le PDP est calculé par inférences répétées du modèle sauvegardé sur un
échantillon gouverné.

Pour une variable numérique, DataVision utilise une grille de quantiles.
Pour une variable catégorielle, les modalités les plus fréquentes sont
évaluées.

## Calibration

Pour une classification binaire :
- ROC-AUC ;
- Brier score ;
- courbe de calibration ;
- Expected Calibration Error.

## Contre-factuels

La recherche contrefactuelle est déterministe et bornée :
- maximum 10 variables prioritaires ;
- candidats issus de quantiles/modalités observées ;
- une ou deux modifications ;
- classement par objectif puis distance.

Les sorties décrivent le comportement du modèle et non un effet causal garanti.

## Gouvernance

Les données utilisées par XAI sont chargées avec le même `load_dataframe`
que le reste de DataVision, donc après les contrôles d'accès et politiques
Enterprise applicables.

Le LLM n'effectue aucun calcul XAI.
