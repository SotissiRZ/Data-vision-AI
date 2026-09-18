# DataVision v2.14.2 — Floating UI ↔ Orchestrator

## Changement principal

Le bouton flottant peut maintenant utiliser directement :

```text
POST /ai/assistant/turn
```

au lieu d'un ancien endpoint conversationnel générique.

## Flux réel

```text
Utilisateur parle/écrit
       ↓
FloatingDataVisionAssistant
       ↓
createOrchestratorAssistantAdapter
       ↓
/ai/assistant/turn
       ↓
Intent → Plan → Validation → Execution
       ↓
réponse + étapes + critic
       ↓
UI
```

## Confirmation

Quand une étape attend une confirmation :

```text
AgentTurn
   ↓
ActionRun waiting_confirmation
   ↓
bouton "Confirmer"
   ↓
POST /actions/{id}/confirm
   ↓
POST /turns/{turn}/continue
   ↓
reprise du plan
```

Le frontend ne peut donc pas contourner le backend en exécutant directement
l'outil.

## Visualisation du plan

Le panneau affiche désormais l'état de chaque étape :

```text
✓ succeeded
! waiting_confirmation
… running
✕ failed
○ ready/planned
– skipped
```

## Intégration layout

Dans le layout authentifié :

```tsx
import { DataVisionAssistantRoot } from "@/components/assistant/DataVisionAssistantRoot";

export default function Layout({ children }) {
  return (
    <>
      {children}
      <DataVisionAssistantRoot />
    </>
  );
}
```

## Upload

L'upload n'est toujours pas simulé.

`NEXT_PUBLIC_ASSISTANT_UPLOAD_PATH` doit pointer vers le vrai endpoint DataVision
lors de la fusion avec le dépôt principal.
