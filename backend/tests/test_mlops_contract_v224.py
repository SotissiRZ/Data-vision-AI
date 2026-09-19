from pathlib import Path

from app.assistant.contracts import validate_tool_arguments
from app.assistant.models import AssistantAction, AssistantContext
from app.assistant.policy import evaluate_action_policy

ROOT = Path(__file__).resolve().parents[2]


def test_v224_api_routes_exist():
    routes = (ROOT / "backend/app/api/routes/datasets.py").read_text()
    for path in [
        "/models/registry/summary",
        "/models/registry/entries",
        "/models/{model_id}/registry/register",
        "/models/{model_id}/registry/transition",
        "/models/{model_id}/monitor",
        "/models/{model_id}/monitor-schedule",
        "/models/{model_id}/retraining-policy",
        "/models/{model_id}/retraining/check",
    ]:
        assert path in routes


def test_mlops_assistant_tools_are_typed_and_governed():
    stage = validate_tool_arguments(
        "transition_model_stage",
        {"target_stage": "production", "note": "approved"},
    )
    assert stage["target_stage"] == "production"

    monitor = validate_tool_arguments(
        "monitor_model_health",
        {"current_dataset_id": "ds-current"},
    )
    assert monitor["current_dataset_id"] == "ds-current"

    check = evaluate_action_policy(
        AssistantAction(
            id="a1",
            tool="transition_model_stage",
            label="Promote",
            args={"target_stage": "production"},
            risk="destructive",
        ),
        AssistantContext(activeModelId="m1"),
    )
    assert check.decision == "confirmation_required"


def test_frontend_registry_is_integrated():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    component = (ROOT / "frontend/components/ModelRegistryView.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()

    assert "'registry'" in page
    assert "ModelRegistryView" in page
    assert "Model Registry & MLOps" in component
    assert "Monitoring périodique" in component
    assert "Politique de réentraînement" in component
    assert "transitionModelStage" in api
    assert "runModelMonitoring" in api
    assert "saveModelMonitorSchedule" in api


def test_job_worker_supports_model_monitor():
    jobs = (ROOT / "backend/app/services/job_service.py").read_text()
    worker = (ROOT / "backend/app/worker.py").read_text()
    assert '"model_monitor"' in jobs
    assert "claim_due_monitor_schedules" in worker
    assert "_enqueue_due_model_monitors" in worker
