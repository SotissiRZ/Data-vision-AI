# Migration v2.53.3 → v2.54.0

Aucune migration destructive n'est requise. Au démarrage, le metadata store crée automatiquement les tables collaboration supplémentaires (`collaboration_teams`, `collaboration_team_members`, `collaboration_artifact_shares`, `collaboration_ws_tickets`) via `CREATE TABLE IF NOT EXISTS`.

Les revues, commentaires, certifications, utilisateurs, workspaces et datasets existants restent inchangés.
