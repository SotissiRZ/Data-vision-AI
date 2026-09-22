# Validation v2.59.0

## Périmètre

Résilience et exploitation HA : probes avancées, HPA/PDB, migrations explicites, sauvegarde/restauration, rotation KMS et runbook DR.

## Gates attendus

- `RESILIENCE_ACCEPTANCE 8/8` ;
- `HARDENING_ACCEPTANCE 8/8` ;
- `ENTREPRISE_ACCEPTANCE 8/8` ;
- baseline production et hygiène dépôt ;
- tests backend ciblés v2.59.

## Migration depuis v2.58

Migration additive. Le nouveau registre `schema_migrations` applique `2.59.0-001` et crée les tables opérationnelles `backup_runs` et `kms_rotation_events`. Aucun dataset utilisateur n'est transformé.
