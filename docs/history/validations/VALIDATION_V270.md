# Validation — DataVision AI v2.7.0

## Tests exécutés

```text
pytest -q
45 passed
```

## Nouveaux scénarios v2.7

- création d'un connecteur Entreprise ;
- chiffrement du mot de passe et absence du secret dans les réponses API ;
- création d'une source SQL ;
- aperçu read-only ;
- premier refresh incrémental ;
- mise à jour du watermark ;
- second refresh avec append ;
- création d'une nouvelle version immutable ;
- liaison automatique du dataset au workspace ;
- SLA de fraîcheur ;
- historique des runs ;
- planification ;
- claim atomique d'une échéance ;
- schema drift destructif avec policy `fail` ;
- job Redis `connector_refresh` avec contexte tenant-aware.

## Compilation

```text
python -m compileall backend/app : OK
npx tsc --noEmit --noCheck       : OK
strictNullChecks ciblé           : OK
```

Le fichier de stubs TypeScript utilisé uniquement pour la validation locale sans `node_modules` est retiré avant packaging.

## Non revendiqué

- `next build` Docker complet : non exécuté dans cet environnement ;
- connexion réseau réelle vers un PostgreSQL/MySQL externe : non testée ici ;
- haute disponibilité du scheduler multi-worker à grande échelle : non testée en charge.

Ces points nécessitent la machine cible ou un environnement d'intégration disposant des services concernés.
