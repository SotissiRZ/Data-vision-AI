# DataVision AI v2.51.0 — ML Safety & Guardrails

## Objectif

v2.51 transforme les garde-fous ML historiques en politiques exécutables, vérifiables et traçables. L'AutoML ne se contente plus de signaler un risque après entraînement : il peut modifier la stratégie de validation, exclure une feature ou bloquer le run avant tout calcul lorsque la sécurité analytique l'exige.

## Contrôles exécutables

- **Leakage** : copie directe de la cible bloquante, corrélation numérique quasi parfaite exclue, proxy déterministe signalé.
- **Identifiants** : IDs, UUIDs, quasi-identifiants et constantes exclus automatiquement.
- **Déséquilibre** : distribution des classes analysée avant entraînement ; `accuracy` est remplacée par `balanced_accuracy` quand elle serait trompeuse.
- **Petit échantillon** : blocage sous 40 observations complètes ; avertissement sous 100.
- **Temps** : `auto` impose un split chronologique lorsqu'une colonne temporelle fiable est détectée ; `temporal` l'exige explicitement ; `random` reste possible mais documenté.
- **Test final** : les index train/validation/test sont disjoints et hashés ; sélection et tuning n'utilisent jamais le test final.
- **Surapprentissage** : comparaison train/validation sur la métrique de sélection avant refit final.
- **UI/Assistant** : audit pré-entraînement visible dans le Studio ML ; le ML Agent transmet `time_split` au même moteur gouverné.

## API

`POST /api/v1/datasets/{dataset_id}/models/safety-audit`

Le payload accepte `target`, `task`, `features`, `primary_metric`, `split_strategy` et `time_column`.

## Validation

```bash
python scripts/ml_safety_acceptance.py --root . --check
```

Le gate doit retourner `ML Safety acceptance: PASS (8/8 items)` avant release.
