# Migration v2.40.1 → v2.40.2

## Objet

Correctif de build frontend XAI. Aucune migration de base de données ni modification du format des datasets.

## Procédure

1. Conserver votre fichier `.env` actuel.
2. Remplacer le dossier v2.40.1 par le dossier complet v2.40.2.
3. Recopier `.env` si nécessaire.
4. Reconstruire les images Docker avec `docker compose up -d --build`.
5. Vérifier les services avec `docker compose ps`.

## Compatibilité

Les données PostgreSQL, Redis et les volumes applicatifs restent compatibles.
