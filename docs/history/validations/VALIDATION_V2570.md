# Validation v2.57.0

## Gate dédié

```bash
python scripts/assistant_window_acceptance.py --root . --check
```

Contrat : `ASSISTANT_WINDOW_ACCEPTANCE 6/6`.

## Tests ciblés

```bash
cd backend
pytest -q tests/test_frontend_assistant_window_v2570.py
```

## Contrôles release

```bash
python scripts/production_baseline.py --root . --check
python scripts/repository_hygiene.py --check
python scripts/assistant_acceptance.py --root . --check
python scripts/assistant_window_acceptance.py --root . --check
python scripts/entreprise_acceptance.py --root . --check
python scripts/release.py --output dist
python scripts/verify_release.py dist/datavision-ai-v2.57.0-complet.zip --sha-file dist/datavision-ai-v2.57.0-complet.zip.sha256
```
