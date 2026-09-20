# Migration v2.40.0 → v2.40.1

## Objet

Hotfix de build frontend. Aucun changement de schéma, aucune migration de données et aucun changement de contrat API.

## Correctif

`frontend/app/page.tsx` capture désormais le modèle XAI non nul dans `activeModel` avant de définir les callbacks asynchrones. Cela permet à TypeScript de conserver la garantie de non-nullité dans `runCf()` et les autres callbacks XAI.

## Mise à niveau

Remplacer le dossier v2.40.0 par le dossier complet v2.40.1, conserver votre `.env`, puis reconstruire les images Docker.
