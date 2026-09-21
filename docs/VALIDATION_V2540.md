# Validation v2.54.0 — Collaboration

La v2.54.0 consolide la couche Collaboration & Review historique sans créer un second système parallèle.

## Gate

```text
python scripts/collaboration_acceptance.py --root . --check
```

Le contrat `COLLABORATION_ACCEPTANCE` exige 8/8 : équipes workspace, workflow de revue, commentaires/mentions/notifications, WebSocket temps réel avec ticket éphémère, diff de snapshots, journal de décisions, partage d'artefacts gouverné et événements sortants via Governed Actions.

## Sécurité

Le partage ne crée aucun lien public et n'élève jamais les droits du destinataire. Les permissions workspace, RLS/CLS et politiques existantes restent autoritaires. Le WebSocket n'expose pas le JWT dans l'URL : il utilise un ticket à usage unique et expiration courte.
