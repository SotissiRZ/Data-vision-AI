from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_v225_api_routes_exist():
    routes = (
        ROOT / "backend/app/api/routes/datasets.py"
    ).read_text()
    for route in [
        '"/feature-store"',
        '"/feature-store/{feature_set_id}/materialize"',
        '"/models/{model_id}/feature-contract"',
        '"/serving/deployments"',
        '"/serving/{endpoint_key}/predict"',
        '"/models/{model_id}/batch-score"',
    ]:
        assert route in routes


def test_v225_assistant_tools_are_bound_and_typed():
    tools = (
        ROOT / "backend/app/assistant/tools.py"
    ).read_text()
    host = (
        ROOT / "backend/app/assistant/host_v212.py"
    ).read_text()
    contracts = (
        ROOT / "backend/app/assistant/contracts.py"
    ).read_text()

    for name in [
        "list_feature_sets",
        "materialize_feature_set",
        "list_model_deployments",
        "score_model_deployment",
        "batch_score_model",
        "rollback_model_deployment",
    ]:
        assert f'name="{name}"' in tools
        assert f'"{name}": mlops.{name}' in host

    for name in [
        '"materialize_feature_set": FeatureMaterializeArgs',
        '"score_model_deployment": DeploymentScoreArgs',
        '"batch_score_model": BatchScoreArgs',
        '"rollback_model_deployment": DeploymentRollbackArgs',
    ]:
        assert name in contracts


def test_frontend_mounts_feature_store_and_serving():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    component = (
        ROOT / "frontend/components/FeatureServingView.tsx"
    ).read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()

    assert "FeatureServingView" in page
    assert "Feature Store & Serving" in page
    assert "SHADOW · CANARY · ROLLBACK" in component
    assert "Aucun cloud deployment n’est simulé" in component
    assert "getFeatureSets" in api
    assert "createModelDeployment" in api
    assert "scoreModelDeployment" in api
    assert "batchScoreModel" in api
