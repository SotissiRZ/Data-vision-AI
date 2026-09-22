# DataVision AI Security Policy

## Reporting

Do not open a public issue for a suspected vulnerability. Report it through the
private security channel configured by the deployment owner.

A useful report includes the affected version, reproduction steps, expected and
observed behavior, and whether credentials or tenant data may be exposed.

## Production baseline

Before a release is promoted to production:

- backend tests must pass;
- frontend typecheck and production build must pass;
- Docker Compose configuration must validate;
- smoke E2E tests must pass;
- dependency and filesystem security scans must run;
- the release archive must pass SHA256 verification;
- SBOM artifacts must be generated.

Secrets must never be committed to source control. Use `.env`, Secret Vault, or
deployment-specific secret injection.


## v2.31 — MFA, upload antivirus and envelope encryption

### Passkeys / WebAuthn
- Private keys remain in the authenticator.
- Registration and authentication challenges are short-lived and single-use.
- User verification is required for authentication ceremonies.
- After a user enrolls a passkey, password login requires WebAuthn.

### Upload antivirus
- Upload bytes are scanned before dataset persistence.
- Official Compose includes ClamAV.
- `ANTIVIRUS_MODE=required` is fail-closed and should be used in production.
- Scan metadata stores SHA256/status, never the uploaded bytes.

### Secret encryption
- New local encrypted secrets use AES-256-GCM with key IDs.
- Production readiness requires a dedicated `SECRET_KMS_KEY`.
- Legacy Fernet ciphertext remains decryptable during migration.
- Old keys can be retained temporarily through `SECRET_KMS_PREVIOUS_KEYS`.

## Dependency compatibility

The runtime pins `cryptography==46.0.5` to satisfy Snowflake Connector 4.7.4 while remaining compatible with OracleDB and WebAuthn.


## v2.34 — confirmation humaine gouvernée

Le drapeau de Tool Registry `human_confirmation_required=true` est maintenant
appliqué par les trois gates concernés : validation de plan, préparation de
l'exécution et endpoint de contrôle d'action. Une résolution contextuelle
(`ce modèle`, `ce résultat`) ne peut donc pas réduire le niveau de confirmation
requis par l'outil ciblé.

L'interface transmet le niveau de risque validé par le backend et permet un
refus explicite. Le refus est enregistré comme annulation du plan, sans lancer
les étapes suivantes.


## v2.35 — résolution sûre des références multi-artefacts

Le Context Engine v5 n'accorde aucune permission supplémentaire. Il résout
uniquement des références vers des artefacts déjà présents dans la mémoire de
session. Les actions continuent de passer par le Tool Registry, RBAC/RLS et les
confirmations humaines.

Lorsqu'une référence correspond à plusieurs artefacts possibles, DataVision
retourne une clarification explicite au lieu de choisir arbitrairement. Les
références liées à un dataset sont invalidées lors d'un changement de dataset.


## Semantic Project Recall (v2.37)

La recherche mémoire est calculée localement par un ranker déterministe. Aucun texte de mémoire projet n'est envoyé à un fournisseur d'embeddings. Les scopes workspace/local, RBAC et politiques de rétention de v2.36 restent autoritaires.


## v2.38 — Sécurité des actions de mémoire projet

Les artefacts mémorisés ne sont jamais exécutés directement. Une relance transforme uniquement la recette compacte en intention `replay_artifact`, puis repasse par le planificateur, le Tool Registry, la validation de contrat, RBAC/RLS et les confirmations humaines. Une allow-list interdit le replay de mutations telles que suppression de colonne, envoi externe, notebook, déploiement ou rollback. La réutilisation sur un autre dataset vérifie d'abord que toutes les colonnes mémorisées existent dans le schéma actif.
