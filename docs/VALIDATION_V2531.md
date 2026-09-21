# Validation DataVision AI v2.53.1

Hotfix frontend de la vue Insight Engine.

## Défaut corrigé

Le build Next.js de v2.53.0 compilait le bundle puis échouait au contrôle TypeScript car la condition utilisait `feed?.limitations` alors que le rendu référençait ensuite `feed.limitations`. TypeScript conservait donc correctement la possibilité que `feed` soit `null`.

## Correctif

La vue capture désormais `const limitations: string[] = feed?.limitations ?? []` puis utilise uniquement `limitations` dans le JSX.

## Non-régression

Le test `backend/tests/test_frontend_insights_nullability_v2531.py` interdit le retour d'un accès direct `feed.limitations.map`.

Aucune migration de données ni modification d'API n'est requise.
