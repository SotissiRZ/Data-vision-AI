# Forecasting & Anomaly Detection — v2.53.0

## Forecasting

Le moteur utilise un backtesting **rolling-origin** sur plusieurs fenêtres chronologiques. Les modèles candidats sont évalués hors-échantillon avec MAE, RMSE, MAPE, sMAPE et biais. La sélection est gouvernée par une métrique explicite.

Les intervalles de prévision sont empiriques : leurs bornes proviennent des quantiles des résidus accumulés pendant le backtesting. Ils ne sont donc jamais calculés par le LLM.

Les séries irrégulières sont détectées. Par défaut, DataVision bloque le calcul si des périodes manquent ; l’utilisateur doit sélectionner explicitement une stratégie de régularisation.

## Anomalies

Le moteur conserve IQR, z-score robuste et Isolation Forest. Le nouveau mode `consensus` exige au moins deux votes sur trois et expose le détail d’accord entre méthodes.

## Gouvernance

L’Assistant expose `forecast_dataset` au ML Agent et `detect_dataset_anomalies` au Statistics Agent. Les résultats conservent la méthode, les diagnostics et les avertissements nécessaires à l’interprétation.
