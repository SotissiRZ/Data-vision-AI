# Sécurité opérationnelle & supply chain — v2.63

DataVision applique une chaîne de confiance à plusieurs niveaux :

- SBOM backend CycloneDX, frontend CycloneDX et source SPDX ;
- index SBOM avec SHA-256 de chaque inventaire ;
- provenance in-toto compatible SLSA pour l'archive source ;
- signatures keyless Sigstore/Cosign des artefacts de release ;
- images GHCR construites avec SBOM/provenance BuildKit puis signées par Cosign ;
- policy-as-code Rego évaluée sur les manifests Helm rendus ;
- rotation de secrets uniquement pour les secrets explicitement `generated` ;
- rollback de release en deux phases avec plan temporaire et confirmation.

## Politique de rotation d'un secret généré

Lors de la création d'un secret `local_encrypted`, la référence peut inclure :

```json
{"rotation":{"mode":"generated","days":90}}
```

La tâche planifiée ne change jamais automatiquement un secret `env` ou `vault_kv2`.

## Rollback contrôlé

Le rollback est désactivé par défaut. Une fois activé, l'opérateur crée un plan vers une version strictement antérieure. Le jeton de confirmation n'est retourné qu'à la création et seul son SHA-256 est persisté. En mode `plan_only`, DataVision confirme le plan sans prétendre modifier l'infrastructure ; en mode `webhook`, le webhook HTTPS configuré reçoit une requête HMAC-signée.
