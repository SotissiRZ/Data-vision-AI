# DataVision AI v2.75.0 — Cloud Connectors & CDC ingestion

## Objectif

Étendre **Sources & Refresh** au stockage objet cloud et à l'ingestion CDC log-based sans compromettre les invariants DataVision : secrets chiffrés, lecture seule des systèmes sources, versions de datasets immuables, lineage et reprise déterministe.

## Object storage natif

La v2.75 ajoute trois backends optionnels au catalogue dynamique :

- **S3 / S3-compatible** via `boto3`, avec endpoint facultatif pour MinIO/Ceph, région, credentials explicites ou chaîne IAM ;
- **Google Cloud Storage** via `google-cloud-storage`, avec ADC ou service account JSON chiffré ;
- **Azure Blob Storage** via `azure-storage-blob`, avec account URL, container et credential optionnel.

La découverte liste les objets sans les télécharger. Une source `object` sélectionne une clé précise puis matérialise CSV, JSON/JSONL, Parquet ou XLSX. La taille lue est bornée par `source_options.max_object_mb` (200 MB par défaut, 2 GB maximum explicite).

## CDC log-based gouverné

Une source `refresh_mode=cdc` cible une table ou collection et impose `source_options.primary_key`. Les producteurs peuvent envoyer des enveloppes `debezium-json` ou `canonical` à l'endpoint CDC du workspace.

Le moteur :

1. normalise create/read/update/delete en `upsert` / `delete` ;
2. calcule un `event_id` déterministe lorsqu'il n'est pas fourni ;
3. déduplique les événements déjà appliqués ;
4. maintient un checkpoint **par partition** ;
5. rejette comme stale les offsets numériques/LSN déjà consommés ;
6. applique les mutations par clé primaire ;
7. contrôle le schema drift ;
8. crée une nouvelle version immuable du dataset pour tout lot réellement appliqué ;
9. enregistre batch, événements, checkpoints, refresh run et lineage.

Un replay du même lot terminé est idempotent. Les resume tokens opaques ne sont pas ordonnés artificiellement : seule leur égalité est considérée stale afin de ne pas inventer une sémantique de tri fournisseur.

## API

- `GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/cdc`
- `POST /api/v1/workspaces/{workspace_id}/sources/{source_id}/cdc/events`

Le POST accepte jusqu'à 5 000 événements et un mode `dry_run` qui valide/applique en mémoire sans avancer les checkpoints.

## Garde-fous

- aucune écriture n'est effectuée vers les bases/cloud sources ;
- les secrets restent dans le chiffrement connecteur existant ;
- les sources CDC ne peuvent pas recevoir de schedule périodique ;
- le refresh snapshot classique est refusé pour une source CDC ;
- l'ingestion CDC exige `refresh:run` ; la consultation des checkpoints exige `connectors:read` ;
- les datasets produits restent immuables et rattachés au lineage.

## Limites explicites

DataVision reçoit les événements CDC depuis un producteur log-based (par exemple Debezium/Kafka Connect ou un bridge interne). La v2.75 n'embarque pas un cluster Kafka, ne configure pas les slots PostgreSQL/binlogs MySQL à la place de l'administrateur et ne simule pas un accès aux journaux lorsque l'infrastructure source n'est pas configurée.
