# DataVision AI v2.6 — Collaboration & Review

## Objectif

Ajouter un **human-in-the-loop organisationnel** entre le calcul analytique et la publication/décision. La collaboration ne doit pas être un simple fil de commentaires : elle doit produire une décision traçable, attribuée et révisable.

## Ressources revues

- dataset ;
- métrique sémantique ;
- analyse ;
- dashboard ;
- rapport ;
- modèle ;
- visualisation.

## Modèle de données

### `review_items`
Contient la ressource, son snapshot/version, owner, reviewer, priorité, échéance, statut et décision.

### `review_comments`
Discussion persistante avec mentions et état résolu/non résolu.

### `review_events`
Historique append-only des décisions et transitions.

### `collaboration_notifications`
Notifications individuelles : assignation, mention, commentaire, transition, certification.

### `resource_certifications`
Certification gouvernée d'une ressource approuvée avec expiration optionnelle et révocation.

## Workflow

```text
draft
  └─ submit → in_review
               ├─ approve → approved
               └─ request_changes → changes_requested
                                         └─ reopen → in_review
```

`archive` est réservé à l'administration du workflow.

## Séparation approbation / certification

Une **approbation** signifie que le reviewer a validé la ressource dans le contexte de la revue.
Une **certification** signifie qu'un Owner/Admin désigne cette ressource comme référence gouvernée jusqu'à expiration ou révocation.

Cette séparation évite de confondre peer review et gouvernance métier.

## RBAC

- Owner/Admin : administration complète + certification ;
- Data Scientist : soumission + peer review/approval ;
- Analyst : soumission + commentaires ;
- Viewer : lecture + commentaires.

## Mentions

Le moteur résout les mentions à partir des membres du workspace. Les notifications sont persistées et marquées lues explicitement.

## UX

Le Review Center se compose de trois zones :

1. file de revues filtrable ;
2. fiche de décision avec discussion/historique ;
3. notifications et certifications actives.

L'interface évite les gros tableaux : priorité à la file de travail, aux statuts, à l'ownership et aux décisions.

## Limites v2.6

- pas encore de WebSocket temps réel ;
- pas d'email/Slack/Teams sortant ;
- pas de règle automatique "rapport publiable uniquement si approuvé" ;
- pas encore de comparaison visuelle diff entre deux versions d'un dashboard/rapport ;
- pas de signature électronique réglementaire.

Ces éléments restent explicitement planifiés.
