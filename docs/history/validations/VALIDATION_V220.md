# Validation v2.2.0

## Suite automatisée

```text
pytest -q
28 passed
```

Les scénarios v2.2 vérifient notamment :

- preview legacy filtré par RLS/CLS ;
- header de réponse `X-DataVision-Governed` ;
- SQL Workspace sur le sous-ensemble gouverné ;
- impossibilité d'utiliser une colonne cachée dans une analyse ;
- refus des transformations pour le rôle Analyst ;
- refus d'accès à un dataset non lié au workspace ;
- catalogue isolé par workspace ;
- RLS évaluée avant la projection de colonnes ;
- héritage de policies sur une version dérivée ;
- liaison automatique de la version dérivée ;
- réutilisation du contexte tenant-aware par un job de forecasting.

## Compilation

```text
python -m compileall -q app
OK
```

## Ports

```text
Web : 3005
API : 8005
```

Le build Docker/Next.js complet doit être validé sur l'environnement cible Windows/Docker Desktop, comme pour les versions précédentes.
