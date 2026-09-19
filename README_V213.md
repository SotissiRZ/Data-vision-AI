# DataVision AI — Patch v2.15.0
## Conversational & Voice Agent

Ce patch introduit la couche produit nécessaire pour transformer l'AI Analyst existant en assistant global, flottant, contextuel, vocal et proactif.

> Important : ce package est un **patch d'intégration** construit à partir de l'architecture documentée de DataVision v2.12.0. Il ne prétend pas avoir été fusionné dans le ZIP v2.12.0, car les octets de cette archive n'étaient pas accessibles dans l'environnement courant.

## Objectif

Tout ce que l'utilisateur peut faire dans DataVision doit pouvoir, lorsque raisonnable et autorisé, être demandé à l'agent :

- par texte ;
- par voix ;
- avec le contexte de l'écran courant ;
- avec des fichiers joints ;
- avec propositions d'actions ;
- avec confirmation obligatoire pour les actions sensibles ;
- avec historique et annulation via les mécanismes existants de DataVision.

## Ce que contient ce patch

### Frontend

- bouton flottant global ;
- panneau conversationnel ;
- dictée vocale ;
- synthèse vocale ;
- interruption de la voix de l'agent quand l'utilisateur reprend la parole ;
- mode conversation continue explicitement activable ;
- pièces jointes ;
- bus d'événements contextuels ;
- alertes proactives ;
- adaptateur REST configurable.

### Backend

- modèles Pydantic du contexte agent ;
- endpoint d'observation proactive ;
- moteur de règles déterministe pour les alertes critiques ;
- politique de risque des actions ;
- stockage de contexte en mémoire pour développement ;
- interface prête pour Redis/PostgreSQL dans DataVision Enterprise.

## Arborescence

```text
datavision-v2.13-agent-patch/
├── README_V213.md
├── MIGRATION_GUIDE.md
├── docs/
│   └── CONVERSATIONAL_VOICE_AGENT_V213.md
├── frontend/
│   ├── components/assistant/
│   │   └── FloatingDataVisionAssistant.tsx
│   └── lib/assistant/
│       ├── adapter.ts
│       ├── event-bus.ts
│       └── voice.ts
├── backend/
│   └── app/assistant/
│       ├── __init__.py
│       ├── models.py
│       ├── context_store.py
│       ├── policy.py
│       ├── proactive.py
│       └── router.py
└── tests/
    ├── test_policy.py
    └── test_proactive.py
```

## Version cible

- DataVision v2.12.x
- Next.js / React / TypeScript
- FastAPI / Pydantic
- API par défaut : `http://localhost:8005`
- UI par défaut : `http://localhost:3005`

## Principes de sécurité

1. Le microphone n'est jamais activé automatiquement.
2. Le mode conversation continue doit être activé explicitement.
3. Les suppressions, exports externes, écritures en base et transformations destructives exigent une confirmation.
4. Le LLM n'effectue aucun calcul statistique lui-même.
5. Les alertes critiques sont basées sur des signaux déterministes lorsque possible.
6. Le contexte de l'utilisateur reste tenant-aware.
7. Les actions doivent être auditées par les mécanismes existants de DataVision.


## Ajouts v2.13.1

- Tool Registry gouverné ;
- contrats de risque et permissions par outil ;
- détecteur de blocage fondé sur les événements sémantiques ;
- mémoire de session compacte ;
- exécuteur gouverné prêt à être branché sur le RBAC/RLS v2.12 ;
- helpers React pour déclarer l'écran actif, la sélection et les événements ;
- endpoint catalogue `GET /ai/assistant/tools` ;
- endpoint diagnostic d'activité `POST /ai/assistant/activity/check`.

La version 2.13.1 reste un patch d'intégration tant que les handlers réels du
dépôt v2.12 ne sont pas raccordés au Tool Registry.


## Ajouts v2.13.2

- validation structurée des plans produits par l'agent ;
- refus des outils inconnus ;
- vérification du contexte nécessaire avant exécution ;
- risque canonique provenant du Tool Registry ;
- classification `ready / confirmation_required / deny` ;
- contrats supplémentaires pour inspection de fichiers, fusion et export.


## Ajouts v2.13.3

- Host Bridge officiel vers les moteurs DataVision ;
- cycle complet des actions agentiques ;
- confirmation humaine persistée dans un `ActionRun` ;
- support d'un `rollback_token` fourni par les moteurs réels ;
- canal temps réel SSE par workspace ;
- client realtime frontend ;
- clients frontend du cycle d'action ;
- abstraction STT/TTS prête pour fournisseurs locaux ou cloud ;
- tests des bridges et du cycle d'action.


## Ajouts v2.13.4

- contrats Pydantic des arguments de chaque outil ;
- validation des arguments avant policy/exécution ;
- schémas JSON exposés à l'UI ;
- outils statistiques, régression, AutoML et XAI ;
- premiers outils GIS : reprojection, jointure spatiale, buffer ;
- workflows standards réutilisables ;
- endpoint de validation d'un payload d'outil.


## Ajouts v2.14.0

- Agent Orchestrator Runtime ;
- détection d'intention ;
- interface de Planner Provider ;
- planner déterministe de secours ;
- exécution multi-étapes ;
- Critic déterministe ;
- Recovery Policy avec retry unique des erreurs transitoires ;
- endpoint `/ai/assistant/turn` ;
- client TypeScript de l'orchestrateur ;
- règle stricte anti-invention des variables/couches/cibles absentes.


## Ajouts v2.14.1

- séquencement strict des étapes ;
- arrêt obligatoire dès qu'une confirmation humaine est requise ;
- `AgentTurnRun` persistant ;
- reprise exacte du plan après confirmation ;
- annulation du plan ;
- partage du même ActionRunStore entre orchestrateur et API actions ;
- endpoints GET/continue/cancel des turns ;
- tests de non-exécution des étapes downstream.


## Ajouts v2.14.2

- adaptateur frontend dédié à `/ai/assistant/turn` ;
- confirmation UI → ActionRun → reprise du TurnRun ;
- panneau affichant le plan et l'état des étapes ;
- composant `DataVisionAssistantRoot` prêt à monter dans le layout global ;
- conservation du texte + voix sur le même orchestrateur ;
- aucun upload fictif : endpoint hôte explicitement requis.


## Ajouts v2.15.0

- Model Gateway indépendant du fournisseur ;
- registry de providers ;
- politiques `local_only / prefer_local / allow_external` ;
- consentement externe explicite ;
- provider local configurable ;
- provider générique OpenAI-compatible ;
- projection minimale du contexte ;
- `GatewayPlannerProvider` structuré ;
- sélection du planner via variables d'environnement ;
- endpoints de découverte et prévisualisation du routage ;
- fallback déterministe conservé.
