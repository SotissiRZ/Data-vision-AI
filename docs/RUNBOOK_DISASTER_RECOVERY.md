# Runbook — Reprise après sinistre DataVision

## Objectifs

Les objectifs doivent être adaptés au contrat d'exploitation. Baseline recommandée pour la plateforme : **RPO ≤ 24 h** avec la sauvegarde quotidienne du chart, et **RTO ≤ 4 h** lorsque PostgreSQL, le stockage RWX, Vault et les images conteneur sont disponibles dans le site de reprise.

## 1. Déclarer l'incident

1. Geler les déploiements et rotations de clés.
2. Capturer l'état des pods, événements Kubernetes, métriques OpenTelemetry et logs PostgreSQL/Redis/Vault.
3. Identifier la dernière sauvegarde valide et vérifier son SHA-256.
4. Ne pas restaurer par-dessus une plateforme encore en écriture.

## 2. Vérifier une sauvegarde

```bash
python -m app.ops.backup inspect /app/data/backups/datavision-....tar.gz
```

Le manifeste doit indiquer `format=datavision-backup-v1`, la version produit, le backend de base et la migration de schéma.

## 3. Restaurer

Arrêter API et workers, conserver une copie du volume actuel, puis exécuter :

```bash
python -m app.ops.backup restore /app/data/backups/datavision-....tar.gz --confirm
```

La restauration PostgreSQL utilise `pg_restore --clean --if-exists --no-owner`. Une restauration est volontairement refusée sans `--confirm`.

## 4. Réappliquer les migrations

```bash
python -m app.ops.migrate status --json
python -m app.ops.migrate apply --json
```

Ne remettre le trafic que lorsque `/health/startup` et `/health/ready` répondent 200.

## 5. Validation fonctionnelle

- authentification + refresh session ;
- lecture d'un dataset et d'une version immuable ;
- exécution d'une analyse simple ;
- accès à un rapport existant ;
- exécution d'un job worker ;
- vérification du cockpit Entreprise et de l'audit ;
- validation du scrape OpenTelemetry.

## 6. Rotation KMS après compromission

Pour Vault Transit, un owner/admin d'organisation peut lancer la rotation via l'API DataVision. Vérifier que `new_version > previous_version`, puis tester la lecture d'anciens secrets et la création d'un nouveau secret. Vault conserve les anciennes versions nécessaires au déchiffrement selon sa politique de clé.

## 7. Rollback

Si la validation échoue :

1. couper à nouveau le trafic ;
2. restaurer le snapshot pré-reprise du volume/base ;
3. redéployer la dernière image connue saine ;
4. vérifier les migrations et les secrets ;
5. documenter la cause et ne reprendre le trafic qu'après validation.
