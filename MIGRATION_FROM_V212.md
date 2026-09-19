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
