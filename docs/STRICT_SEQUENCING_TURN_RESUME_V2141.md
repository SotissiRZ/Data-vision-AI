# DataVision v2.14.1 — Strict Sequencing & Turn Resume

## Invariant critique

Une étape qui dépend d'une confirmation humaine bloque désormais entièrement le
plan.

Avant :

```text
step 1 → confirmation requise
step 2 → pouvait encore être traitée
```

Désormais :

```text
step 1 → WAITING_CONFIRMATION
              ↓
          STOP DU PLAN
              ↓
confirmation utilisateur
              ↓
step 1 exécutée
              ↓
step 2
```

Aucune étape downstream n'est exécutée avant la résolution de l'étape courante.

## TurnRun persistant

Chaque demande agentique possède un `AgentTurnRun` :

```text
turn_run_id
session_id
intent
steps
current_step_index
status
critic
final_message
```

Cela permet de reprendre exactement là où l'exécution s'était arrêtée.

## Endpoints

```text
POST /ai/assistant/turn
GET  /ai/assistant/turns/{turn_run_id}
POST /ai/assistant/turns/{turn_run_id}/continue
POST /ai/assistant/turns/{turn_run_id}/cancel
```

## Partage du cycle d'action

Le `/turn` et les endpoints `/actions` utilisent maintenant la même instance
`ActionLifecycleManager` et le même `ActionRunStore`.

Une action proposée par l'orchestrateur peut donc réellement être confirmée
via l'API d'action, puis le TurnRun reprend.

## Production

Les stores mémoire restent des implementations de développement. En production,
ils doivent être remplacés par les stores persistants tenant-aware de DataVision.
