# Forecasting, Anomaly Detection & XAI — v0.8

## Forecasting

Service : `backend/app/services/forecasting.py`.

Le moteur prépare une série triée et agrégée, crée une fenêtre de validation chronologique, compare les méthodes autorisées puis réajuste la méthode retenue sur l'historique complet. La sélection repose sur le RMSE de validation. Les intervalles 95 % sont des intervalles empiriques basés sur l'écart-type des résidus de validation ; ils sont étiquetés comme tels dans l'API.

## Anomalies

Service : `backend/app/services/anomaly_detection.py`.

- `iqr` : détection univariée par bornes Q1−1.5×IQR et Q3+1.5×IQR ;
- `robust_z` : médiane + MAD ;
- `isolation_forest` : modèle multivarié après imputation médiane et standardisation.

Le moteur retourne les index/valeurs et ne modifie pas le dataset.

## XAI

Service : `backend/app/services/xai.py`.

Les nouveaux artefacts modèles contiennent :

- `feature_baselines` ;
- `evaluation_indices` correspondant au test final.

Diagnostics :

- permutation importance ;
- matrice de confusion ;
- ROC/PR ;
- calibration binaire + Brier ;
- résidus en régression.

Explication locale : perturbation `one-feature-at-a-time` vers une baseline calculée sur train + validation. L'effet est la différence entre la sortie originale et la sortie après remplacement. Cette méthode n'est pas présentée comme SHAP.

## Confidentialité

Aucune donnée n'est envoyée à un service IA externe par ces modules. Les calculs s'exécutent localement dans le backend Python.
