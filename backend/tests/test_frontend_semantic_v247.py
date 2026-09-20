from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")


def test_v247_semantic_studio_exposes_business_governance_fields():
    assert "Définition métier" in PAGE
    assert "Rôles autorisés" in PAGE
    assert "business_definition" in PAGE
    assert "allowed_roles" in PAGE


def test_v247_semantic_studio_exposes_linked_glossary():
    assert "Glossaire métier lié" in PAGE
    assert "target_type" in PAGE
    assert "target_id" in PAGE
    assert "Ajouter au glossaire" in PAGE


def test_v247_query_workspace_exposes_semantic_resolution_trace():
    assert "Résolution :" in PAGE
    assert "semantic_grounding.relationships" in PAGE
    assert "sql_validation" in PAGE
    assert "SQL/plan read-only validé" in PAGE


def test_v247_frontend_uses_governed_semantic_api():
    assert "/semantic/validate" in API
    assert "/semantic/query" in API
    assert "/workspace/nlq" in API
