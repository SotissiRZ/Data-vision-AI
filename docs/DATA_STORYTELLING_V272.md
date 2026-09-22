# DataVision AI v2.72 — Data Storytelling avancé

## Objectif

La v2.72 transforme le Report Builder en moteur de narration analytique gouvernée. Une histoire n’est pas produite comme un texte libre : elle est construite à partir de preuves issues du dataset, du profilage, de la qualité, des insights, des analyses et des visualisations disponibles.

## Architecture

Le service `backend/app/services/storytelling.py` construit un blueprint déterministe. Chaque page comporte un rôle narratif, un titre, un résumé, des claims, des références visuelles, un takeaway et un taux de couverture de preuve. Les claims portent explicitement leurs `evidence_ids`.

Le `report_builder.py` transforme le blueprint en blocs `story_page`, les valide avec la version verrouillée du dataset puis les rend en Markdown, HTML, DOCX ou PDF.

## Contrôles de preuve

- chaque claim doit référencer au moins une preuve existante ;
- la couverture globale doit être de 100 % avant validation ;
- aucune causalité n’est générée automatiquement ;
- les calculs numériques restent déterministes et ne sont pas délégués au LLM ;
- la version du dataset est verrouillée dans le blueprint et le rapport.

## Publication gouvernée

`publish_report` refuse la publication si la validation du rapport échoue ou si le Data Reliability Gate fournit des blockers. Une publication réussie crée un reçu immuable contenant notamment l’empreinte SHA-256 du rapport, la visibilité, le canal, le contexte workspace/acteur, la version du dataset, le statut de validation et la couverture de preuve. Une seconde publication du même contenu retourne le même reçu.

## API

- `POST /api/v1/datasets/{dataset_id}/storytelling/preview` : prévisualiser la trame ;
- `POST /api/v1/datasets/{dataset_id}/reports` : générer le rapport avec les paramètres storytelling ;
- `POST /api/v1/datasets/{dataset_id}/reports/{report_id}/publish` : publier après les gates ;
- `GET /api/v1/datasets/{dataset_id}/reports/{report_id}/publication` : lire le reçu de publication.

Paramètres principaux : `story_audience`, `story_objective`, `story_tone`, `story_max_pages`.

## UI et Assistant

Le Report Builder permet de définir l’audience, le ton, l’objectif et le nombre maximal de pages, de prévisualiser la trame et de publier un rapport validé. Le contrat Assistant expose les mêmes paramètres afin d’éviter deux moteurs divergents.

## Acceptance

Le gate `scripts/storytelling_acceptance.py --check` couvre huit invariants de release : moteur multi-page, liens de preuve, contrôles éditoriaux, rendu multi-format, publication gouvernée, endpoints, raccordement Assistant/UI et présence des tests d’intégration.
