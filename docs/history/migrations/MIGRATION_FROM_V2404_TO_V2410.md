# Migration v2.40.4 → v2.41.0

Aucune migration de base de données n'est requise.

## Changement de stockage local des métadonnées dataset

À partir de v2.41.0, les metadata sidecars utilisent `<dataset_id>.meta.json` afin de ne jamais entrer en collision avec un dataset JSON brut `<dataset_id>.json`.

- les sidecars legacy `<dataset_id>.json` des datasets CSV/XLSX/Parquet/TXT restent lisibles ;
- les nouveaux datasets utilisent automatiquement le nouveau format ;
- un dataset JSON importé avant v2.41.0 dont le fichier a déjà été écrasé par son sidecar doit être réimporté depuis le fichier source d'origine.

## Mise à niveau

1. `docker compose down`
2. Remplacer le dossier applicatif par la distribution complète v2.41.0.
3. Conserver les volumes Docker et recopier le `.env` local.
4. `docker compose up -d --build`
5. `docker compose ps`
6. Exécuter, si Python local dispose des dépendances backend : `python scripts/mvp_acceptance.py --root . --check`

Ne pas utiliser `docker compose down -v` sauf si la suppression volontaire des données persistantes est souhaitée.
