# Upgrade DataVision v2.81.5 → v2.81.6

La v2.81.6 supprime le second formulaire de connexion qui restait intégré à **Gouvernance & sécurité**. L’interface web possède désormais une seule porte d’entrée : l’écran standard **Connexion / Inscription**.

1. Extraire la v2.81.6 dans un nouveau dossier.
2. Copier le fichier `.env` de l’installation précédente.
3. Exécuter `./upgrade-windows.ps1`.
4. Ouvrir DataVision : sans session, l’écran **Connexion / Inscription** doit apparaître avant l’application.
5. Après connexion, ouvrir **Gouvernance & sécurité** et vérifier qu’aucun formulaire de connexion secondaire n’est affiché.

Aucune migration de schéma n’est nécessaire. Les comptes, organisations, workspaces, rôles et politiques existants restent inchangés.
