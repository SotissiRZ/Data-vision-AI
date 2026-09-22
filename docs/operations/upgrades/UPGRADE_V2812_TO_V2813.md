# Upgrade DataVision v2.81.2 → v2.81.3

Cette mise à jour corrige le blocage de la première configuration causé par la limite mémoire implicite OpenSSL/scrypt et rend la connexion à un compte existant accessible depuis l’écran de première configuration.

## Windows

1. Conservez le fichier `.env` et les volumes Docker existants.
2. Extrayez la v2.81.3 dans un nouveau dossier.
3. Recopiez votre `.env` existant.
4. Exécutez `./upgrade-windows.ps1`.

`PASSWORD_SCRYPT_MAXMEM_MB` est optionnel sur une configuration existante ; la valeur par défaut est `256`. Pour une installation de développement où `DEMO_ACCOUNT_ENABLED` est absent, le compte test local est désormais activé par défaut. Il reste automatiquement désactivé lorsque `APP_ENV=production`.
