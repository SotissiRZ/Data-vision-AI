# DataVision AI v2.80.0 — Release Candidate

## Statut

La v2.80.0 est un **Release Candidate**. Le périmètre fonctionnel est gelé : les changements admis après ce jalon sont limités aux corrections de défauts, sécurité, installation, upgrade, packaging et preuves de validation.

Le statut `production stable` n'est pas auto-attribué. Les preuves externes d'infrastructure cible et l'UAT métier restent obligatoires avant v3.0.0.

## Installation neuve

Sous Windows avec Docker Desktop :

```powershell
.\install-windows.ps1
```

Le script exécute le préflight, initialise `.env`, génère les secrets locaux manquants puis reconstruit les images applicatives.

## Upgrade supporté

Le chemin directement validé par ce RC est **v2.79.x → v2.80.0** :

```powershell
.\upgrade-windows.ps1
```

L'upgrade conserve les volumes Docker, copie la configuration dans `upgrade-backups/`, crée par défaut une sauvegarde applicative, reconstruit les images, applique les migrations explicites puis vérifie `/health/ready`.

Aucun script d'upgrade RC n'utilise `docker compose down -v`.

## Doctor de configuration

```powershell
python scripts/config_doctor.py --root . --env-file .env
```

Pour une validation production stricte :

```powershell
python scripts/config_doctor.py --root . --env-file .env --mode production
```

Le mode production refuse notamment les secrets placeholders, impose le chiffrement KMS renseigné et exige `ANTIVIRUS_MODE=required`.

## Conditions de passage v3.0.0

- tous les gates automatisés verts ;
- archive reproductible et SHA-256 vérifiés ;
- installation/upgrade cible exécutés avec preuves ;
- preuve performance cible encore valide ;
- UAT métier signée ;
- sign-off production strict sans waiver non approuvé.
