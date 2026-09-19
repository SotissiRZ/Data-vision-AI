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


## v2.27.0 — Préférences UI synchronisées

Une nouvelle table de métadonnées est créée automatiquement :

```text
user_preferences
```

Elle contient uniquement des préférences d'interface validées et non des secrets.

Après remplacement du dossier :

```powershell
docker compose down
docker compose build api web
docker compose up -d
docker compose ps
```

Le `worker` et le `sandbox` ne changent pas dans cette version.


## v2.28.0 — AI Analyst Performance & Streaming

Deux nouvelles tables de métadonnées sont créées automatiquement :

```text
ai_analysis_runs
ai_analysis_cache
```

Après remplacement du dossier :

```powershell
docker compose down
docker compose build api web
docker compose up -d
docker compose ps
```

Le worker n'est pas requis pour le nouveau runtime interactif AI Analyst : les
exécutions interactives utilisent un pool interne borné de 4 threads daemon et
restent compatibles avec le mode Local. Les jobs Enterprise historiques restent
disponibles séparément.


## v2.29.0 — Production Hardening & CI/CD

Aucune migration de données n'est requise.

Les principaux changements sont infrastructurels : workflows CI, healthchecks,
Playwright, scans et release reproductible.

Après remplacement du dossier :

```powershell
copy .env.example .env
docker compose config
docker compose down
docker compose build api worker sandbox web
docker compose up -d
docker compose ps
```

Attendez que `api`, `sandbox`, `worker` et `web` passent à l'état healthy avant
de valider l'installation.


## v2.30 — CDC Compliance

Aucune migration de données n'est requise.

Nouveaux fichiers :

```text
compliance/CDC_COVERAGE_MATRIX.json
compliance/CDC_COVERAGE_SUMMARY.json
docs/CDC_COVERAGE_MATRIX.md
docs/CDC_COMPLIANCE_V2300.md
scripts/cdc_audit.py
```

Le backend et le frontend doivent être reconstruits :

```powershell
docker compose down
docker compose build api web
docker compose up -d
```


## v2.31.0 — Security P0

No manual database migration is required; the metadata tables are created automatically.

New environment settings:

```env
WEBAUTHN_ENABLED=true
WEBAUTHN_RP_ID=localhost
WEBAUTHN_ORIGIN=http://localhost:3005
ANTIVIRUS_MODE=preferred
SECRET_KMS_KEY=
SECRET_KMS_KEY_ID=primary
SECRET_KMS_PREVIOUS_KEYS={}
```

For production:

```env
APP_ENV=production
ANTIVIRUS_MODE=required
SECRET_KMS_KEY=<strong secret injected by runtime>
WEBAUTHN_RP_ID=datavision.example.com
WEBAUTHN_ORIGIN=https://datavision.example.com
```

Rebuild the API/web because backend dependencies and the Identity UI changed:

```powershell
docker compose down
docker compose build --no-cache api worker web
docker compose up -d
docker compose ps
```

The official Compose now also starts ClamAV.


## v2.31.2 — correctif de build Docker

Le pin `cryptography==46.0.4` de v2.31.0 était incompatible avec `snowflake-connector-python==4.7.4`, qui exige `cryptography>=46.0.5`.

v2.31.2 utilise :

```text
cryptography==46.0.5
```

Avant reconstruction sur Windows :

```powershell
.\reset-docker.ps1
docker compose build --no-cache api worker web
docker compose up -d
docker compose ps
```

Aucun volume n'est supprimé par `reset-docker.ps1`.

## v2.31.2 — Correctif de déploiement Windows/Docker

Cette version ajoute un préflight strict et empêche le démarrage après un build échoué.
Avant tout build, `preflight-windows.ps1` vérifie :

- `VERSION=2.31.2` ;
- `backend/requirements.txt` contient `cryptography==46.0.5` ;
- aucune ancienne ligne `cryptography==46.0.4` ;
- `docker compose config` est valide.

Utiliser de préférence :

```powershell
.\rebuild-windows.ps1
```

Le script supprime les anciennes images applicatives mais conserve les volumes PostgreSQL, Redis et ClamAV.


## v2.31.3 — Contexte assistant dataset

Aucune migration de données n’est requise. Reconstruire `api` et `web` pour bénéficier du nouveau profil temporel et de l’intention `dataset_context`.


## v2.32.0 — Context Engine v2

Cette version ajoute une table de métadonnées `assistant_session_memory`.
Aucune migration manuelle n’est nécessaire : la table est créée par l’initialisation du metadata store.

La mémoire persistée contient uniquement un état sémantique compact (dataset/modèle/colonnes/intention/résumé de résultat), pas le transcript brut du chat.

Après remplacement du dossier :

```powershell
.\rebuild-windows.ps1
```

Après démarrage, rechargez le dataset actif une fois afin de remplir immédiatement le contexte enrichi.


## v2.33.0 — Context Engine v3

Aucune migration SQL manuelle n'est nécessaire : les artefacts analytiques
compacts sont persistés dans le champ JSON `facts_json` déjà existant de la
mémoire de session assistant.

Reconstruire `api`, `worker` et `web`.


## v2.34.0 — Context Engine v4 & actions gouvernées

Aucune migration de données obligatoire n'est requise.

Évolutions :

- résolution contextuelle d'actions sur le modèle mémorisé ;
- propagation du niveau de risque Tool Registry jusqu'au frontend ;
- confirmation humaine imposée lorsque le Tool Registry définit
  `human_confirmation_required=true` ;
- boutons explicites **Confirmer / Refuser** pour les actions orchestrées ;
- refus enregistré côté serveur et reprise sûre du turn run.

Reconstruction recommandée :

```powershell
.\reset-docker.ps1
.\rebuild-windows.ps1
```


## v2.35.0 — Context Engine v5 / Multi-artifact Memory

Aucune migration de données obligatoire n'est requise.

Les anciennes mémoires d'artefacts sont rétrocompatibles : les références
`Graphique #N`, `Modèle #N`, etc. sont recalculées de manière déterministe au
chargement puis persistées lors de la prochaine mise à jour de session.

Après remplacement du dossier :

```powershell
.\preflight-windows.ps1
.\reset-docker.ps1
.\rebuild-windows.ps1
```


## v2.36.0 — Context Engine v6 / Project Memory

La mise à jour ajoute deux tables de métadonnées créées automatiquement au démarrage :

- `assistant_project_memory`
- `assistant_project_memory_policy`

Aucune migration manuelle n'est requise. Les anciens datasets, modèles, secrets, workspaces et mémoires de session restent inchangés.

Après remplacement du dossier :

```powershell
.\preflight-windows.ps1
.\reset-docker.ps1
.\rebuild-windows.ps1
```

La dépendance de sécurité reste verrouillée sur `cryptography==46.0.5`.


## v2.37.0 — Context Engine v7 / Semantic Project Recall

Aucune migration manuelle de données n'est nécessaire. La recherche utilise les entrées existantes de `assistant_project_memory`. Les nouveaux artefacts enregistrent aussi le nom du dataset et la couverture temporelle compacte lorsqu'ils sont disponibles.
