# Upgrade DataVision v2.81.4 → v2.81.5

La v2.81.5 introduit une interface d’authentification standard Connexion / Inscription et l’auto-inscription configurable.

1. Extraire la v2.81.5 dans un nouveau dossier.
2. Copier le fichier `.env` de l’installation précédente.
3. Pour autoriser l’inscription depuis l’interface, définir `SELF_REGISTRATION_ENABLED=true`.
4. Exécuter `./upgrade-windows.ps1`.
5. Ouvrir DataVision et vérifier que les onglets **Connexion** et **Inscription** sont disponibles.

Aucune migration de schéma n’est nécessaire. Les comptes existants restent inchangés.
