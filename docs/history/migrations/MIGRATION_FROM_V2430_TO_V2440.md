# Migration v2.43.0 → v2.44.0

1. Conserver votre `.env` actuel et vos volumes Docker existants.
2. Remplacer le dossier applicatif par la distribution complète v2.44.0.
3. Replacer/copier le `.env` à la racine si nécessaire.
4. Lancer `python scripts/assistant_acceptance.py --root . --check`.
5. Lancer `docker compose down` puis `docker compose up -d --build`.
6. Vérifier `docker compose ps` puis `/api/health` et `/api/v1/ai/assistant/health` via le proxy applicatif.

Aucune suppression de volume n'est requise. Les datasets, modèles, notebooks et métadonnées existants restent compatibles.
