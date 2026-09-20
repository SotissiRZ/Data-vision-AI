# Migration v2.40.3 → v2.40.4

Aucune migration de base de données ni de configuration n’est requise.

1. Arrêter la stack : `docker compose down`.
2. Remplacer le dossier v2.40.3 par le dossier complet v2.40.4.
3. Conserver/copier le fichier `.env` local si nécessaire.
4. Reconstruire : `docker compose up -d --build`.
5. Vérifier : `docker compose ps`.

Le changement porte uniquement sur le typage TypeScript du Feature Store et n’altère pas les contrats API ni les données persistées.
