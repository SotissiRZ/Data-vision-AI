from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_v220_routes_are_exposed():
    routes = (
        ROOT / "backend/app/api/routes/datasets.py"
    ).read_text()

    assert '"/{dataset_id}/root-cause"' in routes
    assert '"/models/{model_id}/optimize-scenarios"' in routes


def test_assistant_exposes_decision_tools():
    tools = (
        ROOT / "backend/app/assistant/tools.py"
    ).read_text()
    host = (
        ROOT / "backend/app/assistant/host_v212.py"
    ).read_text()
    planner = (
        ROOT / "backend/app/assistant/planner_runtime.py"
    ).read_text()

    assert 'name="run_root_cause_analysis"' in tools
    assert 'name="optimize_decision_scenarios"' in tools
    assert '"run_root_cause_analysis": analysis.run_root_cause_analysis' in host
    assert '"optimize_decision_scenarios": ml.optimize_decision_scenarios' in host
    assert 'if name == "root_cause_analysis":' in planner
    assert 'if name == "optimize_scenarios":' in planner


def test_frontend_decision_lab_contains_rca_and_optimizer():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()

    assert "Root Cause Analysis — décomposition de l’écart" in page
    assert "Optimisation multi-scénarios" in page
    assert "Identifier les facteurs" in page
    assert "runRootCauseAnalysis" in api
    assert "optimizeModelScenarios" in api
