# Migration v2.50.0 → v2.51.0

- Aucun changement destructif de dataset ou de modèle existant.
- `AutoMLRequest` et `BenchmarkRequest` ajoutent `split_strategy` (`auto|random|temporal`) et `time_column` optionnel.
- Nouveau endpoint `models/safety-audit` sans entraînement.
- En classification déséquilibrée, une demande explicite `accuracy` peut être gouvernée vers `balanced_accuracy`.
- Une copie directe de la cible bloque désormais AutoML au lieu de seulement produire un warning.
- En mode `auto`, une colonne temporelle fiable déclenche un split chronologique et le timestamp brut est retiré des features.
- Les Model Cards et expériences stockent `safety_audit`, `split_audit` et `overfitting_assessment`.
