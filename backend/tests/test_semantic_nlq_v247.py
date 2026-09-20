from __future__ import annotations

import pandas as pd
import pytest

from app.services.semantic_layer import (
    get_semantic_model,
    query_semantic_metric,
    save_semantic_model,
    validate_semantic_model,
)
from app.services.semantic_nlq import plan_semantic_question
from app.services.nlq_sql import run_nlq
from app.services.storage import save_dataframe_source
from app.services.tenant_access import DataAccessContext, reset_access_context, set_access_context


def _ctx(role: str) -> DataAccessContext:
    return DataAccessContext(
        user_id=f"user-{role}",
        email=f"{role}@example.test",
        workspace_id="ws-semantic",
        role=role,
        organization_id="org-semantic",
    )


def _make_model(fact_id: str, dim_id: str | None = None) -> dict:
    tables = [{
        "id": "base", "dataset_id": fact_id, "label": "Sales", "role": "fact", "active": True,
        "description": "Transactions commerciales", "allowed_roles": [],
    }]
    relationships = []
    dimensions = [{
        "id": "region", "table": "base", "column": "region", "label": "Région",
        "kind": "categorical", "hidden": False, "certified": True,
        "business_definition": "Zone commerciale de rattachement", "synonyms": ["zone"],
        "allowed_roles": [],
    }]
    if dim_id:
        tables.append({
            "id": "product", "dataset_id": dim_id, "label": "Products", "role": "dimension",
            "active": True, "allowed_roles": [],
        })
        relationships.append({
            "id": "sales_product", "from_table": "base", "from_column": "product_id",
            "to_table": "product", "to_column": "product_id", "cardinality": "many_to_one",
            "join_type": "left", "active": True, "description": "Produit de la vente", "allowed_roles": [],
        })
        dimensions.append({
            "id": "category", "table": "product", "column": "category", "label": "Catégorie produit",
            "kind": "categorical", "hidden": False, "certified": True,
            "business_definition": "Famille commerciale du produit", "synonyms": ["famille"],
            "allowed_roles": [],
        })
    return {
        "tables": tables,
        "relationships": relationships,
        "metrics": [{
            "id": "revenue", "name": "Revenue", "label": "Chiffre d'affaires", "type": "base",
            "table": "base", "column": "revenue", "aggregation": "sum", "unit": "EUR",
            "format": "currency", "business_definition": "Montant facturé hors taxes",
            "synonyms": ["CA", "ventes"], "certified": True,
            "allowed_roles": ["owner", "admin", "analyst"],
        }],
        "dimensions": dimensions,
        "hierarchies": [],
        "business_glossary": [{
            "term": "turnover", "definition": "Synonyme métier international du chiffre d'affaires",
            "target_type": "metric", "target_id": "revenue", "synonyms": ["sales turnover"],
            "allowed_roles": ["owner", "admin", "analyst"],
        }],
    }


def test_v247_semantic_contract_normalizes_governance_metadata(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = pd.DataFrame({"region": ["N", "S"], "revenue": [100.0, 80.0]})
    meta = save_dataframe_source(df, "sales.csv")
    model = _make_model(meta["id"])
    validation = validate_semantic_model(meta["id"], df, model)
    assert validation["valid"] is True
    saved = save_semantic_model(meta["id"], df, model)
    metric = saved["metrics"][0]
    assert saved["semantic_version"] == 2
    assert metric["business_definition"] == "Montant facturé hors taxes"
    assert metric["unit"] == "EUR"
    assert metric["allowed_roles"] == ["owner", "admin", "analyst"]
    assert saved["business_glossary"][0]["target_id"] == "revenue"


def test_v247_glossary_resolves_nlq_and_exposes_grounding(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = pd.DataFrame({"region": ["Nord", "Nord", "Sud"], "revenue": [100.0, 120.0, 80.0]})
    meta = save_dataframe_source(df, "sales.csv")
    save_semantic_model(meta["id"], df, _make_model(meta["id"]))

    plan = plan_semantic_question(meta["id"], df, "Quel est le turnover par zone ?")
    assert plan is not None
    assert plan["metric_id"] == "revenue"
    assert plan["metric_match_term"] == "turnover"
    assert plan["metric_unit"] == "EUR"
    assert plan["metric_definition"] == "Montant facturé hors taxes"
    assert plan["dimensions"] == ["region"]

    out = run_nlq(df, "Quel est le turnover par zone ?", 100, get_semantic_model(meta["id"], df), meta["id"])
    assert out["execution_mode"] == "semantic"
    assert out["semantic_grounding"]["metric_id"] == "revenue"
    assert out["semantic_grounding"]["matched_term"] == "turnover"
    assert out["semantic_grounding"]["metric_unit"] == "EUR"
    assert out["sql_validation"]["read_only"] is True
    assert out["sql_validation"]["deterministic_execution"] is True


def test_v247_multitable_query_traces_relationships(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    fact = pd.DataFrame({"product_id": [1, 2, 1], "region": ["N", "S", "N"], "revenue": [100.0, 200.0, 50.0]})
    dim = pd.DataFrame({"product_id": [1, 2], "category": ["A", "B"]})
    fact_meta = save_dataframe_source(fact, "fact.csv")
    dim_meta = save_dataframe_source(dim, "products.csv")
    save_semantic_model(fact_meta["id"], fact, _make_model(fact_meta["id"], dim_meta["id"]))

    out = query_semantic_metric(fact_meta["id"], fact, "revenue", ["category"])
    assert out["value"] == 350.0
    assert out["tables_used"] == ["base", "product"]
    assert out["relationships_used"] == ["sales_product"]
    assert {row["category"]: row["value"] for row in out["result"]} == {"B": 200.0, "A": 150.0}

    nlq = run_nlq(fact, "turnover par famille", 100, get_semantic_model(fact_meta["id"], fact), fact_meta["id"])
    assert nlq["execution_mode"] == "semantic"
    assert nlq["semantic_grounding"]["relationships"] == ["sales_product"]
    assert "sales_product" in nlq["sql"]


def test_v247_semantic_role_filter_and_no_nlq_bypass(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = pd.DataFrame({"region": ["N", "S"], "revenue": [100.0, 80.0]})
    meta = save_dataframe_source(df, "sales.csv")
    save_semantic_model(meta["id"], df, _make_model(meta["id"]))

    token = set_access_context(_ctx("viewer"))
    try:
        visible = get_semantic_model(meta["id"], df)
        assert visible["access"]["role"] == "viewer"
        assert visible["metrics"] == []
        with pytest.raises(PermissionError, match="métrique"):
            query_semantic_metric(meta["id"], df, "revenue")
        with pytest.raises(PermissionError, match="métrique"):
            run_nlq(df, "Quel est le chiffre d'affaires ?", 100, visible, meta["id"])
    finally:
        reset_access_context(token)

    token = set_access_context(_ctx("analyst"))
    try:
        visible = get_semantic_model(meta["id"], df)
        assert [m["id"] for m in visible["metrics"]] == ["revenue"]
        assert query_semantic_metric(meta["id"], df, "revenue")["value"] == 180.0
    finally:
        reset_access_context(token)


def test_v247_invalid_semantic_roles_are_rejected_by_validation(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "data_root", tmp_path)
    df = pd.DataFrame({"region": ["N"], "revenue": [100.0]})
    meta = save_dataframe_source(df, "sales.csv")
    model = _make_model(meta["id"])
    model["metrics"][0]["allowed_roles"] = ["superuser"]
    validation = validate_semantic_model(meta["id"], df, model)
    assert validation["valid"] is False
    assert any("rôles inconnus" in err for err in validation["errors"])
