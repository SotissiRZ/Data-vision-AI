# Installation du dossier complet v2.15.3

Ce ZIP contient le projet DataVision complet, pas un patch.

## Recommandation Windows

Ne l'extrais pas directement par-dessus ton dossier actuel.

1. Arrête DataVision :

```powershell
cd D:\Bureau\Project\datavision
docker compose down
```

2. Renomme l'ancien dossier en sauvegarde, par exemple :

```text
datavision-v2.12-backup
```

3. Extrais `datavision-ai-v2.15.3-complet.zip`.

4. Renomme le dossier extrait en :

```text
datavision
```

5. Copie ton ancien `.env` dans le nouveau dossier si nécessaire, puis ajoute
les variables Model Gateway de `.env.example`.

6. Reconstruis :

```powershell
docker compose build web
docker compose build api
docker compose up -d
docker compose ps
```

7. Ouvre :

```text
http://localhost:3005
```

API :

```text
http://localhost:8005
http://localhost:8005/docs
```

## Important

La structure d'origine v2.12 est conservée :

```text
datavision/
├── backend/
├── frontend/
├── docs/
├── docker-compose.yml
├── .env.example
├── README.md
├── VERSION
├── install-windows.ps1
├── start-datavision.ps1
└── stop-datavision.ps1
```

L'assistant est intégré sous :

```text
frontend/components/assistant/
frontend/lib/assistant/
backend/app/assistant/
```


## v2.18 — Nouveau service sandbox

La v2.18 ajoute un conteneur Docker interne `sandbox`.

Reconstruire l'ensemble :

```powershell
docker compose build api sandbox web
docker compose up -d
docker compose ps
```

Le service `sandbox` ne publie aucun port sur la machine hôte.


## v2.21 — Connecteurs avancés

Le backend installe de nouveaux drivers de base de données et cloud warehouse.

Après remplacement du dossier :

```powershell
docker compose down
docker compose build --no-cache api worker web
docker compose up -d
docker compose ps
```

Pour SQLite, déposer les fichiers `.db` dans :

```text
data/connectors/sqlite
```

Ne placez jamais de mot de passe, token ou JSON de service account dans le
champ `options`. Utilisez le champ secret du connecteur.


## v2.22 — Plugin System & MCP

La v2.22 ajoute les tables metadata :

- `plugin_installations` ;
- `plugin_tools` ;
- `plugin_runs`.

Elles sont créées automatiquement par le Metadata Store au démarrage.

Le backend ajoute aussi `jsonschema` pour valider les contrats dynamiques des
extensions.

Après remplacement du dossier :

```powershell
docker compose down
docker compose build --no-cache api worker web
docker compose up -d
docker compose ps
```

Les credentials de plugin doivent être créés dans **Identité & Secrets**, puis
référencés par `secret_id` dans **Plugins & MCP**. Ne placez aucun token dans
l'endpoint, le manifest ou les options JSON.


## v2.23 — Responsible AI

Aucune migration SQL obligatoire n'est ajoutée pour ce module.

Les audits Responsible AI sont calculés depuis les artefacts modèles existants
et les datasets de référence. Les résumés persistés sont stockés dans la Model
Card du modèle.

Après remplacement :

```powershell
docker compose down
docker compose build api worker web
docker compose up -d
docker compose ps
```

Les anciens modèles continuent de fonctionner. Ils apparaissent simplement avec
un statut Responsible AI non évalué jusqu'à ce qu'un audit soit exécuté.


## v2.24 — Model Registry & MLOps

La v2.24 ajoute uniquement des tables metadata et du code applicatif ; aucune
base externe supplémentaire n'est requise.

Reconstruction recommandée :

```powershell
docker compose down
docker compose build api worker web
docker compose up -d
docker compose ps
```

Les modèles nouvellement entraînés sont enregistrés automatiquement en `draft`.
Les anciens artefacts restent compatibles et peuvent être enregistrés depuis
**Modéliser → Model Registry**.


## v2.25 — Feature Store & Serving

v2.25 ajoute plusieurs tables de métadonnées créées automatiquement au
démarrage :

```text
feature_sets
feature_materializations
model_deployments
model_deployment_revisions
model_serving_requests
```

Aucune migration manuelle n'est requise avec le metadata store DataVision.

Après remplacement du dossier :

```powershell
docker compose down
docker compose build api worker web
docker compose up -d
docker compose ps
```

Le `sandbox` n'a pas changé dans cette version.

Le serving v2.25 est fourni par l'API DataVision elle-même. Aucun cluster
Kubernetes ou service cloud externe n'est créé automatiquement.


## v2.25.1 — Hotfix de lisibilité UI

Cette version ne demande **aucune migration de données**.

Après remplacement du dossier :

```powershell
docker compose down
docker compose build web
docker compose up -d
```

Le changement concerne surtout le frontend : tailles de police, densité,
lisibilité des panneaux et assistant flottant.


## v2.26.0 — Accessibilité d’affichage

Aucune migration de données n’est nécessaire.

Après remplacement du dossier :

```powershell
docker compose down
docker compose build web
docker compose up -d
```

Cette version modifie seulement le frontend : topbar, contrôles de zoom,
modes de lecture et responsive.


## v2.26.1 — Topbar

Aucune migration de données n'est nécessaire.

```powershell
docker compose down
docker compose build web
docker compose up -d
```

La version modifie uniquement le frontend : barre de recherche et bouton de paramétrage.
