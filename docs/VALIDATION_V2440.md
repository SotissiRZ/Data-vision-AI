# Validation v2.44.0 — Assistant V1 tool-connected

La v2.44.0 ferme le lot **Assistant V1** du roadmap DataVision en consolidant les briques agentiques existantes autour d'un contrat exécutable et vérifiable.

## Gate principal

```bash
python scripts/assistant_acceptance.py --root . --check
```

Le manifest `compliance/ASSISTANT_ACCEPTANCE.json` exige 8/8 éléments : assistant flottant, contexte live, outils exécutables uniquement, exécution hôte réelle, actions gouvernées, resynchronisation UI, fichiers et voix/texte.

## Garanties ajoutées

- un outil non raccordé n'est plus exposé au planner ni au catalogue utilisateur ;
- le Plan Validator et l'Executor refusent explicitement un outil sans handler ;
- le contexte utilisé pour une action est relu au moment exact de son déclenchement ;
- une transformation agentique provoque le rechargement de la version produite dans l'interface ;
- les résultats modèle/rapport/visualisation/notebook peuvent rediriger l'utilisateur vers le module concerné ;
- les confirmations côté serveur restent l'autorité pour toute action sensible.

## Validation locale attendue

```bash
python scripts/production_baseline.py --root . --check
python scripts/assistant_acceptance.py --root . --check
python scripts/repository_hygiene.py --check
```

Le build Docker/Next complet reste à confirmer sur la machine cible avec `docker compose up -d --build`.
