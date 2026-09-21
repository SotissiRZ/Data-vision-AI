# Migration v2.53.0 → v2.53.1

Correctif frontend uniquement.

- Aucun changement de schéma ou de volume Docker.
- Conserver le fichier `.env` existant.
- Rebuilder `web` (ou l'ensemble des services) pour intégrer le correctif TypeScript.

Commande recommandée :

```powershell
docker compose down
docker compose up -d --build
```
