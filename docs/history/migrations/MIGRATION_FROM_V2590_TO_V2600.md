# Migration v2.59.0 → v2.60.0

1. Appliquer les migrations `python -m app.ops.migrate apply --json`.
2. Conserver `BACKUP_OBJECT_STORE_PROVIDER=disabled` si aucun stockage objet n’est configuré.
3. Pour S3-compatible, définir endpoint, bucket, region et credentials dans le secret d’exécution ; activer `BACKUP_OBJECT_STORE_AUTO_UPLOAD=true` seulement après un upload manuel réussi.
4. Conserver `autoscaling.worker.mode=cpu` si KEDA n’est pas installé. Passer à `keda_redis` uniquement sur un cluster avec les CRD KEDA.
5. Exécuter `python -m app.ops.backup drill-latest` avant d’activer le CronJob de restore drill en production.
6. Les exercices de chaos restent désactivés tant que `SRE_CHAOS_ENABLED=false`.
