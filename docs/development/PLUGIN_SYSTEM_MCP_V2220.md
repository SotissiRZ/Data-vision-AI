# DataVision v2.22.0 — Plugin System & MCP

## Objectif

Étendre DataVision sans permettre à une extension de contourner le cœur métier,
le RBAC ou la Safety Policy.

## Architecture

```text
Workspace Entreprise
        ↓
Plugin installation
        ↓
Manifest validé / MCP tools/list
        ↓
plugin_tools metadata
        ↓
Runtime Plugin Registry
        ↓
AssistantToolRegistry
        ↓
GovernedToolExecutor
        ↓
confirmation + RBAC
        ↓
HTTP/MCP call
```

## Protocoles

### MCP HTTP

Séquence utilisée pour la découverte :

```text
initialize
notifications/initialized
tools/list
```

Pour l'exécution :

```text
initialize
notifications/initialized
tools/call
```

Un `Mcp-Session-Id` renvoyé par le serveur est réutilisé pendant la séquence.
Les réponses JSON et un payload JSON issu d'un flux SSE simple sont gérés.

### HTTP JSON

Un tool comporte :

```json
{
  "name": "search",
  "description": "Recherche externe",
  "input_schema": {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": false
  },
  "method": "POST",
  "path": "/search"
}
```

Le schema est validé en Draft 2020-12.

## Risque

Le champ `risk` du manifest est informatif. Le runtime enregistre tous les tools
plugins avec le risque canonique `external`.

Un manifest ne peut donc pas transformer une action distante en lecture sûre.

## Isolation workspace

Le nom runtime est de la forme :

```text
plugin.<plugin_key>.<remote_tool>__<workspace_hash>
```

Le planner ne reçoit que les tools du workspace courant. Le GovernedToolExecutor
refuse en plus tout mismatch de workspace avant exécution.

## Secret Vault

Les modes d'authentification supportés sont `none`, `bearer` et `api_key`.
Seul un `secret_id` est enregistré dans le plugin. La valeur est résolue au
moment de l'appel par le Secret Vault existant.

## SSRF

`network_scope=public` :
- HTTPS requis ;
- IP non globale refusée ;
- loopback, link-local, multicast et metadata IP refusées ;
- redirects désactivés.

`network_scope=private` :
- HTTP interne autorisé ;
- loopback, link-local, multicast et metadata IP restent refusées.

## Données transmises

Le plugin reçoit toujours les arguments explicitement validés par son JSON
Schema.

`context_policy=none` : aucun contexte ajouté.

`context_policy=semantic` : uniquement des références sémantiques, jamais les
lignes du dataset, jamais `uiState`, jamais les événements complets.

## Audit

`plugin_runs` stocke uniquement :
- plugin/tool ;
- user/workspace ;
- statut ;
- noms des clés d'arguments ;
- durée ;
- erreur bornée.

Les valeurs des arguments et les résultats complets ne sont pas archivés dans
cette table.

## Limites

Pas d'exécution locale de packages plugins, pas de MCP stdio, pas de marketplace
ni signature cryptographique de package dans v2.22. Les resources/prompts MCP et
le sampling MCP ne sont pas encore exposés à l'assistant.
