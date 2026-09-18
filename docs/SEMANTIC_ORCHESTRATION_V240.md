# Semantic Orchestration — DataVision AI v2.4.0

## Objectif

La v2.4 transforme la couche sémantique de v2.3 en **runtime transversal**. Elle n'est plus confinée au Semantic Studio : elle devient le contrat commun utilisé par NLQ, AI Analyst et Dashboard Builder.

## 1. NLQ semantic-first

Pipeline :

```text
Question métier
  ↓
Normalisation FR/EN
  ↓
Résolution métrique / synonymes
  ↓
Résolution dimensions / hiérarchies
  ↓
Résolution time intelligence
  ↓
Semantic Query Engine v2
  ↓
Résultat tabulaire + provenance
```

Le planificateur ne calcule aucune valeur. Il résout uniquement l'intention métier. Les valeurs sont calculées par `query_semantic_metric`.

### Priorité

1. si une métrique sémantique est reconnue, utiliser le moteur sémantique ;
2. sinon, conserver le traducteur SQL local existant.

Cela préserve la compatibilité avec les questions historiques tout en ajoutant le multi-table.

## 2. AI Analyst semantic-first

Le Tool Registry expose maintenant `semantic_query`.

Une question de métrique simple produit :

```text
profile
quality
semantic_query
critic
```

Les demandes explicitement statistiques, prédictives ou temporelles conservent leurs moteurs spécialisés.

## 3. Dashboard sémantique

Deux nouveaux widgets :

- `semantic_kpi` ;
- `semantic_chart`.

Configuration conceptuelle :

```json
{
  "type": "semantic_chart",
  "config": {
    "metric_id": "revenue",
    "dimension": "category",
    "hierarchy_id": "catalog",
    "hierarchy_level": 0,
    "chart_type": "bar"
  }
}
```

Les filtres peuvent cibler une colonne physique ou une dimension sémantique.

## 4. Cross-filter multi-table

Un filtre sur `product.category = A` est exécuté dans le graphe sémantique. Après filtrage, seules les colonnes `base__*` sont reprojetées vers un DataFrame de faits. Les KPI et graphiques physiques héritent donc du même périmètre.

Cette opération reste sûre car seules les relations N:1 et 1:1 sont autorisées dans l'exécution automatique.

## 5. Drill-down

Une hiérarchie stockée dans le modèle sémantique devient exécutable dans le Dashboard Builder. Le backend retourne un objet `drill` avec :

- niveau courant ;
- dimension courante ;
- dimension suivante ;
- niveau suivant.

Le frontend ajoute le filtre du niveau courant puis recharge le widget au niveau suivant.

## 6. Jointures multi-hop

v2.3 savait relier la table de faits à une dimension directe. v2.4 calcule maintenant la fermeture de jointure nécessaire pour atteindre une table cible via des tables intermédiaires.

Exemple :

```text
sales.product_id
  → product.product_id
  → product.category_id
  → category.category_id
  → category.sector
```

Le moteur refuse toujours les chemins non atteignables et les relations présentant un risque de fan-out.

## 7. Limites actuelles

- pas de relation N:N automatique ;
- pas encore de semantic SQL compiler physique complet ;
- pas encore de cache distribué des requêtes sémantiques ;
- drill-down actuellement séquentiel, pas de drill-through vers une page dédiée ;
- les formules calculées restent arithmétiques et ne constituent pas encore un langage DAX-like.

Ces limites sont explicites afin de préserver la fiabilité analytique.
