# Semantic Model Studio v2 — DataVision AI 2.3

## Objectif

La couche sémantique v2 fournit une définition métier stable au-dessus des datasets physiques. Elle sert à éviter trois erreurs classiques : dupliquer la logique de calcul dans plusieurs écrans, faire deviner au moteur IA la signification d'une colonne, et agréger une métrique sur une jointure qui modifie le grain des données.

## Structure du modèle

Un modèle contient :

- `tables` : datasets participants et alias métier ;
- `relationships` : relations directionnelles sûres depuis la table de faits ;
- `metrics` : mesures de base ou calculées ;
- `dimensions` : axes d'analyse certifiables ;
- `hierarchies` : chemins de navigation métier ;
- `business_glossary` : vocabulaire métier.

La table `base` correspond toujours au dataset racine actuellement ouvert.

## Relations et grain

L'exécution automatique accepte actuellement :

- `many_to_one` ;
- `one_to_one`.

La clé de droite d'une relation `many_to_one` doit être unique. Une violation est bloquée avant sauvegarde et avant exécution. Les relations `many_to_many` et `one_to_many` ne sont pas exécutées automatiquement tant qu'un modèle de grain explicite n'est pas disponible.

Cette contrainte est volontaire : une jointure qui multiplie les lignes peut transformer `SUM(revenue)` en un chiffre faux tout en donnant un SQL techniquement valide.

## Métriques

### Métrique de base

Une métrique de base possède :

```json
{
  "id": "revenue",
  "type": "base",
  "table": "base",
  "column": "revenue",
  "aggregation": "sum"
}
```

Agrégations : `sum`, `mean`, `median`, `min`, `max`, `count`, `nunique`.

### Métrique calculée

Une métrique calculée référence des IDs de métriques :

```text
(revenue - cost) / revenue * 100
```

L'expression autorise uniquement nombres, noms de métriques, parenthèses et opérateurs arithmétiques. Elle est interprétée via AST ; aucun code arbitraire n'est exécuté.

## Dimensions

Une dimension possède un ID sémantique, une table, une colonne physique, un label, des synonymes, un type et un état de certification. Une dimension masquée ne peut pas être utilisée dans le Query Lab.

## Hiérarchies

Une hiérarchie référence une suite ordonnée d'IDs de dimensions. Exemple :

```text
calendar = [year, quarter, month]
```

La v2.3 persiste et valide ces hiérarchies. Depuis la v2.4, le Dashboard Builder les exécute comme chemins de drill-down avec filtres parents conservés.

## Semantic Query Engine

Endpoint :

```text
POST /api/v1/datasets/{dataset_id}/semantic/query
```

Exemple :

```json
{
  "metric_id": "revenue",
  "dimensions": ["category"],
  "date_dimension": "order_date",
  "time_grain": "month",
  "comparison": "yoy",
  "time_calculation": "ytd"
}
```

Le moteur :

1. résout métrique et dimensions ;
2. identifie les tables nécessaires ;
3. construit uniquement les jointures sûres ;
4. applique les filtres gouvernés ;
5. agrège la métrique ;
6. évalue les métriques calculées ;
7. applique l'intelligence temporelle ;
8. retourne les résultats et la version du modèle sémantique.

## Time intelligence

Granularités : `day`, `week`, `month`, `quarter`, `year`.

Comparaisons :

- `previous_period` ;
- `yoy`.

Calculs :

- `running_total` ;
- `ytd` ;
- `rolling_mean` ;
- `rolling_sum`.

Ces calculs sont descriptifs et déterministes. Leur validité métier dépend de la définition de la métrique (par exemple, un cumul de pourcentage n'a généralement pas de sens).

## Sécurité Enterprise

Les tables liées sont chargées via le même `load_dataframe()` tenant-aware que le reste de DataVision. Ainsi, une relation ne permet pas de contourner RBAC/RLS/Column Security. Une table d'un workspace non autorisé n'est pas disponible dans le catalogue sémantique et son chargement est refusé.

## Limites actuelles

- pas de relation N:N automatique ;
- pas de modèle explicite de grain composite ;
- pas encore de SQL multi-table généré depuis NLQ ;
- les hiérarchies ne pilotent pas encore le drill-down du Dashboard Builder ;
- les métriques sémantiques ne sont pas encore des widgets natifs du Dashboard Builder.

Ces limites sont déclarées pour éviter de simuler une maturité qui n'est pas encore implémentée.
