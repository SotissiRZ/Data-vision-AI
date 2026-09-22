# DataVision v2.24.0 — Model Registry & MLOps

## Objectif

Cette version introduit une couche MLOps persistante au-dessus des artefacts
`.joblib` et des Model Cards existants.

## Registry

Tables principales :

- `model_registry_entries` ;
- `model_registry_events` ;
- `model_monitoring_runs` ;
- `model_monitor_schedules` ;
- `model_retraining_policies` ;
- `model_retraining_requests`.

## Versionnement

`model_key` :

```text
{dataset_root}:{target}:{task}
```

`version_no` est incrémenté par `model_key` dans le workspace courant.

## Stages

Transitions autorisées :

```text
draft -> staging | retired
staging -> draft | production | retired
production -> retired
retired -> staging
```

La production est mono-champion par `model_key` et workspace.

## Production Gate

Mode Entreprise : certification active obligatoire.

Tous modes : un Responsible AI Gate explicitement bloqué empêche la promotion.

## Intégrité

À l'enregistrement :

```text
SHA256(model.joblib)
SHA256(model.card.json)
```

En draft/staging, les métadonnées de gouvernance peuvent encore enrichir la
Model Card. Les hashes sont resynchronisés lors d'une transition gouvernée.
Après promotion, un changement de bytes d'un artefact de production est exposé
comme `production_artifact_integrity_changed` lors du monitoring.

## Monitoring

Le monitoring calcule :

- métriques de performance courantes si la cible est disponible ;
- dégradation relative de la métrique primaire ;
- drift par feature ;
- statut `healthy` ou `degraded` ;
- blockers et warnings ;
- provenance dataset de référence / dataset courant.

### Drift numérique

```text
abs(mean_current - mean_reference) / pooled_std
```

### Drift catégoriel

```text
Total Variation Distance
```

## Scheduler

`model_monitor_schedules` est réclamé atomiquement par le worker via une mise à
jour conditionnelle de `next_run_at`.

Le job queue reçoit :

```text
job_type = model_monitor
```

Le worker ne réentraîne jamais le modèle dans ce job.

## Retraining

La politique de réentraînement est une politique opérationnelle configurable.
Elle ne devient éligible qu'après `min_rows` observations de monitoring.

Si les seuils sont dépassés :

```text
monitoring evidence
       ↓
retraining policy
       ↓
recommendation
       ↓
optional traceable request
```

Une requête ne lance aucun entraînement automatiquement.

## Limites explicites v2.24

Cette version ne revendique pas encore :

- déploiement de modèles vers Kubernetes/SageMaker/Vertex AI ;
- serving autoscalé externe ;
- shadow traffic réel ;
- A/B testing de trafic de production ;
- feature store distribué ;
- réentraînement automatique sans approbation humaine ;
- rollback d'un endpoint de serving externe.

Le Registry gère le lifecycle DataVision et les preuves MLOps, sans simuler un
système de déploiement cloud qui n'est pas connecté.
