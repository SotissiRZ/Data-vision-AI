# Upgrade DataVision v2.81.3 → v2.81.4

## Motif
La v2.81.3 pouvait arrêter `upgrade-windows.ps1` pendant le préflight si le Python global de Windows ne contenait pas les dépendances backend, par exemple `pydantic_settings`. Cela était incohérent avec l’architecture Docker : ces dépendances appartiennent à l’image API, pas à l’hôte Windows.

## Procédure
1. Extraire la v2.81.4 dans un nouveau dossier.
2. Copier le fichier `.env` de l’installation précédente dans ce nouveau dossier.
3. Depuis PowerShell, lancer :

```powershell
.\upgrade-windows.ps1
```

Le script effectue maintenant les contrôles structurels avant build, construit les images, puis vérifie les dépendances Python directement dans la nouvelle image API avant les migrations et le démarrage.

## Données
Les volumes Docker persistants sont conservés par l’upgrade. Ne lancez pas `docker compose down -v`.
