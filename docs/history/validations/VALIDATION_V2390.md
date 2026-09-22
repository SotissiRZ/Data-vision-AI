# Validation DataVision AI v2.39.0

## Scope

Repository Cleanup & Professional Structure.

## Guarantees

- aucun moteur analytique modifié ;
- aucune route métier supprimée ;
- manifests historiques déplacés hors de la racine ;
- migration historique déplacée sous `docs/history/` ;
- contrôle automatique d'hygiène du dépôt ;
- scripts Windows et version alignés sur v2.39.0.

## Checks

- `python scripts/repository_hygiene.py --check`
- compilation Python
- tests backend disponibles
- audit CDC
- inspection de préservation des fichiers v2.38
- packaging reproductible
