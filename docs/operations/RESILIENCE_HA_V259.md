# DataVision AI v2.59 — Résilience & exploitation HA

La v2.59 transforme le packaging Kubernetes de v2.58 en socle d'exploitation haute disponibilité.

## Capacités livrées

- probes séparées `startup`, `readiness`, `liveness` ;
- readiness conditionnée par l'état des migrations de schéma ;
- migrations versionnées et Job Helm `pre-install,pre-upgrade` ;
- rolling update sans indisponibilité API/web (`maxUnavailable: 0`) ;
- PodDisruptionBudget API/web ;
- HorizontalPodAutoscaler API/web/worker ;
- répartition des réplicas API/web entre nœuds ;
- sauvegarde planifiée par CronJob avec `concurrencyPolicy: Forbid` ;
- sauvegardes tar.gz manifestées et vérifiées SHA-256 ;
- dump/restauration PostgreSQL via `pg_dump` / `pg_restore` ;
- rotation Vault Transit en ligne, avec journal d'audit ;
- runbook de reprise après sinistre.

## Migrations

En Kubernetes, `config.schemaAutoMigrate=false` par défaut et le Job Helm applique les migrations avant le rollout. Le statut est inspectable avec :

```bash
python -m app.ops.migrate status --json
python -m app.ops.migrate apply --json
```

En Docker Compose, `SCHEMA_AUTO_MIGRATE=true` reste le comportement par défaut pour conserver la simplicité d'installation locale. Une exécution explicite est possible :

```bash
docker compose --profile ops run --rm migrate
```

## Sauvegarde

```bash
python -m app.ops.backup create --label manual
# ou
docker compose --profile ops run --rm backup
```

Les archives sont conservées sous `DATA_ROOT/backups/` et limitées par `BACKUP_RETENTION_COUNT`.
