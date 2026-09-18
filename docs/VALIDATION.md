# Validation — v1.0.2

## Backend

```text
16 passed
```

La suite couvre notamment :

- upload / profiling / qualité ;
- préparation / versioning / rollback ;
- pipelines et feature engineering ;
- tests statistiques avec tailles d’effet et payloads de visualisation ;
- régression avec Q-Q plot, histogramme des résidus et influence ;
- ANOVA, ACP et clustering ;
- SQL, NLQ et visualisations ;
- AutoML, model registry et XAI ;
- forecasting et anomalies ;
- AI Analyst et provenance ;
- historique AI Analyst ;
- Report Builder et exports.

## Python

`python -m compileall backend/app` : OK.

## Frontend

Les fichiers `frontend/app/page.tsx` et `frontend/lib/api.ts` ont été validés au niveau syntaxique par transpilation TypeScript.

Le build Next.js/Docker complet reste à exécuter sur la machine cible. Cette distinction est volontaire : une validation syntaxique n’est pas présentée comme un build de production réussi.

## Ports

```text
Web : 3005
API : 8005
```
