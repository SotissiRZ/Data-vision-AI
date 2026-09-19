# Structure du projet DataVision AI

Depuis v2.39.0, la racine du dépôt est volontairement limitée aux fichiers
opérationnels. La documentation historique est rangée sous `docs/history/`.

```text
datavision/
├── .github/                 # CI/CD et sécurité
├── backend/                 # API FastAPI, moteurs analytiques, assistant
├── compliance/              # Matrice CDC et acceptance
├── docs/                    # Documentation produit et technique
│   └── history/             # Historique de versions non opérationnel
│       ├── manifests/
│       └── migrations/
├── frontend/                # Next.js / React
├── sandbox/                 # Exécution notebook isolée
├── sbom/                    # Software Bill of Materials
├── scripts/                 # Outils CI, release et audit
├── .env.example
├── docker-compose.yml
├── Makefile
├── README.md
├── SECURITY.md
├── VERSION
├── RELEASE_MANIFEST.json    # généré dans les archives de release
├── install-windows.ps1
├── preflight-windows.ps1
├── rebuild-windows.ps1
├── reset-docker.ps1
├── start-datavision.ps1
└── stop-datavision.ps1
```

## Règles d'hygiène

1. Aucun `MERGE_MANIFEST_V*.json` ne doit être ajouté à la racine.
2. Les migrations historiques vont dans `docs/history/migrations/`.
3. Les manifests historiques vont dans `docs/history/manifests/`.
4. La racine ne contient que les fichiers nécessaires au lancement, au build,
   à la sécurité, aux tests et à la documentation principale.
5. `scripts/repository_hygiene.py --check` vérifie automatiquement ces règles.
