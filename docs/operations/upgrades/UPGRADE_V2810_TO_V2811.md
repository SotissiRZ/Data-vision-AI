# Upgrade v2.81.0 → v2.81.1

Cette mise à jour corrige l'expérience de première authentification sans modifier le schéma de base de données.

1. Remplacer le code par l'archive complète v2.81.1 dans un dossier propre.
2. Conserver les volumes PostgreSQL/Redis et les données applicatives.
3. Retirer `BOOTSTRAP_SECRET` de `.env` s'il était présent ; il n'est plus utilisé par l'interface.
4. Ajouter `FIRST_RUN_SETUP_MODE=local` et `PASSWORD_MIN_LENGTH=8` si ces variables ne sont pas déjà présentes.
5. Si l'instance possède déjà au moins un utilisateur, aucun bootstrap n'est rejoué.
6. Si l'instance locale est neuve, ouvrir DataVision depuis `localhost` et créer le premier administrateur depuis l'assistant de première configuration.
7. Si l'instance neuve est hébergée sur un serveur distant, créer le premier propriétaire depuis la console du serveur :

```bash
docker compose exec api python -m app.ops.bootstrap_owner --email admin@example.com
```

Le mot de passe est demandé de manière interactive et n'est pas passé comme argument de ligne de commande.

## Sécurité

La session de première configuration locale est aléatoire, limitée à 15 minutes, placée dans un cookie HttpOnly `SameSite=Strict`, puis invalidée lorsque le premier propriétaire est créé. Une instance distante n'autorise pas la revendication du premier compte via le navigateur.
