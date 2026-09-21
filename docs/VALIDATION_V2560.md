# Validation v2.56.0

## Gate dédié

```bash
python scripts/entreprise_acceptance.py --root . --check
```

Contrat : `ENTREPRISE_ACCEPTANCE 8/8`.

## Tests ciblés

```bash
cd backend
PYTHONPATH=. pytest -q tests/test_entreprise_platform_v2560.py tests/test_frontend_entreprise_v2560.py
```

Les tests couvrent le stockage hashé des jetons SCIM, le cycle utilisateur SCIM, la découverte OIDC par domaine, Private AI, Prometheus, la posture on-prem et la terminologie visible.

## Validation complète avant release

```bash
cd backend
PYTHONPATH=. pytest -q
cd ..
python scripts/entreprise_acceptance.py --root . --check
python scripts/release.py --root .
```

Le build Next.js nécessite les dépendances frontend installées (`npm ci`) ; le dépôt source n’embarque volontairement pas `node_modules`.
