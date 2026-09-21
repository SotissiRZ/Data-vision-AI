# Validation v2.60.0

Gate principal :

```bash
python scripts/sre_acceptance.py --root . --check
```

Le gate vérifie huit familles : error budget/alerting, Governed Actions, stockage objet S3-compatible, restore drill, KEDA Redis, chaos contrôlé, cockpit SRE et intégration CI/release.

Tests ciblés : `backend/tests/test_sre_operations_v2600.py`.
