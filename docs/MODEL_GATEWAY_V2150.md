# DataVision v2.15.0 — Model Gateway

## Objectif

Découpler DataVision de tout fournisseur IA unique.

```text
Agent Orchestrator
       ↓
PlannerProvider
       ↓
Model Gateway
       ├── Local provider
       ├── OpenAI-compatible provider
       ├── Anthropic natif
       └── Gemini natif
```

## Invariant de sécurité

Le modèle peut proposer un plan. Il ne peut jamais exécuter directement une
opération DataVision.

Tout plan traverse encore :

```text
Tool Registry
→ Pydantic contracts
→ Plan Validator
→ Assistant Policy
→ RBAC / RLS / Column Security
→ ActionRun
→ Confirmation éventuelle
→ Host Bridge
```

## Modes de confidentialité

### `local_only`
Seuls les providers déclarés `local` sont éligibles.

### `prefer_local`
Le local est prioritaire. Un provider externe reste interdit tant que
`allow_external_ai=false`.

### `allow_external`
Un provider externe peut être choisi uniquement si l'autorisation externe
est explicitement activée.

## Projection du contexte

Le planner reçoit un contexte sémantique compact.

Le projecteur fourni n'envoie jamais :
- les lignes du dataset ;
- `uiState` brut ;
- des valeurs d'échantillon.

Pour un provider externe, il est également possible de masquer les noms des
colonnes sélectionnées.

## Configuration

### Planner
```text
DATAVISION_AI_PLANNER_MODE=deterministic|gateway
DATAVISION_AI_PRIVACY_MODE=local_only|prefer_local|allow_external
DATAVISION_AI_ALLOW_EXTERNAL=false
DATAVISION_AI_PREFERRED_PROVIDER=
DATAVISION_AI_EXTERNAL_COLUMN_NAMES=true
DATAVISION_AI_EXTERNAL_MAX_EVENTS=5
```

### Provider local
```text
DATAVISION_OLLAMA_MODEL=
DATAVISION_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

### Provider OpenAI-compatible
```text
DATAVISION_OPENAI_COMPATIBLE_BASE_URL=
DATAVISION_OPENAI_COMPATIBLE_MODEL=
DATAVISION_OPENAI_COMPATIBLE_API_KEY=
```

### Provider Anthropic natif
```text
DATAVISION_ANTHROPIC_MODEL=
DATAVISION_ANTHROPIC_BASE_URL=https://api.anthropic.com
DATAVISION_ANTHROPIC_API_KEY=
```

### Provider Gemini natif
```text
DATAVISION_GEMINI_MODEL=
DATAVISION_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
DATAVISION_GEMINI_API_KEY=
```

Les profils créés dans le Centre de contrôle IA peuvent utiliser ces quatre types.
En workspace Entreprise, les clés externes restent référencées via le Secret Vault.

Aucun secret n'est stocké dans le code.

## GatewayPlannerProvider

Le planner demande une sortie structurée :

```json
{
  "steps": [
    {
      "tool": "profile_dataset",
      "label": "Profiler",
      "reason": "Comprendre les données",
      "args": {}
    }
  ]
}
```

Les outils inconnus sont supprimés, puis les outils restants sont revalidés
par les couches déterministes.

## Fallback

Le `DeterministicPlanner` reste le mode par défaut.

Si le mode gateway est configuré mais que son initialisation échoue, DataVision
revient au planner déterministe local. Cette dégradation n'autorise jamais un
autre provider externe de manière implicite.

## API

```text
GET  /ai/assistant/models/providers
POST /ai/assistant/models/route
```

L'UI peut donc afficher le provider qui serait sélectionné avant d'autoriser
un traitement externe.
