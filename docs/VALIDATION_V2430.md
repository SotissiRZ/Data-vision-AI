# Validation v2.43.0 — Data Workspace reproductible

La v2.43.0 ferme le lot **Data Workspace** du roadmap DataVision sans réécrire les briques notebook/sandbox déjà présentes.

## Gate exécutable

```bash
python scripts/workspace_acceptance.py --root . --check
```

Le manifest `compliance/WORKSPACE_ACCEPTANCE.json` exige 8/8 éléments :

1. SQL local read-only ;
2. Python sandbox isolé ;
3. R sandbox isolé ;
4. notebook lié à une version immuable ;
5. exécution ordonnée de tout le notebook ;
6. artefacts persistés/téléchargeables ;
7. promotion d'artefact en version gouvernée ;
8. provenance reproductible avec hash du code et fingerprint des données.

## Non-régression

Les tests dédiés sont :

- `backend/tests/test_notebook_v218.py` ;
- `backend/tests/test_data_workspace_v243.py` ;
- `backend/tests/test_frontend_workspace_v243.py`.

Le contrôle complet reste complété par `production_baseline.py`, `repository_hygiene.py`, les gates MVP/Data Preparation et la suite backend.

## Limites de validation locale

Le vrai `next build` et la santé des conteneurs restent des preuves d'environnement cible. La CI et le build Docker sur la machine de déploiement constituent la validation finale du frontend/sandbox packagés.
