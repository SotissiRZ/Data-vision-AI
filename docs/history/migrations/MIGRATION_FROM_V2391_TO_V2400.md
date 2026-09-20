# Migration v2.39.1 → v2.40.0

Aucune migration de données n'est requise.

v2.40.0 ajoute des contrôles de baseline et renforce l'intégrité des archives de release. Les moteurs analytiques, schémas de données et contrats assistant existants sont conservés.

## Vérifications recommandées

```powershell
python scripts/production_baseline.py --check
python scripts/repository_hygiene.py --check
python scripts/cdc_audit.py --check
.\preflight-windows.ps1
```

Le préflight exige désormais `VERSION=2.40.0`.
