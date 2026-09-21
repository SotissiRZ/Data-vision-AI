# Migration v2.58.0 → v2.59.0

La migration est additive et non destructive.

- En Helm, le Job `pre-install,pre-upgrade` exécute `python -m app.ops.migrate apply --json` avant le rollout.
- En Docker Compose/local, `SCHEMA_AUTO_MIGRATE=true` conserve l'application automatique des migrations.
- La migration `2.59.0-001` ajoute `backup_runs` et `kms_rotation_events` ainsi que le registre `schema_migrations`.
- Aucun dataset, modèle, rapport ou artefact utilisateur existant n'est supprimé.
