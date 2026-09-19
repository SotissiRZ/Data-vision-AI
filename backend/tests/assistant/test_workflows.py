from app.assistant.workflows import list_workflows


def test_core_workflows_exist():
    workflows = {item["id"]: item for item in list_workflows()}
    assert "analyze_dataset" in workflows
    assert "predict_target" in workflows
    assert "geospatial_analysis" in workflows
