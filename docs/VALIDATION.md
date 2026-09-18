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
