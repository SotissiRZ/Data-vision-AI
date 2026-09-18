# Validation — DataVision AI v2.0.0

```text
Backend pytest   : 23 passed
Python compileall: OK
TSX syntax       : OK via TypeScript transpileModule
api.ts syntax    : OK via TypeScript transpileModule
CSS braces       : OK
Ports            : 3005 / 8005
```

Nouveaux parcours couverts : couche sémantique, métriques certifiées, NLQ avec synonymes et agrégation explicite, Trust Center, grounding sémantique d'AI Analyst, Decision Lab what-if et sensibilité.

Le build `next build` complet n'est pas déclaré validé dans l'environnement de génération : l'installation npm a dépassé le délai disponible. La validation finale Docker reste effectuée sur la machine cible.

# Validation — DataVision AI v1.3.0

- Backend : 20 tests passent.
- Python : `compileall` OK.
- Dashboard Builder : persistance, preview filtré, KPI et graphique agrégé couverts par test API.
- Frontend TSX/TS : transpilation syntaxique OK.
- Ports : 3005 / 8005.
- Build Next.js/Docker final : à confirmer sur la machine cible.

# Validation — v1.2.0

## Backend

```text
19 passed
```

La suite couvre notamment :

- upload / profiling / qualité ;
- préparation / versioning / rollback ;
- pipelines et feature engineering ;
- tests statistiques, régression, ANOVA, ACP et clustering ;
- SQL, NLQ et visualisations ;
- AutoML, model registry, forecasting, anomalies et XAI ;
- AI Analyst, critic et provenance ;
- dashboard analytique et visualisations sauvegardées ;
- Professional Report Studio ;
- narration analytique automatique ;
- visualisations automatiques de rapport ;
- limites et précautions d’interprétation ;
- exports PDF, DOCX, HTML et Markdown.

## Python

`python -m compileall backend/app` : OK.

## Frontend

- transpilation syntaxique TypeScript/TSX : OK ;
- le build complet Next.js n’est pas déclaré validé dans cet environnement faute d’installation locale complète des dépendances frontend.

## QA visuelle des rapports

Un rapport intelligent de validation a été exporté puis rendu pour contrôle visuel :

```text
PDF  : 13 pages rendues et inspectées
DOCX : 13 pages rendues et inspectées
```

Contrôles effectués : page de garde, narration analytique, cartes de constats, graphiques et légendes, limites, pagination, absence de chevauchement et de titres de figures orphelins.

## Ports

```text
Web : 3005
API : 8005
```
