# Migration v2.41.0 → v2.42.0

La migration ne modifie aucun schéma de dataset existant et ne requiert pas de suppression de volumes Docker.

## Changements principaux

1. Les pipelines enregistrés en ancien format restent lisibles et rejouables.
2. Les nouveaux pipelines utilisent `format_version: 2` et distinguent explicitement les étapes `transform` et `combine_dataset`.
3. Une combinaison multi-dataset sauvegardée conserve l'identifiant, la racine et la version de sa dépendance secondaire.
4. Au replay, une dépendance peut être remplacée par un binding `{root_id: dataset_id}`.
5. Le moteur prévalide toutes les étapes en mémoire avant toute création de version persistée.

## Déploiement

1. Conserver `.env` et les volumes persistants.
2. Remplacer le dossier applicatif par la distribution complète v2.42.0.
3. Exécuter `preflight-windows.ps1` ou le baseline de production.
4. Reconstruire avec `docker compose up -d --build`.

Ne pas utiliser `docker compose down -v` sauf volonté explicite de supprimer les données persistantes.
