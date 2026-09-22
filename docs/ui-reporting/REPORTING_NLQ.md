# Reporting reproductible et NLQ — v1.0

## Reporting

Un rapport est persisté sous forme JSON structurée dans `data/reports/` puis exporté à la demande.

Sections disponibles : `overview`, `quality`, `descriptive`, `ai_analysis`, `methodology`, `provenance`.

Le rapport référence la version exacte du dataset et, lorsqu'elle est sélectionnée, la session AI Analyst exacte. Les exports n'effectuent pas de nouveau calcul : ils rendent les résultats déjà liés à cette provenance.

Formats : PDF, DOCX, HTML, Markdown.

## Historique AI Analyst

Chaque réponse AI Analyst est enregistrée dans `data/analyses/<session_id>.json`. L'historique est filtré par `dataset_id` et expose une vue synthétique avant chargement de la session complète.

## NLQ / Text-to-SQL

Le traducteur v1.0 est déterministe. Il gère notamment :

- comptages ;
- moyenne ;
- somme ;
- min/max ;
- regroupement `par` / `selon` / `by` ;
- top N ;
- projection de colonnes mentionnées.

La requête produite passe ensuite dans le validateur SQL read-only de DataVision. Les instructions destructives restent interdites.

En cas d'ambiguïté, la réponse contient `confidence` et `assumptions` afin que l'utilisateur puisse vérifier la traduction avant de réutiliser la requête.
