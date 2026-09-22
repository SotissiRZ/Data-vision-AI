# DataVision AI v2.56.0 — Plateforme Entreprise

La v2.56.0 consolide les fonctions destinées aux déploiements d’organisation sans créer un second moteur parallèle. Elle réutilise les primitives déjà présentes — RBAC/RLS/CLS, OIDC, WebAuthn, coffre de secrets, moteur de politiques IA, télémétrie — et ajoute les contrôles manquants.

## Identité et provisioning

- découverte OIDC par domaine email via `GET /api/v1/auth/oidc/discover` ;
- SSO OIDC Authorization Code + PKCE déjà présent, conservé ;
- MFA WebAuthn déjà présent, conservé ;
- jetons SCIM générés avec préfixe `dvscim_`, retournés une seule fois et persistés uniquement sous forme SHA-256 ;
- cycle SCIM 2.0 `Users` : liste, création/JIT, lecture, patch et désactivation ;
- rôle SCIM propagé aux memberships organisation et workspace, sans contournement du modèle RBAC existant.

## Private AI

`POST /api/v1/workspaces/{workspace_id}/entreprise/private-ai/enforce` applique la politique stricte du moteur IA existant :

- `privacy_mode=local_only` ;
- `allow_external_ai=false` ;
- aucune ligne brute vers un fournisseur externe ;
- aucune valeur d’échantillon vers un fournisseur externe.

La posture reste lisible via `GET /api/v1/workspaces/{workspace_id}/entreprise/private-ai`.

## Déploiement on-prem

Deux paramètres documentent la posture de déploiement :

- `DEPLOYMENT_PROFILE=onprem` par défaut ;
- `EXTERNAL_EGRESS_POLICY=explicit_opt_in` par défaut.

Ils complètent le déploiement Docker Compose existant, Postgres/Redis, réseau sandbox isolé et coffre de secrets chiffré. Ils ne prétendent pas remplacer les contrôles réseau de l’infrastructure hôte : firewall, proxy, DNS, segmentation et politiques Kubernetes restent sous responsabilité du déploiement.

## Observabilité

`GET /api/v1/workspaces/{workspace_id}/metrics/prometheus` expose au format Prometheus, sous permission `observability:read` :

- volume HTTP ;
- erreurs 5xx ;
- latence p95 ;
- jobs en échec ;
- tokens IA entrants/sortants ;
- coût IA estimé.

Chaque série est scindée par `workspace_id`.

## Cockpit Entreprise

La vue Gouvernance affiche une posture calculée : isolation tenant, SSO, MFA, SCIM, Private AI, chiffrement, antivirus et observabilité, plus le profil de déploiement. Le bouton **Forcer Private AI** applique la politique stricte au workspace actif.

## Compatibilité

Les libellés produit utilisent **Entreprise**. Certains identifiants techniques historiques (`enterprise.py`, fonctions `getEnterprise…`, clés `dv_enterprise_*`, route legacy `/enterprise/status`) sont volontairement conservés afin de ne pas casser les clients existants. La route canonique d’affichage est `/entreprise/status`.
