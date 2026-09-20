# Validation v2.41.0 — MVP Acceptance Gate

## Objectif

Transformer le statut MVP d'une preuve principalement structurelle en un gate exécutable couvrant le workflow analytique prioritaire :

`import → profiling → quality → preparation → statistics → visualization → history → export`

## Correctif fonctionnel P0 découvert pendant l'audit

L'audit a révélé une collision de fichiers pour les uploads JSON : le dataset brut `<id>.json` et son metadata sidecar utilisaient le même chemin. Le sidecar pouvait donc écraser le contenu JSON original.

La v2.41.0 sépare désormais les deux ressources :

- données JSON : `<id>.json` ;
- métadonnées : `<id>.meta.json`.

La lecture des anciens sidecars `<id>.json` reste compatible lorsqu'ils contiennent réellement un objet metadata valide. Un ancien upload JSON déjà écrasé avant v2.41.0 ne peut pas être reconstruit automatiquement ; il doit être réimporté depuis sa source originale.

## Preuves exécutables ajoutées

- `compliance/MVP_ACCEPTANCE.json` : matrice des 16 exigences MVP obligatoires ;
- `scripts/mvp_acceptance.py --check` : valide la matrice et exécute le workflow backend intégré ;
- `backend/tests/test_mvp_workflow_v241.py` : import, profilage, qualité, transformation versionnée, statistiques, visualisation, SQL local, AI Analyst, historique, rapport et exports HTML/PDF ;
- validation runtime CSV/XLSX/JSON ; Parquet est exécuté lorsque `pyarrow` est disponible et reste contractualisé par la dépendance Docker/CI sinon ;
- `frontend/e2e/mvp.spec.ts` : même parcours principal via le proxy frontend réel `/api/backend` sur la stack Docker ;
- CI backend : gate MVP explicite ;
- CI E2E : smoke UI + workflow MVP déployé.

## Critères de validation

- Production Baseline : PASS ;
- Repository Hygiene : PASS ;
- CDC audit : aucune preuve manquante ;
- 16/16 exigences MVP avec preuve + test déclarés ;
- workflow backend intégré : PASS ;
- suite backend : PASS ;
- build frontend/Docker et E2E déployé : à confirmer par la CI ou la machine cible.
