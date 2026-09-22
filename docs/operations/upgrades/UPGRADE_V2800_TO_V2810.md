# Upgrade v2.80.x → v2.81.0

La v2.81 est un gel sécurité/documentation. Elle conserve les données et volumes de la v2.80, mais impose l'authentification par défaut et ajoute une migration de throttling des connexions.

1. Sauvegarder la v2.80 et vérifier le restore drill.
2. Extraire la v2.81 dans **un nouveau dossier vide** ; ne pas écraser l'ancien dossier.
3. Copier uniquement `.env` et les éléments de configuration explicitement nécessaires.
4. Vérifier `AUTH_MODE=required`, `AUTH_SECRET`, `BOOTSTRAP_SECRET`, CORS, KMS/Vault et TLS.
5. Exécuter `preflight-windows.ps1` puis `upgrade-windows.ps1`.
6. Vérifier `/health/startup` et `/health/ready`.
7. Se reconnecter : les tokens navigateur ne sont plus persistés dans `localStorage`.
8. Exécuter les smoke tests et les gates de sécurité avant ouverture du trafic.

Si un ancien dossier a déjà reçu plusieurs archives superposées, exécuter :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cleanup-legacy-root.ps1
```
