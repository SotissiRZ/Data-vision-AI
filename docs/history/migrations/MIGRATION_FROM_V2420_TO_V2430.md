# Migration v2.42.0 → v2.43.0

1. Conserver votre fichier `.env` et vos volumes Docker existants.
2. Remplacer le dossier applicatif par la distribution complète v2.43.0.
3. Ne pas exécuter `docker compose down -v` : aucune suppression de volume n'est requise.
4. Exécuter `powershell -ExecutionPolicy Bypass -File .\preflight-windows.ps1` ou lancer directement le build Docker habituel.
5. Les notebooks existants restent compatibles ; leur liaison dataset/version historique est conservée.
6. Les nouveaux artefacts CSV/JSON peuvent être promus en versions de dataset immuables depuis le Notebook Workspace.
