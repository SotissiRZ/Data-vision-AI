# Entreprise Action Connectors — v2.11

## Objectif

La v2.11 transforme le moteur Governed Actions en hub d'intégration. Une action ne devient exécutable qu'après passage par les règles du workspace, les conditions déterministes, la déduplication, le throttling, les quiet hours et la politique d'approbation.

## Connecteurs

| Type | Mode | Authentification | Effet |
|---|---|---|---|
| Webhook | HTTPS JSON | HMAC / Bearer / OAuth2 | POST générique |
| Slack | Incoming Webhook | URL chiffrée | message Slack |
| Slack | Web API | Bearer / OAuth2 client credentials | `chat.postMessage` |
| Teams | Workflow/Webhook | URL chiffrée | message Teams |
| Jira | Cloud REST API | Basic API token / Bearer / OAuth2 | création d'issue |
| Email | SMTP / STARTTLS / SSL | SMTP login / OAuth2 | envoi email |

Les secrets et endpoints de webhook sensibles sont chiffrés via l'enveloppe de secrets DataVision. Les réponses API n'exposent jamais le token, mot de passe, secret HMAC, API token ou URL de webhook sensible.

## Approbation multi-étapes

Une règle `approval_mode=chain` possède une liste ordonnée :

```json
[
  {"label":"Revue technique","role":"data_scientist"},
  {"label":"Validation finale","role":"admin"}
]
```

Chaque run matérialise sa propre copie des étapes. Le service valide l'identité et le rôle au moment de l'action. L'ordre est strict. Un rejet arrête l'exécution.

## OAuth2

La v2.11 supporte le grant `client_credentials` : token endpoint HTTPS, client ID/secret chiffrés, scope/audience optionnels et Bearer injection côté serveur. Le flow Authorization Code avec callback interactif n'est pas encore implémenté.

## Delivery adapters

La livraison est séparée du calcul analytique. Les workers n'obtiennent que le contexte du run et les credentials nécessaires au connecteur. Les tentatives sont auditées dans `action_delivery_attempts` avec code de réponse, latence et erreur.

## Sécurité

- RBAC : configuration et test réservés Owner/Admin ;
- chaînes d'approbation : rôle/utilisateur strict ;
- HTTPS et SSRF guard pour HTTP ;
- endpoints Slack/Teams/webhook sensibles chiffrés ;
- headers sensibles masqués dans les réponses ;
- idempotency, dedupe et throttle ;
- quiet hours ;
- retry/backoff Redis ;
- replay avec nouvel identifiant/fingerprint.

## Tables metadata ajoutées

- `action_destination_options` ;
- `action_rule_approval_chains` ;
- `action_approval_steps`.

Ces tables sont additives : une base v2.10 existante est complétée au démarrage par `CREATE TABLE IF NOT EXISTS`.
