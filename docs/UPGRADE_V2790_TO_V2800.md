# Upgrade v2.79.x → v2.80.0

1. Conserver le dossier v2.79.x tant que le nouvel environnement n'est pas validé.
2. Copier votre `.env` v2.79.x dans le dossier v2.80.0.
3. Exécuter `python scripts/config_doctor.py --root . --env-file .env`.
4. Exécuter `.\upgrade-windows.ps1`.
5. Vérifier `docker compose ps`, `http://localhost:3005` et `http://localhost:8005/health/ready`.
6. Conserver la sauvegarde générée et les preuves d'upgrade avec le dossier de sign-off.

Le projet Compose reste nommé `datavision`; les volumes `postgres_data`, `redis_data` et `clamav_data` sont donc conservés. Le script d'upgrade n'emploie pas `down -v`.

La migration la plus récente attendue est `2.80.0-001` (`release_candidate_freeze_marker`).
