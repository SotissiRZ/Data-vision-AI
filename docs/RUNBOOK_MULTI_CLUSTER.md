# Runbook — Observabilité distribuée et bascule multi-cluster

## Principes de sécurité

La bascule DataVision est volontairement en deux phases : **plan** puis **confirmation**. Un plan contient un préflight, expire rapidement et renvoie un jeton de confirmation qui n'est jamais stocké en clair. En mode `control_plane_only`, DataVision met à jour son état de control plane mais ne prétend pas avoir modifié le DNS, le load balancer ou le routage externe. En mode `webhook`, l'orchestrateur externe reçoit une requête HMAC-SHA256 signée.

## Vérifier la topologie

```bash
python -m app.ops.runbook topology <workspace_id>
```

## Vérifier les réplications cross-region

```bash
python -m app.ops.runbook verify-replications <backup_id>
```

Une réplication utilisable pour une bascule doit être marquée `verification_status=verified`. La vérification distante utilise une requête HEAD et le metadata `x-amz-meta-sha256` écrit lors de l'upload.

## Préparer une bascule

```bash
python -m app.ops.runbook failover-plan <workspace_id> <cluster_cible> \
  --actor-id <user_id> --reason "maintenance région primaire"
```

Conserver le `confirmation_token` retourné : il n'est pas persisté en clair et expire selon `MULTI_CLUSTER_CONFIRMATION_TTL_MINUTES`.

## Confirmer la bascule

```bash
python -m app.ops.runbook failover-confirm <workspace_id> <plan_id> \
  --actor-id <user_id> --token <confirmation_token>
```

En production, utiliser `MULTI_CLUSTER_FAILOVER_EXECUTOR=webhook` seulement avec un orchestrateur de trafic explicitement configuré. Le webhook reçoit `traceparent`, `X-Request-ID` et `X-DataVision-Signature`.

## Examiner une trace distribuée

Chaque réponse API expose `X-Trace-ID`, `Traceparent` et `X-Request-ID`. Les événements DataVision sont consultables via :

```text
GET /api/v1/workspaces/{workspace_id}/operational/traces/{trace_id}
```

## Rollback

Créer un **nouveau** plan vers l'ancien cluster primaire. Ne réutiliser ni un plan confirmé ni son jeton. Vérifier d'abord qu'une réplication récente et `verified` est disponible dans la région cible du rollback.
