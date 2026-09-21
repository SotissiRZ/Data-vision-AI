# Validation DataVision AI v2.53.2

Hotfix Trust Center : correction du contrat versions et garde-fous frontend.

- `result.versions` est une enveloppe API ; le lineage utilise désormais `result.versions.versions`.
- `checks`, `warnings` et `policy` sont normalisés avant rendu.
- Test de non-régression : `backend/tests/test_frontend_trust_center_v2532.py`.
