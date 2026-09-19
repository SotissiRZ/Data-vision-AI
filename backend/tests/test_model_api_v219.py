from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_model_api_contains_v219_routes():
    routes = (
        ROOT / "backend/app/api/routes/datasets.py"
    ).read_text()

    assert '/{dataset_id}/models/benchmark' in routes
    assert '/models/{model_id}/xai/pdp' in routes
    assert '/models/{model_id}/xai/shap' in routes
    assert '/models/{model_id}/xai/counterfactuals' in routes
    assert '/models/{model_id}/xai/capabilities' in routes


def test_assistant_host_exposes_benchmark_and_full_xai():
    tools = (
        ROOT / "backend/app/assistant/tools.py"
    ).read_text()
    host = (
        ROOT / "backend/app/assistant/host_v212.py"
    ).read_text()

    assert 'name="benchmark_models"' in tools
    assert '"benchmark_models": ml.benchmark_models' in host
    assert 'method in {"shap", "shap_global", "shap_local"}' in host
    assert 'method == "partial_dependence"' in host
    assert 'method in {"counterfactual", "counterfactuals"}' in host


def test_frontend_exposes_advanced_benchmark_and_xai():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()

    for label in ("SVM", "XGBoost", "LightGBM", "CatBoost"):
        assert label in page

    assert "Calculer SHAP" in page
    assert "Dépendance partielle (PDP)" in page
    assert "Chercher des contre-factuels" in page
    assert "runModelBenchmark" in api
    assert "runModelSHAP" in api
    assert "runModelPDP" in api
    assert "runModelCounterfactuals" in api
