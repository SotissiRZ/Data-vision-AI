# DataVision AI — Benchmark marché 2026

Date de recherche : **18 septembre 2026**.

Ce document synthétise une revue de produits et documentations publiques de Power BI / Microsoft Fabric, Tableau, Looker, ThoughtSpot, Dataiku, Alteryx, Metabase et Apache Superset. Il ne prétend pas mesurer la fréquence réelle d'usage de chaque fonction chez les clients de ces éditeurs : les éléments classés « récurrents » sont ceux qui reviennent de façon systématique dans les offres et documentations étudiées.

## 1. Fonctions devenues indispensables

Les capacités suivantes se retrouvent de manière récurrente dans les plateformes modernes :

1. **Couche sémantique / métriques gouvernées** : définitions métier, dimensions, synonymes, relations, sécurité et logique commune à tous les rapports et agents.
2. **Dashboards interactifs** : filtres, cross-filtering, drill-down, exploration, KPI et vues personnalisables.
3. **SQL + self-service** : exploration visuelle mais possibilité de descendre au SQL, de vérifier les requêtes et de conserver la traçabilité.
4. **Analyse conversationnelle / NLQ** : question en langage naturel, génération de requête, visualisation et explication.
5. **Qualité, préparation et versioning** : la donnée doit être préparée, contrôlée et reproductible avant l'IA.
6. **Automatisation et suivi de métriques** : alertes, abonnements, changements importants et diffusion dans le flux de travail.
7. **Gouvernance / sécurité / provenance** : RBAC/RLS, audit, lineage, métriques certifiées et contrôle de ce qui est montré à l'IA.
8. **ML / AutoML / explicabilité** pour les plateformes data-science avancées.
9. **Agents outillés** : l'agent ne se limite plus à produire du texte ; il appelle des outils, contrôle les résultats et peut déclencher des actions.

## 2. Ce que montrent les leaders

| Produit | Forces observées | Limites / compromis publics utiles à DataVision |
|---|---|---|
| Power BI / Fabric | Modèles sémantiques, BI enterprise, Copilot, DAX, gouvernance | Microsoft insiste sur la préparation du modèle pour l'IA et reconnaît que des modèles mal préparés peuvent produire des réponses faibles ou trompeuses. Les sorties Copilot sont non déterministes. |
| Tableau | Visual analytics très forte, Tableau Pulse, métriques suivies, insights contextuels distribués par email/Slack | L'expérience Pulse est centrée sur des métriques définies ; les capacités conversationnelles dépendent du contexte disponible. |
| Looker | LookML / couche sémantique gouvernée, sécurité, conversational analytics | Les conversations standards restent limitées à certains contextes ; plusieurs visualisations et analyses avancées — forecasting, corrélation, anomalies — ont des restrictions ou nécessitent Advanced Analytics. |
| ThoughtSpot | Agent analytics, couche sémantique, requêtes traçables, actions vers les outils métier | Montre que l'avenir du NLQ n'est pas le text-to-SQL opaque : le contexte sémantique, la vérifiabilité et l'action sont centraux. |
| Dataiku DSS 15 | Très large couverture data/ML/MLOps, agents, Agent Skills, MCP, Polars, gouvernance | La profondeur fonctionnelle rend l'architecture et l'expérience très riches ; cela renforce l'intérêt d'une interface DataVision progressive et orientée objectifs plutôt qu'une liste de dizaines de modules. |
| Alteryx | Workflows visuels de préparation et d'automatisation | En 2026, Alteryx a séparé certains modes en applications distinctes explicitement pour réduire la complexité d'interface et la confusion entre modes. |
| Metabase | Self-service BI, filtres, drill-through, abonnements/alertes, actions | Très efficace pour BI opérationnelle ; DataVision doit conserver cette simplicité tout en allant plus loin en statistiques, ML et reproductibilité. |
| Apache Superset | 40+ visualisations, SQL Lab, filtres, cross-filter, drill, semantic layer | Excellente couverture BI/SQL ; DataVision peut se différencier en intégrant nativement préparation, statistiques, ML, XAI et décision. |

## 3. Failles de conception à éviter

### 3.1 Le chatbot posé au-dessus des données

Un chatbot sans modèle métier ni outils déterministes est fragile. Power BI et Looker documentent explicitement la nécessité de préparer et gouverner le contexte sémantique. DataVision doit donc toujours privilégier :

`intention -> sémantique -> outil -> calcul -> validation -> explication`.

### 3.2 La navigation par catalogue de fonctions

Afficher toutes les fonctions dans une seule barre latérale finit par reproduire la complexité d'un IDE ou d'une suite BI enterprise. La séparation de modes d'Alteryx en 2026 confirme que la réduction de la complexité contextuelle est un enjeu produit réel.

DataVision v2 adopte donc six espaces : **Vue d'ensemble, Données, Analyser, Modéliser, Décider, Publier**. Les outils secondaires apparaissent uniquement dans le contexte du travail en cours.

### 3.3 Les résultats impossibles à auditer

Le produit doit afficher le dataset, sa version, la requête/code, le moteur, les paramètres et la provenance. Une explication IA sans preuve calculée ne doit pas être considérée comme un résultat analytique.

### 3.4 Les métriques définies différemment dans chaque dashboard

Les définitions métier doivent être centralisées. DataVision v2 introduit une couche sémantique avec métriques, dimensions, synonymes, unités et certification.

### 3.5 La « décision » confondue avec la causalité

Un what-if de modèle indique comment **le modèle** réagit à une modification des entrées. Ce n'est pas une preuve d'effet causal. DataVision l'affiche explicitement et conserve les hypothèses du scénario.

## 4. Positionnement DataVision visé

DataVision ne cherche pas à être uniquement un BI tool, un notebook, un AutoML ou un assistant conversationnel. Le positionnement cible est :

> **Data Intelligence Workspace vérifiable : de la donnée brute à la décision, avec statistiques professionnelles, BI, ML/XAI, couche sémantique, agent analytique et reporting reproductible dans un même produit installable.**

Le différenciateur recherché n'est pas « plus de boutons ». C'est la continuité de preuve entre :

`source -> version -> transformation -> métrique -> analyse -> modèle -> explication -> scénario -> décision -> rapport`.

## 5. Réponse produit implémentée en v2.0

- interface restructurée par objectifs et non par catalogue de modules ;
- command palette globale `Ctrl/Cmd + K` ;
- playbooks d'entrée orientés question : comparer, expliquer, prévoir, analyser automatiquement ;
- **Semantic Studio** avec métriques, dimensions, synonymes, unités et certification ;
- NLQ sémantiquement ancré ; une agrégation explicitement demandée par l'utilisateur prime sur l'agrégation par défaut de la métrique ;
- AI Analyst capable de résoudre les synonymes métier vers les colonnes physiques et d'exposer ce grounding dans la provenance ;
- **Metric Pulse** local : valeur courante, tendance, variation et signal d'anomalie ;
- **Trust Center** : qualité, sémantique, reproductibilité, confidentialité et politiques d'exécution ;
- **Decision Lab** : scénarios what-if et courbes de sensibilité sur le modèle sauvegardé ;
- topbar de contexte : dataset, version, qualité et score de confiance ;
- densité visuelle réduite, panneaux moins décoratifs et sous-navigation contextuelle.

## 6. Prochaines capacités prioritaires, non simulées

Ces fonctions sont importantes sur le marché mais **ne sont pas présentées comme implémentées en v2.0** :

- authentification multi-utilisateurs, RBAC/RLS/column-level security ;
- scheduler, abonnements, alertes et monitoring continu des métriques ;
- actions connectées (Slack/Jira/CRM/webhooks) avec approbation humaine ;
- modèles sémantiques multi-tables : relations, hiérarchies, formules de métriques et calendriers ;
- orchestration asynchrone Redis/Celery pour jobs longs et streaming d'état ;
- connecteurs cloud et bases enterprise ;
- plugin/MCP runtime avec permissions ;
- collaboration, commentaires et validation ;
- causal inference séparée du what-if prédictif.

## 7. Sources publiques principales

- Microsoft Learn — *Prepare semantic model for AI / Copilot in Power BI*: https://learn.microsoft.com/en-us/power-bi/create-reports/tutorial-copilot-power-bi-prepare-model
- Microsoft Learn — *Use Copilot with semantic models*: https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-semantic-models
- Tableau Help — *Explore Metrics with Tableau Pulse*: https://help.tableau.com/current/online/en-gb/pulse_explore_metrics.htm
- Google Cloud — *Conversational Analytics in Looker overview*: https://docs.cloud.google.com/looker/docs/conversational-analytics-overview
- ThoughtSpot — *Spotter*: https://www.thoughtspot.com/product/agents/spotter
- ThoughtSpot — *Spotter Semantics*: https://www.thoughtspot.com/product/spotter-semantics
- Dataiku DSS 15 — *Release notes*: https://doc.dataiku.com/dss/latest/release_notes/15.html
- Dataiku DSS 15 — *Automated machine learning*: https://doc.dataiku.com/dss/latest/machine-learning/auto-ml.html
- Alteryx Designer Cloud — *Release Notes*: https://help.alteryx.com/aac/en/release-notes/release-notes-for-designer-cloud.html
- Apache Superset — https://superset.apache.org/
- Metabase Documentation — https://www.metabase.com/docs/latest/
