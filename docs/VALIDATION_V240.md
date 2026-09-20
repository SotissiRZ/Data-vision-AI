# Validation v2.40.0

## Objectif

Transformer v2.39.1 en baseline de production vérifiable sans modifier les moteurs analytiques historiques.

## Contrôles ajoutés

- `scripts/production_baseline.py --check` : contrôle structurel local, sans réseau ;
- vérification de la version produit dans les fichiers de conformité ;
- vérification des pins `cryptography==46.0.5` et `snowflake-connector-python==4.7.4` ;
- vérification du proxy API same-origin et de l'inclusion de `compliance/` dans l'image backend ;
- vérification de la présence de l'adapter assistant ;
- `scripts/verify_release.py` contrôle désormais l'intégrité de chaque fichier du ZIP via le manifest embarqué ;
- rejet des entrées ZIP dupliquées, chemins dangereux, fichiers non déclarés ou manquants ;
- auto-vérification par `scripts/release.py` après création d'une archive.

## Validation locale de génération

Les contrôles Python, CDC, hygiène du dépôt et tests backend sont exécutables dans l'environnement de génération.

Le moteur Docker n'est pas disponible dans cet environnement ; la validation `docker compose build` reste donc une étape de CI/machine cible et n'est pas présentée comme exécutée ici.

## Limites connues de l'environnement de génération

- l'environnement de génération utilise Python 3.13.5 alors que Docker/CI cible Python 3.12 ;
- les 347 tests backend atteignent `347 passed` et `pytest.main()` retourne 0, mais Python 3.13.5 reste bloqué ensuite dans son garbage collector final ; aucun thread DataVision non-daemon n'est encore actif au moment du blocage ;
- ce comportement ne doit pas être présenté comme reproduit sous Python 3.12 tant que la CI cible ne l'a pas confirmé ;
- Docker n'est pas installé dans l'environnement de génération ; le build Docker reste à valider sur CI/machine cible ;
- aucun `package-lock.json` artificiel n'est généré hors registre npm. Le verrouillage transitif frontend reste un point de durcissement futur.
