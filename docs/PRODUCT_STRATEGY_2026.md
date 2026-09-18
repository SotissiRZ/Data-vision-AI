# DataVision AI — Product Strategy 2026

## North Star

DataVision doit réduire le nombre de ruptures dans un projet analytique. Un utilisateur ne devrait pas devoir passer d'un outil de préparation à un logiciel statistique, puis à un notebook, puis à un BI tool, puis à un chatbot, puis à un générateur de rapport pour répondre correctement à une question.

La North Star produit est : **temps nécessaire pour passer d'une donnée brute à un résultat vérifié et reproductible**.

## Architecture d'expérience v2

L'interface principale est organisée autour de six intentions :

- **Vue d'ensemble** : état du dataset, qualité, confiance, insights et playbooks ;
- **Données** : aperçu, qualité, préparation, statistiques descriptives ;
- **Analyser** : visualisation, tests, SQL/NLQ, régression, ANOVA, ACP, clustering ;
- **Modéliser** : AutoML, forecasting, anomalies, XAI, prédictions ;
- **Décider** : AI Analyst, Semantic Studio, Decision Lab, Trust Center ;
- **Publier** : dashboards et rapports.

Cette structure évite une barre latérale plate de plus de vingt entrées. Une sous-navigation contextuelle expose uniquement les outils utiles dans l'espace actif.

## Principe de confiance

Aucun résultat numérique n'est considéré « publié » sans :

1. dataset et version ;
2. moteur de calcul ;
3. paramètres ;
4. résultat brut ;
5. validation / guardrail ;
6. interprétation ;
7. provenance.

## Semantic-first AI

La couche sémantique est le contrat entre les données physiques et les utilisateurs. Les agents doivent résoudre une question vers des métriques et dimensions gouvernées avant d'exécuter SQL/statistiques/ML lorsque cette information existe.

Une métrique peut comporter : nom, label, colonne, agrégation, unité, description, synonymes et certification.

## Decision Intelligence

La décision doit être séparée en trois niveaux :

- **Observation** : ce qui est mesuré dans les données ;
- **Prédiction** : ce qu'un modèle estime ;
- **Scénario** : comment un modèle réagit à une hypothèse.

Le produit ne doit jamais présenter automatiquement un scénario prédictif comme un effet causal.

## Roadmap prioritaire

### P0 — fiabilité enterprise

Authentification, organisations/workspaces, RBAC/RLS, secrets, audit log consolidé, jobs asynchrones, tests E2E.

### P1 — métriques proactives

Alertes, seuils, changements significatifs, abonnements, scheduler, digest et webhooks.

### P1 — semantic layer v2

Relations multi-tables, hiérarchies, time intelligence, formules métriques, métriques dérivées, validation et approbation.

### P1 — action layer

Actions externes avec permissions et Human-in-the-loop : webhook, ticketing, messagerie, CRM et APIs métier.

### P2 — causal & optimization

Causal inference explicite, expérimentation, optimization sous contraintes et recommandation robuste. Ces fonctions doivent rester distinctes des simulations de modèle prédictif.
