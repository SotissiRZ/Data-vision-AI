# Validation — DataVision AI v2.12.0

## Backend

```text
pytest -q
64 passed
```

La suite couvre notamment :

- rotation d'un refresh token et invalidation de l'ancien ;
- révocation serveur d'une session ;
- liste des sessions utilisateur ;
- secrets `local_encrypted` versionnés ;
- références vers variables d'environnement ;
- démarrage OIDC avec state + PKCE ;
- échange OIDC et provisioning JIT ;
- state OIDC à usage unique ;
- validation cryptographique RS256 avec une clé RSA/JWKS de test ;
- résolution d'un secret HashiCorp Vault KV v2 avec transport HTTP simulé ;
- compatibilité des tests historiques v0.x → v2.11.

## Vérifications statiques

```text
Python compileall                    : OK
TS/TSX transpilation ciblée          : OK
strictNullChecks ciblé               : OK
Ports                                : 3005 / 8005
```

La validation TypeScript ciblée couvre `app/page.tsx`, `app/layout.tsx` et `lib/api.ts` avec `strictNullChecks=true`. Le stub de validation est supprimé avant packaging.

## Ce qui n'est pas revendiqué comme validé

- `next build` complet dans Docker sur la machine cible ;
- connexion réelle à un fournisseur OIDC externe ;
- appel réel à un serveur HashiCorp Vault externe ;
- comportements propres à chaque IdP au-delà du profil OIDC testé ;
- haute disponibilité multi-réplicas du metadata store/session layer.

Ces points nécessitent un environnement réseau et des credentials réels. La v2.12 teste la logique applicative, la cryptographie RS256, les politiques de session et les adaptateurs de transport avec doubles contrôlés.
