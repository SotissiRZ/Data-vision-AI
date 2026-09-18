# DataVision AI v2.8 — Data Reliability & Lineage

## 1. Objectif

La v2.8 ajoute une couche de fiabilité indépendante des moteurs d'analyse. Elle répond à quatre questions avant qu'un résultat ne soit diffusé :

1. Le dataset respecte-t-il les règles attendues ?
2. Sa distribution a-t-elle changé de façon significative ?
3. Quelles ressources dépendent de ce dataset ?
4. Une publication ou certification doit-elle être autorisée ?

Cette couche reste déterministe : aucun LLM n'évalue un Data Contract.

## 2. Modèle de Data Contract

Un contrat est lié à la **lignée racine** d'un dataset. Il continue donc à s'appliquer aux versions dérivées.

```json
{
  "name": "Sales contract",
  "enforcement_mode": "block",
  "rules": [
    {"type":"required_columns","columns":["id","revenue"],"severity":"critical"},
    {"type":"row_count","min":1000,"severity":"high"},
    {"type":"missing_pct","column":"revenue","max":1,"severity":"critical"},
    {"type":"unique","column":"id","max_duplicate_pct":0,"severity":"critical"},
    {"type":"distribution_drift","column":"revenue","max_ks":0.2,"severity":"high"}
  ]
}
```

### Modes

- `monitor` : enregistre les échecs sans conséquence de publication ;
- `warn` : fait remonter les échecs comme avertissements ;
- `block` : les règles bloquantes en échec ferment le Publication Gate.

### États

- `never_run` ;
- `healthy` ;
- `warning` ;
- `failing` ;
- `critical`.

## 3. Règles supportées

### required_columns

Vérifie la présence de colonnes obligatoires.

### row_count

Vérifie un minimum et/ou maximum de lignes.

### missing_pct

Contrôle le pourcentage de valeurs manquantes pour une colonne.

### unique

Contrôle le taux maximal de doublons parmi les valeurs non nulles.

### range

Contrôle une plage numérique minimale/maximale et considère les valeurs non convertibles comme invalides.

### allowed_values

Contrôle un domaine catégoriel autorisé.

### dtype

Familles disponibles : `boolean`, `integer`, `numeric`, `datetime`, `string`.

### regex

Valide les valeurs non nulles avec une expression régulière.

### distribution_drift

- numérique : statistique de Kolmogorov-Smirnov ;
- catégoriel : Total Variation Distance.

La baseline par défaut est la version précédente de la même lignée.

## 4. Score de fiabilité

Les règles sont pondérées par sévérité :

```text
low       1
medium    2
high      3
critical  4
```

Le score est la proportion pondérée de contrôles réussis. Il sert à l'observabilité ; le Publication Gate s'appuie directement sur l'état et les règles bloquantes, pas seulement sur un seuil arbitraire de score.

## 5. Validation automatique des versions

Deux chemins réexécutent automatiquement les contrats :

- nouvelle version issue d'une transformation gouvernée ;
- nouvelle version issue d'un refresh connecteur.

Un échec de Data Contract n'annule pas la création immuable d'une version : il crée un événement de fiabilité et peut fermer le gate de publication. Cela maintient la traçabilité de ce qui est réellement arrivé aux données.

## 6. Publication Gate

Le gate retourne :

```text
allowed
blockers
warnings
contracts_evaluated
freshness
```

Règle fail-closed importante : un contrat `block` doit avoir été exécuté sur la **version exacte** demandée. Si une nouvelle version n'a jamais été évaluée, le gate reste fermé.

Le gate est branché sur :

- `Review Center → Certify` ;
- export des rapports en session Enterprise.

## 7. Lineage

Le graphe est reconstruit à partir des artefacts persistés et du registre explicite :

- `refresh_runs` pour les sources ;
- metadata de versions pour les transformations ;
- analyses AI enregistrées ;
- Model Cards ;
- dashboards ;
- rapports ;
- modèle sémantique ;
- `lineage_registry` pour les relations explicitement enregistrées.

Relations principales :

```text
source          --materialized_as--> dataset
dataset         --transformed_to--> dataset
dataset         --analyzed_by-----> analysis
dataset         --trained_model---> model
dataset         --defines_metric--> metric
dataset         --feeds_dashboard-> dashboard
dataset         --feeds_report----> report
analysis        --included_in-----> report
```

## 8. Impact Analysis

L'analyse d'impact parcourt le graphe downstream par BFS avec profondeur limitée. Elle renvoie :

- ressources impactées ;
- profondeur ;
- relation utilisée ;
- résumé par type de ressource.

Elle permet par exemple de vérifier qu'une modification de dataset touche 2 dashboards, 1 modèle et 3 rapports avant de la publier.

## 9. API

```text
GET    /api/v1/workspaces/{workspace}/reliability/summary
GET    /api/v1/workspaces/{workspace}/contracts
POST   /api/v1/workspaces/{workspace}/contracts
GET    /api/v1/workspaces/{workspace}/contracts/{contract}
DELETE /api/v1/workspaces/{workspace}/contracts/{contract}
POST   /api/v1/workspaces/{workspace}/contracts/{contract}/run
GET    /api/v1/workspaces/{workspace}/contract-runs
GET    /api/v1/workspaces/{workspace}/lineage
GET    /api/v1/workspaces/{workspace}/impact/{type}/{id}
POST   /api/v1/workspaces/{workspace}/publication-gate
```

## 10. Limites v2.8

- lineage cross-system hors de DataVision non encore disponible ;
- pas encore de data contract SQL personnalisé ;
- pas de profil probabiliste complexe pour drift multivarié ;
- pas encore de SLO temporel agrégé par data product ;
- pas de notification externe Slack/Teams/Jira lors d'une rupture ;
- build Next/Docker complet à confirmer sur la machine cible.

Ces limites restent explicites afin d'éviter de présenter une capacité planifiée comme implémentée.
