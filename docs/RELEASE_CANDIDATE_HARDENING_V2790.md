# DataVision AI v2.79 — Hardening & End-to-End Validation

## Objectif

v2.79 transforme la préparation du Release Candidate en gate technique reproductible sans confondre **readiness technique** et **acceptation production externe**.

## Renforcements livrés

- **Headers de sécurité** côté API et frontend : `nosniff`, anti-framing, referrer policy, permissions policy et HSTS sur HTTPS.
- **Migrations ordonnées par version** même lorsqu'une migration est ajoutée en backport; réapplication idempotente vérifiée.
- **Backup/restore drill** exécuté comme preuve de restauration, avec extraction sûre et contrôle SHA-256 du manifest.
- **Sign-off production durci** : empreinte SHA-256 de chaque preuve, revalidation des pièces jointes, version produit obligatoire et refus des waivers en mode strict.
- **CI exhaustive** : les gates ajoutés de v2.71 à v2.79 sont tous exécutés explicitement.
- **E2E Release Candidate** : headers de sécurité via proxy, corrélation request/trace sur 404, accessibilité clavier du shell et de l'assistant.
- **Frontière externe préservée** : l'UAT et les preuves d'environnement cible restent `pending` tant qu'elles ne sont pas réellement exécutées et signées.

## Gate

```bash
python scripts/release_candidate_acceptance.py --root . --check
```

Le résultat `technical_ready` signifie que le code source et les tests de hardening sont prêts pour un Release Candidate. Il **ne signifie pas** que la production est signée.

## Sign-off strict cible

```bash
python scripts/production_signoff.py verify \
  --evidence-dir production-evidence \
  --require-all
```

Par défaut, un statut `waived` n'est pas accepté par le sign-off strict. L'option `--allow-waivers` existe uniquement pour une revue non finale et doit être explicitement demandée.

## Limites assumées

Les sections CDC §71 et §74 restent partielles jusqu'à exécution réelle sur l'infrastructure cible et UAT métier signée. La v2.79 améliore la qualité des preuves et leur intégrité mais ne fabrique aucune preuve externe.
