# Dashboard Builder — DataVision AI v1.3.0

## Objectif

Le Dashboard Builder permet de composer des tableaux de bord décisionnels persistants à partir des moteurs DataVision. Les widgets restent liés au dataset et à sa lignée ; les calculs sont exécutés côté backend.

## Widgets

- KPI : lignes, variables, qualité, manquants, doublons, moyenne, somme, médiane, valeurs uniques et pourcentage manquant.
- Graphiques : barres, courbe, aire, histogramme, densité, scatter, boxplot et heatmap.
- Texte : notes et interprétations libres.

Chaque widget possède un identifiant, un titre, une taille, un ordre et une configuration analytique.

## Filtres globaux

Opérateurs disponibles : `eq`, `neq`, `contains`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `not_null`. Les filtres sont évalués avant les calculs. Les comparaisons numériques et temporelles sont coercées lorsque cela est possible.

## Cross-filtering

Un clic sur une barre ajoute un filtre global sur la dimension correspondante. Un nouveau clic sur une autre valeur de la même dimension remplace le cross-filter précédent. Les filtres peuvent être retirés via les chips de l'interface.

## Persistance

Les définitions sont stockées sous `data/dashboards/*.json`. Un dashboard conserve : dataset actif, root dataset, version, filtres, widgets, ordre, tailles, dates de création/mise à jour et version du schéma de définition.

## API

- `GET /api/v1/datasets/{id}/dashboards`
- `POST /api/v1/datasets/{id}/dashboards`
- `GET /api/v1/datasets/{id}/dashboards/{dashboard_id}`
- `DELETE /api/v1/datasets/{id}/dashboards/{dashboard_id}`
- `POST /api/v1/datasets/{id}/dashboards/preview`

## Sécurité et fiabilité

Aucune expression libre n'est évaluée. Les filtres sont interprétés par une liste d'opérateurs autorisés. Les graphiques utilisent `build_visualization` et les KPI sont calculés par pandas / moteurs DataVision.

## Limites actuelles

- le déplacement libre au pixel n'est pas utilisé : la grille reste responsive et les cartes sont réordonnées par glisser-déposer ;
- le cross-filter est actuellement déclenché directement par les graphiques en barres ;
- l'export d'un dashboard entier vers PDF/rapport sera une évolution ultérieure ;
- les dashboards collaboratifs nécessiteront la future couche utilisateurs/permissions.
