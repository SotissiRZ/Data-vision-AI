# DataVision AI

DataVision AI est une plateforme intégrée pour l’ingestion, la préparation, l’analyse, la visualisation, le machine learning, le reporting et l’aide à la décision gouvernée.

Version courante : **2.81.0**.

## Démarrage rapide

Sous Windows :

```powershell
.\preflight-windows.ps1
.\start-datavision.ps1
```

Ou avec Docker Compose :

```bash
docker compose up --build
```

L’authentification est obligatoire par défaut (`AUTH_MODE=required`). Le mode `local_dev` doit être activé explicitement et ne doit pas être utilisé en production.

## Documentation

Toute la documentation détaillée est centralisée dans [`docs/`](docs/README.md).

Documents principaux :

- [Architecture](docs/ARCHITECTURE.md)
- [Rapport technique](docs/RAPPORT_TECHNIQUE.md)
- [Guide utilisateur](docs/GUIDE_UTILISATEUR.md)
- [Guide de déploiement](docs/GUIDE_DEPLOIEMENT.md)
- [Guide d’exploitation](docs/GUIDE_EXPLOITATION.md)
- [Rapport sécurité](docs/RAPPORT_SECURITE.md)
- [Matrice de couverture du CDC](docs/CDC_COVERAGE_MATRIX.md)
- [Changelog](docs/CHANGELOG.md)

Les versions DOCX/PDF destinées à diffusion sont dans [`docs/deliverables/documentation/`](docs/deliverables/documentation/).

## Sécurité

Consulter [`SECURITY.md`](SECURITY.md) pour la politique de signalement et [`docs/RAPPORT_SECURITE.md`](docs/RAPPORT_SECURITE.md) pour le rapport de sécurité complet.

## Vérification de release

```bash
python scripts/repository_hygiene.py --root . --check
python scripts/production_baseline.py --root .
python scripts/release_candidate_acceptance.py --root .
python scripts/release_installation_acceptance.py --root .
```

La promotion en production doit également inclure les contrôles frontend, les scans de dépendances/images et les validations externes prévues par le processus de release.
