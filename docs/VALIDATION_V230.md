# Validation DataVision AI v2.3.0

## Backend

- `pytest -q` : **31 passed**.
- `python -m compileall app` : OK.

## Scénarios v2.3 ajoutés

1. Catalogue de tables sémantiques visible.
2. Modèle fact + dimension avec relation N:1 valide.
3. Agrégation d'une métrique de la table de faits par une dimension d'une table liée.
4. Métrique calculée sûre à partir de deux métriques de base.
5. Comparaison YoY par période calendaire réelle.
6. YTD sur une série mensuelle.
7. Blocage d'une relation N:1 lorsque la clé côté dimension contient des doublons.

## Frontend

`page.tsx` et `lib/api.ts` sont passés dans `typescript.transpileModule` avec TypeScript 5.8.3 : aucune erreur de syntaxe/transpilation.

Le build `next build` complet reste à valider sur l'environnement Docker utilisateur disposant des dépendances npm, conformément au processus utilisé depuis les versions précédentes.
