from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_responsible_ai_routes_are_exposed():
    routes = (ROOT / "backend/app/api/routes/datasets.py").read_text()
    assert '/models/{model_id}/responsible-ai/fairness' in routes
    assert '/models/{model_id}/responsible-ai/gate' in routes
    assert '/models/{model_id}/responsible-ai/risk' in routes
    assert '/models/{model_id}/responsible-ai/drift' in routes


def test_assistant_tools_and_host_bridge_are_bound():
    tools = (ROOT / "backend/app/assistant/tools.py").read_text()
    host = (ROOT / "backend/app/assistant/host_v212.py").read_text()
    for name in [
        'evaluate_model_fairness',
        'assess_model_risk',
        'responsible_ai_publication_gate',
    ]:
        assert f'name="{name}"' in tools
        assert f'"{name}": ml.{name}' in host


def test_frontend_responsible_ai_view_is_integrated():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    component = (ROOT / "frontend/components/ResponsibleAIView.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()

    assert "'responsible'" in page
    assert "ResponsibleAIView" in page
    assert "DataVision ne déduit jamais automatiquement" in component
    assert "Publication gate" in component
    assert "runModelFairnessAudit" in api
    assert "runModelResponsibleAIGate" in api
    assert "runModelPopulationDrift" in api


def test_model_card_no_longer_marks_fairness_as_planned():
    modeling = (ROOT / "backend/app/services/modeling.py").read_text()
    assert '"fairness": {"status": "not_evaluated"' in modeling
    assert "Fairness avancée reste prévue" not in modeling


def test_model_certification_respects_persisted_responsible_ai_gate():
    collaboration = (ROOT / "backend/app/services/collaboration.py").read_text()
    assert 'review.get("resource_type") == "model"' in collaboration
    assert "Responsible AI Gate" in collaboration
    assert 'model_gate.get("allowed") is False' in collaboration


def test_assistant_can_route_explicit_fairness_requests():
    models = (ROOT / "backend/app/assistant/models.py").read_text()
    intent = (ROOT / "backend/app/assistant/intent.py").read_text()
    planner = (ROOT / "backend/app/assistant/planner_runtime.py").read_text()
    assert '"fairness_analysis"' in models
    assert '"model_risk"' in models
    assert '"fairness_analysis"' in intent
    assert 'if name == "fairness_analysis":' in planner
    assert 'if name == "model_risk":' in planner


def test_assistant_fairness_tools_have_typed_contracts():
    from app.assistant.contracts import validate_tool_arguments

    args = validate_tool_arguments(
        "evaluate_model_fairness",
        {
            "protected_columns": ["group"],
            "mode": "both",
            "min_group_size": 10,
        },
    )
    assert args["protected_columns"] == ["group"]

    try:
        validate_tool_arguments(
            "evaluate_model_fairness",
            {"protected_columns": []},
        )
    except Exception:
        pass
    else:
        raise AssertionError("Empty group selection must fail validation.")
