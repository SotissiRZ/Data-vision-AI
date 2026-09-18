# DataVision AI v2.10 — Governed Actions & Automation

## Objectif
Fermer la boucle entre insight et action sans transformer l'analytique en moteur autonome non contrôlé. Toute action externe est liée à un workspace, une identité, une règle, un événement et une piste d'audit.

## Modèle
- `action_destinations` : destinations webhook, secret chiffré, headers autorisés.
- `action_rules` : événement, dataset optionnel, conditions, approbation, throttling, déduplication, quiet hours, template, retry.
- `action_runs` : état de l'action, fingerprint, approbation, scheduling, réponse, replay.
- `action_delivery_attempts` : une ligne par tentative réseau.

## États
`pending_approval → approved/queued → running → completed|failed`, avec `scheduled`, `rejected` et `suppressed_throttle` selon le contrôle appliqué.

## Sécurité
1. RBAC spécifique `actions:read/manage/trigger/approve`.
2. Webhook HTTPS obligatoire hors localhost de développement.
3. Résolution DNS avant livraison et blocage des IP privées/réservées.
4. HMAC-SHA256 sur `timestamp.body`; le secret n'est jamais renvoyé par l'API.
5. `Idempotency-Key` fondée sur le fingerprint de l'action.
6. Un job `action_delivery` est interne et n'est pas exposé comme type soumettable par l'API générique.
7. Le worker vérifie que le run appartient au même workspace que le job.

## Conditions
Les conditions utilisent un petit DSL déterministe : `eq`, `neq`, `in`, `contains`, `gt`, `gte`, `lt`, `lte`, `exists`. Aucune évaluation de code utilisateur n'est utilisée.

## Quiet hours
Les plages horaires utilisent `zoneinfo` avec timezone IANA. Si l'action tombe dans la plage silencieuse, elle est stockée `scheduled`. Le worker appelle `process_due_runs()` lors de sa boucle de scheduling.

## Payload templates
- `{{event.metric_label}}` produit une interpolation texte.
- `${event.severity}` conserve le type natif lorsqu'il occupe toute la valeur.
- `_datavision` apporte event id/type, workspace et dataset sans inclure les données brutes.

## Intégrations natives v2.10
- Proactive Intelligence → `proactive_alert`.
- Data Contract en échec → `reliability_failure`.
- Review approuvée → `review_approved`.
- Certification créée → `certification_created`.
- Déclenchement manuel contrôlé → `manual`.

## Limites volontaires
La v2.10 fournit un connecteur webhook générique et sécurisé. Les connecteurs SaaS natifs OAuth (Slack, Teams, Jira, email transactionnel), approvals multi-étapes, vault externe et allowlists réseau administrées sont planifiés pour les versions suivantes.
