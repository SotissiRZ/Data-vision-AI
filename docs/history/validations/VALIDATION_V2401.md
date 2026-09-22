# Validation v2.40.1

## Motif de la release

Le build Docker/Next v2.40.0 échouait lors du contrôle TypeScript avec : `app/page.tsx:1023 — model is possibly null`.

## Correction

Le composant XAI utilise désormais une référence `activeModel` capturée après `if (!model) return ...`. Les callbacks asynchrones n'accèdent plus à `model.task` sans narrowing persistant.

## Contrôles inclus

- production baseline ;
- repository hygiene ;
- audit CDC ;
- tests backend et test de non-régression XAI ;
- vérification cryptographique de l'archive de release.

## Validation machine cible

Le build Docker complet doit être relancé sur la machine cible avec `docker compose up -d --build`.
