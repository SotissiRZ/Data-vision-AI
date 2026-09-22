# Validation v2.48.0 — Insight Engine

La v2.48.0 introduit un moteur d'insights déterministe et traçable.

## Couverture

- qualité des données ;
- anomalies par z-score robuste MAD ;
- tendances par agrégation temporelle + pente normalisée ;
- segments dominants et écarts standardisés ;
- corrélations de Pearson ;
- changements de volume et de moyenne entre versions immuables ;
- ranking, fingerprints et historique des scans ;
- UI dédiée et outil Assistant/Statistics Agent.

## Gate

```bash
python scripts/insight_acceptance.py --root . --check
```

Le gate exige 8/8 items et exécute les tests backend/frontend v2.48.

## Principe de fiabilité

Tous les nombres proviennent des moteurs Python déterministes. Les textes d'explication ne transforment jamais une association descriptive en causalité.
