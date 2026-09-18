# Guide d'intégration v2.13

## 1. Copier les fichiers

Copier :

```text
frontend/components/assistant/*
frontend/lib/assistant/*
backend/app/assistant/*
```

dans les emplacements équivalents du dépôt DataVision.

## 2. Monter le routeur FastAPI

Dans le point d'entrée FastAPI existant :

```python
from app.assistant.router import router as assistant_router

app.include_router(assistant_router)
```

Le routeur expose :

```text
POST /ai/assistant/observe
POST /ai/assistant/action/check
GET  /ai/assistant/health
```

## 3. Monter le bouton flottant dans le layout global

Dans le layout React/Next racine :

```tsx
import { FloatingDataVisionAssistant } from "@/components/assistant/FloatingDataVisionAssistant";
import { createRestAssistantAdapter } from "@/lib/assistant/adapter";

const assistantAdapter = createRestAssistantAdapter({
  apiBaseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8005",
  chatPath: "/ai/chat",
  observePath: "/ai/assistant/observe",
});
```

Puis rendre :

```tsx
<FloatingDataVisionAssistant
  adapter={assistantAdapter}
  locale="fr-FR"
/>
```

## 4. Brancher le contexte applicatif

Chaque module important doit publier son contexte.

Exemple après sélection d'un dataset :

```ts
import { assistantEventBus } from "@/lib/assistant/event-bus";

assistantEventBus.setContext({
  workspaceId,
  route: "/data/explore",
  screen: "Data Explorer",
  activeDatasetId: dataset.id,
  selectedEntity: {
    type: "dataset",
    id: dataset.id,
    label: dataset.name,
  },
});
```

## 5. Publier les événements

Exemple qualité :

```ts
assistantEventBus.emit({
  type: "dataset.quality.issue",
  severity: "warning",
  payload: {
    column: "age",
    rule: "missing_ratio",
    value: 0.174,
  },
});
```

Exemple fuite de données :

```ts
assistantEventBus.emit({
  type: "ml.leakage.detected",
  severity: "critical",
  payload: {
    target: "churn",
    feature: "final_churn_status",
  },
});
```

## 6. Raccorder l'AI Analyst existant

Le patch suppose que DataVision v2.12 possède déjà son endpoint conversationnel ou son orchestrateur.

L'adaptateur REST envoie :

```json
{
  "message": "Analyse ce dataset",
  "context": {},
  "attachmentIds": []
}
```

Adaptez `chatPath` et, si nécessaire, la fonction `normalizeChatResponse()` de `frontend/lib/assistant/adapter.ts` au contrat réel du v2.12.

## 7. Uploads de fichiers

Le patch n'invente pas un endpoint d'upload.

Branchez le chemin réel de DataVision :

```ts
createRestAssistantAdapter({
  apiBaseUrl,
  chatPath: "/ai/chat",
  observePath: "/ai/assistant/observe",
  uploadPath: "/<endpoint-upload-réel>",
});
```

Sans `uploadPath`, le bouton de pièce jointe reste visible mais l'interface indique que le connecteur d'upload doit être configuré.

## 8. Politiques d'action

Avant toute action agentique :

```text
Agent propose action
      ↓
POST /ai/assistant/action/check
      ↓
allow / confirmation_required / deny
      ↓
orchestrateur existant
      ↓
audit + versioning + undo
```

Ne contournez pas les contrôles RBAC/RLS existants.

## 9. Voice

La première couche utilise les capacités vocales du navigateur :

- Web Speech Recognition si disponible ;
- `speechSynthesis` pour la synthèse vocale.

Pour une version desktop/local plus robuste, remplacez ensuite cette couche par des providers :

```text
STTProvider
├── Browser
├── Local Whisper / faster-whisper
└── Cloud configurable

TTSProvider
├── Browser
├── Local TTS
└── Cloud configurable
```

L'interface `voice.ts` a volontairement été isolée pour permettre ce remplacement.

## 10. Validation requise avant de déclarer v2.13 terminée

- intégration avec le vrai `/ai/chat` ;
- tests E2E du bouton flottant ;
- tests microphone sur Chrome/Edge ;
- vérification des permissions navigateur ;
- test du barge-in ;
- test RBAC/RLS ;
- audit de chaque action ;
- test de rollback ;
- test Docker frontend/backend ;
- vérification que l'agent n'envoie pas des données privées à un provider externe sans configuration.
