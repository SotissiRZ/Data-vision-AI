# DataVision AI v2.73.0 — Model Gateway multi-provider natif

## Objectif

Fermer le gap P1 du CDC §48 en ajoutant deux adaptateurs cloud natifs au gateway existant, sans contourner la gouvernance DataVision.

Providers pris en charge :

- Ollama local / on-premise ;
- API OpenAI-compatible ;
- Anthropic Messages API native ;
- Google Gemini `models.generateContent` natif.

## Invariants de sécurité

Les providers ne reçoivent jamais de permission d'exécuter directement une action DataVision. Le gateway ne fait que générer du texte ou un plan structuré. Les actions restent soumises au Tool Registry, aux contrats Pydantic, au Plan Validator, à la policy assistant, au RBAC/RLS, aux confirmations humaines et à l'audit.

Les providers externes restent bloqués si `allow_external_ai=false` ou si le mode de confidentialité est `local_only`. Les profils workspace utilisent le Secret Vault ; les variables d'environnement API key restent réservées au mode local.

## Sorties structurées

- Anthropic : JSON Schema via `output_config.format` ;
- Gemini : JSON Schema via `generationConfig.responseJsonSchema` avec `responseMimeType=application/json` ;
- OpenAI-compatible : `response_format.json_schema` ;
- Ollama : `format` JSON schema.

## Configuration par environnement

```text
DATAVISION_ANTHROPIC_MODEL=
DATAVISION_ANTHROPIC_BASE_URL=https://api.anthropic.com
DATAVISION_ANTHROPIC_API_KEY=

DATAVISION_GEMINI_MODEL=
DATAVISION_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
DATAVISION_GEMINI_API_KEY=
```

Les mêmes providers peuvent être créés depuis le Centre de contrôle IA avec Secret Vault, ordre de fallback, routage par tâche, budget et télémétrie existants.

## Acceptance

Le gate `MODEL_GATEWAY_ACCEPTANCE` vérifie les deux adaptateurs natifs, les schémas structurés, la confidentialité, le Secret Vault, le frontend, la configuration environnement et les tests d'intégration.
