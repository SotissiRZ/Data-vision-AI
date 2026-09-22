# DataVision v2.13.3 — Host Bridge, Action Lifecycle & Realtime

## Pourquoi cette étape

L'agent peut désormais être raccordé proprement aux moteurs existants sans
transformer le LLM en accès direct au code interne.

## Host Bridge

```text
Assistant Tool Registry
        ↓
DataVisionHostBridges
        ├── Data Engine
        ├── Analysis Engine
        ├── Visualization Engine
        ├── ML Engine
        ├── Report Engine
        ├── File Engine
        └── Action Connectors
```

Le patch ne simule aucun de ces moteurs. Lors de la fusion dans le vrai dépôt
v2.12, les services déjà existants doivent implémenter ces protocoles.

## Cycle de vie d'une action

```text
PROPOSED
   ↓ policy
READY ────────────────┐
   ↓                  │
RUNNING               │
   ↓                  │
SUCCEEDED             │
                      │
WAITING_CONFIRMATION  │
   ↓ yes ─────────────┘
   ↓ no
CANCELLED
```

Une action réversible peut ensuite devenir :

```text
SUCCEEDED → ROLLED_BACK
```

`ROLLED_BACK` n'est marqué qu'après exécution réelle du rollback par le moteur
DataVision. Le endpoint fourni ne remplace pas le mécanisme de versioning/undo.

## Realtime

Le backend expose :

```text
GET /ai/assistant/events?workspace_id=...
```

en Server-Sent Events.

Il permet au frontend de recevoir :

```text
assistant.action
assistant.alert
assistant.message
assistant.speaking
```

sans polling agressif.

En déploiement multi-instance, le hub mémoire doit être remplacé par Redis
Pub/Sub, Redis Streams, NATS ou le bus déjà utilisé par DataVision.

## Voix

La couche voix est maintenant explicitement abstraite en deux interfaces :

```text
SpeechToTextProvider
TextToSpeechProvider
```

Le navigateur reste le fallback initial, mais une future édition desktop pourra
utiliser STT/TTS locaux sans modifier le reste de l'agent.

## Endpoints v2.13.3

```text
GET  /ai/assistant/health
GET  /ai/assistant/tools
POST /ai/assistant/observe
POST /ai/assistant/activity/check
POST /ai/assistant/action/check
POST /ai/assistant/plan/validate

POST /ai/assistant/actions
POST /ai/assistant/actions/{id}/confirm
POST /ai/assistant/actions/{id}/execute
GET  /ai/assistant/actions/{id}
POST /ai/assistant/actions/{id}/rollback

GET  /ai/assistant/events
```
