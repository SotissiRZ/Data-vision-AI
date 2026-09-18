# Validation — DataVision AI v2.8.0

Date de validation : 2026-09-18.

## Backend

```text
pytest -q
50 passed
```

Les scénarios v2.8 ajoutés couvrent :

- création d'un Data Contract ;
- required columns ;
- volume ;
- nullité ;
- unicité ;
- plage numérique ;
- score de fiabilité ;
- version saine puis version dégradée ;
- Publication Gate ouvert puis bloqué ;
- distribution drift numérique KS ;
- distribution drift catégorielle TVD ;
- lineage version → analyse → dashboard ;
- impact analysis downstream ;
- blocage de certification par contrat critique ;
- blocage d'export de rapport en contexte Enterprise.

Les suites des versions précédentes restent également exécutées, y compris RBAC/RLS, connecteurs, refresh, collaboration, couche sémantique, dashboards, reporting, ML et AI Analyst.

## Python

```text
python -m compileall backend/app
OK
```

## Frontend

Validation effectuée avec le compilateur TypeScript disponible dans l'environnement :

```text
tsc --noEmit --noCheck ...
OK

tsc --noEmit --strictNullChecks true --noImplicitAny false ...
OK
```

La validation ciblée couvre `app/page.tsx` et `lib/api.ts`, dont le nouveau Reliability Center.

## Non revendiqué

Les éléments suivants ne sont pas déclarés comme validés dans l'environnement de génération :

- `next build` complet avec toutes les dépendances npm réinstallées ;
- build Docker natif ;
- navigateur réel ;
- serveur PostgreSQL/MySQL externe réel.

Ils doivent être confirmés sur la machine Docker cible.
