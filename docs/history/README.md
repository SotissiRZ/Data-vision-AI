# Historique technique DataVision AI

Ce dossier contient les artefacts historiques des versions précédentes. Ils sont
conservés pour la traçabilité, l'audit et la reproductibilité, mais **ne sont pas
nécessaires au fonctionnement courant de DataVision AI**.

## Organisation

- `manifests/` : manifests de fusion des versions historiques ;
- `migrations/` : guides de migration historiques.

Les fichiers opérationnels restent à la racine du dépôt : `README.md`,
`SECURITY.md`, `VERSION`, `docker-compose.yml`, `.env.example`, `Makefile` et les
scripts Windows de démarrage/reconstruction.

À partir de v2.39.0, les nouveaux manifests historiques doivent être placés ici
et non à la racine du dépôt.
