# Validation v2.45.0 — Assistant multimodal et proactif

La v2.45.0 complète l'assistant avec un monitoring sémantique non invasif, un anti-spam déterministe, un contrôle utilisateur des interventions, des préférences vocales persistantes et des artefacts générés téléchargeables depuis la conversation.

## Gates

- `ASSISTANT_MULTIMODAL_ACCEPTANCE`: 8/8.
- tests dédiés: `backend/tests/assistant/test_assistant_v245.py` et `backend/tests/test_frontend_assistant_v245.py`.
- sécurité téléchargement: seuls les `artifact_path` produits par un step réussi et confinés au `data_root` sont servis.
