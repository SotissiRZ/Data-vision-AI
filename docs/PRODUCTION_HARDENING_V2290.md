# DataVision v2.29.0 — Production Hardening & CI/CD

## Objectif

Transformer les validations manuelles des versions précédentes en contrôles
répétables et audités.

## CI

`ci.yml` exécute :

1. installation Python 3.12 ;
2. suite pytest complète ;
3. installation Node 22 ;
4. `npm run typecheck` ;
5. `npm run build` ;
6. `docker compose config -q` ;
7. stack Docker complète ;
8. smoke tests Playwright.

## Health model

`live` signifie que le processus répond.

`ready` signifie que l'API peut accepter du trafic applicatif avec ses
composants obligatoires disponibles.

Le sandbox est signalé dans le payload de readiness mais ne bloque pas toute
l'API lorsqu'il est indisponible : seules les fonctions Notebook en dépendent.

## Sécurité CI

Le workflow `security.yml` exécute :

- pip-audit ;
- npm audit niveau high ;
- Trivy filesystem CRITICAL/HIGH ;
- publication SARIF dans GitHub Security.

Un résultat de scan n'est pas équivalent à une revue de sécurité complète.

## Release

La release taggée construit les images, construit réellement Next.js, génère
l'archive reproductible, vérifie son SHA256 et génère les SBOM.

## E2E

Les tests Playwright utilisent Chromium et une stack Docker réelle. Les
artefacts de trace, screenshot, vidéo et rapport HTML sont conservés en cas
d'échec.

## Limites

Cette version ne revendique pas que GitHub Actions a déjà tourné sur le dépôt
de l'utilisateur. Les workflows sont fournis et leur syntaxe/contrat sont
validés localement ; le premier run GitHub constitue la validation de la
plateforme CI distante.
