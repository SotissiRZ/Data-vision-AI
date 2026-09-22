# DataVision AI — Security Policy

## Signalement d’une vulnérabilité

Ne publiez pas une vulnérabilité suspectée dans un ticket public. Utilisez le canal de sécurité privé défini par le propriétaire du déploiement.

Un signalement utile doit inclure la version concernée, les étapes de reproduction, le comportement attendu et observé, ainsi que l’impact potentiel sur les identités, secrets, workspaces ou données.

## Baseline production

Avant promotion en production, DataVision exige notamment :

- authentification obligatoire (`AUTH_MODE=required`) ;
- secrets hors du dépôt et rotation planifiée ;
- tests backend et frontend validés ;
- gates de sécurité et de release validés ;
- scans de dépendances, images et SBOM ;
- configuration Docker/Kubernetes validée ;
- archive de release vérifiée par SHA-256 ;
- sauvegarde/restauration et procédures d’exploitation testées.

Le mode `AUTH_MODE=local_dev` est réservé au développement et ne doit pas être utilisé en production.

## Documentation sécurité

- Rapport complet : [`docs/RAPPORT_SECURITE.md`](docs/RAPPORT_SECURITE.md)
- Références techniques : [`docs/security/`](docs/security/)
- Politique historique V2.81 avant nettoyage documentaire : [`docs/security/SECURITY_POLICY_HISTORY_V281.md`](docs/security/SECURITY_POLICY_HISTORY_V281.md)

Aucun test interne ne garantit l’absence absolue de vulnérabilité. Une validation de production doit inclure les scans automatisés prévus et, pour un déploiement sensible, un pentest indépendant.
