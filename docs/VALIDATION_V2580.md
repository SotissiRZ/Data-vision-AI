# Validation v2.58.0 — Hardening de production Entreprise

## Gate principal

```bash
python scripts/hardening_acceptance.py --root . --check
```

Contrat : `HARDENING_ACCEPTANCE 8/8`.

## Tests ciblés

```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_entreprise_hardening_v2580.py \
  backend/tests/test_entreprise_platform_v2560.py \
  backend/tests/test_frontend_entreprise_v2560.py
```

## Contrôles de release

```bash
python scripts/production_baseline.py --root . --check
python scripts/repository_hygiene.py --root . --check
python scripts/entreprise_acceptance.py --root . --check
python scripts/hardening_acceptance.py --root . --check
python scripts/release.py --root . --output dist
```
