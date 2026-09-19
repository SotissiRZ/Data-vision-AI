# DataVision v2.25.0 — Feature Store & Serving

## 1. Feature Set

Un Feature Set est un contrat déclaratif versionné.

Il référence un dataset DataVision existant et sélectionne :

```text
entity keys
event time
features
```

Aucune fonction arbitraire n'est exécutée.

## 2. Schema Contract

Le hash du schéma est calculé sur une représentation JSON canonique contenant :

```text
name
dtype
family
nullable
```

Une matérialisation dont le schéma ne correspond plus au contrat est refusée.

## 3. Materialization

Une matérialisation crée un nouveau dataset root immuable avec une provenance :

```text
type = feature_store_materialization
feature_set_id
workspace_id
source_dataset_id
source_dataset_version
schema_sha256
```

En Enterprise, le nouveau dataset est lié au workspace.

## 4. Model Feature Contract

Le Feature Contract d'un modèle vient du dataset réellement référencé par sa
Model Card.

Il est donc dérivé des données d'entraînement et non réinventé dans l'UI.

## 5. Deployment interne

Un deployment contient :

```text
endpoint_key
model_key
primary_model_id
secondary_model_id
strategy
traffic_percent
status
feature_contract
revision_no
```

Le primaire doit être `production/champion`.

Un challenger shadow/canary doit appartenir au même `model_key` et être
`staging` ou `production`.

## 6. Shadow

Le résultat du challenger n'est pas substitué à la réponse primaire.

DataVision conserve uniquement un résumé :

- disagreement rate pour classification ;
- mean/max absolute prediction difference pour régression.

## 7. Canary

Le modèle sélectionné est déterminé par :

```text
sha256(request_id) → bucket → traffic_percent
```

Le routage est donc stable pour un même request ID.

## 8. Serving telemetry

Les observations brutes ne sont pas stockées.

La table `model_serving_requests` conserve seulement métadonnées, hash et
résumé.

## 9. Rollback

Le rollback est un acte gouverné.

Si l'ancien champion est retired :

```text
retired
  ↓
staging
  ↓
production
```

Les préconditions de production du Model Registry sont donc réévaluées.

## 10. Batch Scoring

Le batch scoring produit une nouvelle version de dataset au lieu d'écraser les
données d'entrée.

En classification, les colonnes suivantes peuvent être créées :

```text
prediction
prediction_proba_<class>
```

## 11. Limites explicites

v2.25 ne revendique pas encore :

- Redis/Feast online feature store ;
- faible latence multi-région ;
- autoscaling Kubernetes ;
- Vertex AI Endpoint ;
- SageMaker Endpoint ;
- Azure ML Endpoint ;
- service mesh ;
- model gateway public multi-tenant dédié ;
- GPU serving.

Ces capacités nécessitent un runtime de déploiement externe réel.
