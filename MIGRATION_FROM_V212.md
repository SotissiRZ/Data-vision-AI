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
