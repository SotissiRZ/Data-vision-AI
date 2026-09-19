# DataVision v2.18.0 — Notebook sandboxé

## Objectif CDC

Couvre le chantier :

- Notebook intégré ;
- Python Workspace ;
- SQL Workspace ;
- R Workspace ;
- exécution isolée ;
- reproductibilité ;
- liaison dataset/version ;
- résultats vers artefacts.

## Architecture

```text
DataVision Web
    ↓
/api/v1/notebooks
    ↓
Notebook Service
    ├── Metadata Store
    ├── Audit
    ├── RBAC / RLS
    ├── SQL read-only → DuckDB
    └── Python / R
            ↓
       Sandbox Service
```

## Sandbox

Le sandbox est un conteneur interne séparé.

Contrôles Docker :
- `read_only: true` ;
- `tmpfs /tmp` ;
- `cap_drop: ALL` ;
- `no-new-privileges` ;
- limite mémoire ;
- limite CPU ;
- limite PID ;
- réseau `internal: true` ;
- aucun port publié.

Contrôles processus :
- timeout ;
- limite CPU ;
- limite taille fichiers ;
- limite des descripteurs ;
- environnement nettoyé ;
- répertoire temporaire éphémère.

## Dataset

L'API charge d'abord le dataframe avec le mécanisme normal DataVision.
En Enterprise, cela signifie que RLS et column-level security sont déjà
appliqués avant la sérialisation vers le sandbox.

Le sandbox ne reçoit donc que le dataframe gouverné autorisé pour la requête.

## Python

Variables disponibles :
- `df` ;
- `dataset`.

Helpers :
- `dv_save_dataframe(...)` ;
- `dv_save_json(...)`.

La dernière expression est transformée en résultat structuré lorsque possible.

## R

Variables disponibles :
- `data` ;
- `dataset`.

Helper :
- `dv_save_dataframe(...)`.

## SQL

Table :
- `dataset`.

Une seule requête `SELECT` ou `WITH` est autorisée.

## Artefacts

Les fichiers autorisés sont récupérés depuis le sandbox, bornés en taille,
puis persistés dans le stockage DataVision :

- PNG ;
- SVG ;
- HTML ;
- JSON ;
- CSV ;
- TXT.

## Limites explicites

Cette version ne revendique pas encore :
- kernels persistants entre cellules ;
- Jupyter protocol ;
- GPU sandbox ;
- environnements Conda personnalisés ;
- installation de packages à la volée ;
- collaboration temps réel à plusieurs curseurs.

Ces éléments restent planifiés plutôt que simulés.
