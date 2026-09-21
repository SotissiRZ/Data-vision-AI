from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_v256_frontend_exposes_entreprise_posture_without_visible_english_label():
    page = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/lib/api.ts").read_text(encoding="utf-8")
    assert "Posture Entreprise · v2.58" in page
    assert "Forcer Private AI" in page
    assert "Session Enterprise requise" not in page
    assert "profil Enterprise" not in page
    assert "Initialiser DataVision Enterprise" not in page
    assert "/entreprise/readiness" in api
    assert "Statut Entreprise indisponible" in api


def test_v256_backend_declares_routes_and_release_version():
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    routes = (ROOT / "backend/app/api/routes/enterprise.py").read_text(encoding="utf-8")
    service = (ROOT / "backend/app/services/entreprise_platform.py").read_text(encoding="utf-8")
    current_version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    assert f'version="{current_version}"' in main
    assert f'"version": "{current_version}"' in main
    assert '@router.get("/entreprise/status")' in routes
    assert '@router.get("/workspaces/{workspace_id}/entreprise/readiness")' in routes
    assert '@router.get("/workspaces/{workspace_id}/metrics/prometheus"' in routes
    assert '"edition": "Entreprise"' in service
    assert "token_hash" in service and "hashlib.sha256" in service
