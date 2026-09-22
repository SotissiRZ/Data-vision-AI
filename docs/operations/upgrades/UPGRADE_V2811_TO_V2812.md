# Upgrade v2.81.1 → v2.81.2

1. Arrêter proprement l'ancienne stack et conserver les volumes.
2. Extraire l'archive complète v2.81.2 dans un dossier propre ; ne pas superposer les archives.
3. Copier l'ancien `.env` dans le nouveau dossier puis ajouter, pour un poste de développement uniquement :
   - `DEMO_ACCOUNT_ENABLED=true`
   - `DEMO_ACCOUNT_EMAIL=demo@datavision.local`
   - `DEMO_ACCOUNT_PASSWORD=DataVision8!`
4. En production, définir explicitement `DEMO_ACCOUNT_ENABLED=false`.
5. Exécuter `python scripts/config_doctor.py --root . --env-file .env`.
6. Exécuter `docker compose up --build` puis vérifier `/health/ready`.
7. Vérifier l'icône œil sur l'écran de connexion et, en développement, le bouton du compte test.

Aucune migration destructive de données n'est introduite par ce correctif.
