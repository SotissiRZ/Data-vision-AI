# DataVision AI v2.60 — Exploitation avancée & SRE

La v2.60 complète la résilience HA de v2.59 par une couche SRE observable, automatisable et contrôlée.

## SLO et budgets d’erreur

`backend/app/services/sre_operations.py` agrège les métriques réelles du cockpit Operational Intelligence, calcule le budget d’erreur de disponibilité sur la fenêtre choisie et détecte les breaches de disponibilité, latence P95, succès des jobs, refresh, backlog Redis, fraîcheur des sauvegardes et ancienneté du dernier restore drill.

Les endpoints `/workspaces/{id}/operational/sre` exposent la posture courante. Les snapshots peuvent être persistés et les alertes peuvent être propagées vers Governed Actions sous l’événement `sre_slo_breach`. L’émission automatique par le worker est opt-in via `SRE_AUTO_ALERTS_ENABLED`.

## Sauvegardes objet S3-compatible

Le backup local reste la source primaire. Lorsque `BACKUP_OBJECT_STORE_PROVIDER=s3_compatible`, DataVision peut uploader les archives vers un endpoint S3-compatible avec AWS Signature V4, checksum SHA-256 en metadata et support des endpoints on-prem type MinIO/Ceph.

Aucun SDK S3 additionnel n’est requis : l’implémentation s’appuie sur `httpx`, déjà présent dans le runtime.

## Restore drills

Le manifest `datavision-backup-v2` contient les checksums de chaque fichier. `python -m app.ops.backup drill-latest` extrait l’archive dans un staging temporaire, bloque les chemins dangereux et les liens, vérifie les checksums et exécute `pg_restore --list` si disponible pour un dump PostgreSQL. Aucune donnée de production n’est écrasée pendant le drill.

Le chart Helm planifie un restore drill hebdomadaire par défaut.

## Autoscaling worker piloté par la file

Le mode historique HPA CPU reste le défaut. En positionnant `autoscaling.worker.mode=keda_redis`, le chart installe un `ScaledObject` KEDA basé sur la longueur de la liste Redis `datavision:jobs`. Min/max, seuil d’activation, seuil de scaling et authentification Redis sont configurables.

## Chaos contrôlé

`SRE_CHAOS_ENABLED=false` par défaut. Les scénarios exposés sont volontairement limités : snapshot de readiness et backlog synthétique composé de jobs `sre_probe` courts, sans accès dataset et sans retries. L’intensité est bornée par `SRE_CHAOS_MAX_PROBE_JOBS`.

## Commandes utiles

```bash
python -m app.ops.backup create --label manual
python -m app.ops.backup upload /app/data/backups/<archive>.tar.gz
python -m app.ops.backup drill-latest
python scripts/sre_acceptance.py --root . --check
```
