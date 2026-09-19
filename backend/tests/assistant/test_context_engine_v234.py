from __future__ import annotations

from pathlib import Path

from app.assistant.action_runs import ActionLifecycleManager, ActionRunStore
from app.assistant.artifact_memory import remember_run_artifacts
from app.assistant.executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from app.assistant.memory import SessionMemoryStore
from app.assistant.models import (
    AgentIntent,
    AgentPlanStep,
    AgentTurnRequest,
    AgentTurnRun,
    AgentTurnStep,
    AssistantContext,
)
from app.assistant.plan import validate_agent_plan
from app.assistant.planner_runtime import DeterministicPlanner
from app.assistant.reference_resolver import resolve_references
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import AssistantToolRegistry, ToolSpec, build_default_registry
from app.assistant.turn_runs import AgentTurnRunStore


def _context() -> AssistantContext:
    return AssistantContext(
        workspaceId="ws1",
        activeDatasetId="ds1",
        activeDatasetVersionId="1",
        screen="model",
        uiState={
            "datasetName": "sales.csv",
            "datasetSchema": [
                {"name": "Gender", "dtype": "object"},
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
            ],
        },
    )


def _memory_with_model(model_id: str = "model-42") -> SessionMemoryStore:
    memory = SessionMemoryStore()
    run = AgentTurnRun(
        session_id="s1",
        request_message="entraîne un modèle",
        context=_context(),
        intent=AgentIntent(name="predict_target", confidence=0.99),
        steps=[
            AgentTurnStep(
                tool="run_automl",
                label="AutoML",
                args={"target": "Profit"},
                status="succeeded",
                result={"model_id": model_id, "algorithm": "xgboost", "r2": 0.91},
            )
        ],
        current_step_index=1,
        status="completed",
    )
    remember_run_artifacts(memory, "s1", run)
    return memory


def _resolve(message: str, memory: SessionMemoryStore):
    return resolve_references(
        message=message,
        intent=AgentIntent(name="artifact_context", confidence=0.997),
        context=_context(),
        memory=memory.get_or_create("s1"),
    )


def test_referenced_model_can_be_promoted_without_guessing_model_id():
    resolution = _resolve("mets ce modèle en production", _memory_with_model())
    assert resolution.intent.name == "model_registry"
    assert resolution.intent.entities["target_stage"] == "production"
    assert resolution.context.activeModelId == "model-42"
    assert resolution.inherited is True


def test_stage_mention_without_mutation_verb_does_not_trigger_transition():
    resolution = _resolve("quel est le statut de ce modèle en production ?", _memory_with_model())
    assert resolution.intent.name == "model_registry"
    assert "target_stage" not in resolution.intent.entities
    assert resolution.context.activeModelId == "model-42"


def test_contextual_monitoring_restores_model_reference():
    resolution = _resolve("surveille ce modèle et vérifie le drift", _memory_with_model())
    assert resolution.intent.name == "monitor_model"
    assert resolution.context.activeModelId == "model-42"


def test_contextual_fairness_uses_explicit_group_column():
    resolution = _resolve("audite l'équité de ce modèle sur Gender", _memory_with_model())
    assert resolution.intent.name == "fairness_analysis"
    assert resolution.intent.entities["protected_columns"] == ["Gender"]
    assert resolution.context.activeModelId == "model-42"


def test_retraining_command_creates_governed_request_plan():
    memory = _memory_with_model()
    resolution = _resolve("réentraîne ce modèle", memory)
    assert resolution.intent.name == "retraining_check"
    assert resolution.intent.entities["create_request"] is True

    plan = DeterministicPlanner().plan(
        message="réentraîne ce modèle",
        intent=resolution.intent,
        context=resolution.context,
        attachment_ids=[],
    )
    assert len(plan) == 1
    assert plan[0].tool == "request_model_retraining"
    assert plan[0].args["create_request"] is True


def test_tool_registry_confirmation_metadata_is_enforced():
    registry = build_default_registry()
    plan = [
        AgentPlanStep(
            tool="request_model_retraining",
            label="Créer une demande de réentraînement",
            args={"create_request": True},
        )
    ]
    result = validate_agent_plan(
        steps=plan,
        context=AssistantContext(activeModelId="model-42"),
        registry=registry,
        authorization=AllowAllDevelopmentAuthorization(),
    )
    assert result.valid is True
    assert result.executable_without_confirmation is False
    assert result.steps[0].status == "confirmation_required"
    assert result.steps[0].risk == "reversible"


def test_turn_step_exposes_registry_risk_and_refusal_cancels():
    registry = AssistantToolRegistry()
    registry.register(
        ToolSpec(
            name="contextual_sensitive",
            description="test",
            category="test",
            risk="reversible",
            metadata={"human_confirmation_required": True},
        ),
        lambda **kwargs: {"ok": True},
    )

    class Planner:
        def plan(self, **kwargs):
            return [AgentPlanStep(tool="contextual_sensitive", label="Action sensible")]

    auth = AllowAllDevelopmentAuthorization()
    lifecycle = ActionLifecycleManager(
        executor=GovernedToolExecutor(registry, auth),
        store=ActionRunStore(),
    )
    orchestrator = build_orchestrator(
        registry=registry,
        authorization=auth,
        planner=Planner(),
        action_lifecycle=lifecycle,
        turn_store=AgentTurnRunStore(),
    )
    response = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="confirm-v234",
            message="analyse ce dataset",
            context=AssistantContext(activeDatasetId="ds1"),
        )
    )
    assert response.status == "waiting_confirmation"
    assert response.steps[0].risk == "reversible"
    action_id = response.pending_action_run_ids[0]
    lifecycle.confirm(action_id, False)
    resumed = orchestrator.continue_turn(
        response.metadata["turn_run_id"],
        confirmed_action_run_id=action_id,
    )
    assert resumed.status == "partial"
    assert "annul" in resumed.message.lower()


def test_frontend_has_explicit_confirm_and_reject_governance_controls():
    root = Path(__file__).resolve().parents[3]
    assistant = (root / "frontend/components/assistant/FloatingDataVisionAssistant.tsx").read_text(encoding="utf-8")
    adapter = (root / "frontend/lib/assistant/orchestrator-adapter.ts").read_text(encoding="utf-8")
    assert "✓ Confirmer" in assistant
    assert "Refuser" in assistant
    assert "adapter.rejectAction" in assistant
    assert "confirmed: false" in adapter
    assert "step.risk" in adapter
