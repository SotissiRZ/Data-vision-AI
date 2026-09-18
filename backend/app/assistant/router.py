from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .activity import ActivityMonitor, alerts_from_activity
from .contracts import tool_json_schema, validate_tool_arguments
from .action_runs import ActionLifecycleManager, ActionRunStore
from .executor import AllowAllDevelopmentAuthorization, GovernedToolExecutor
from .context_store import InMemoryAssistantContextStore
from .models import (
    ActionCheckRequest,
    ActionCheckResponse,
    AgentTurnRequest,
    AgentTurnResponse,
    AgentTurnContinueRequest,
    AgentTurnCancelRequest,
    AgentTurnRun,
    ActionRun,
    ActionRunCreateRequest,
    ActionRunConfirmRequest,
    ActionRunRollbackRequest,
    AgentPlanValidationRequest,
    AgentPlanValidationResponse,
    ActivityObservationResponse,
    ObserveRequest,
    ObserveResponse,
    ToolCatalogItem,
)
from .policy import evaluate_action_policy
from .plan import validate_agent_plan
from .proactive import evaluate_proactive_event
from .realtime import AssistantRealtimeHub, RealtimeMessage
from .runtime import build_orchestrator
from .turn_runs import AgentTurnRunStore
from .tools import build_default_registry
from .workflows import list_workflows

router = APIRouter(prefix="/ai/assistant", tags=["assistant-v2.13"])
store = InMemoryAssistantContextStore()
tool_registry = build_default_registry()
activity_monitors: dict[str, ActivityMonitor] = defaultdict(ActivityMonitor)

authorization = AllowAllDevelopmentAuthorization()
tool_executor = GovernedToolExecutor(tool_registry, authorization)
action_run_store = ActionRunStore()
action_lifecycle = ActionLifecycleManager(
    executor=tool_executor,
    store=action_run_store,
)
realtime_hub = AssistantRealtimeHub()
turn_run_store = AgentTurnRunStore()
agent_orchestrator = build_orchestrator(
    registry=tool_registry,
    authorization=authorization,
    action_lifecycle=action_lifecycle,
    turn_store=turn_run_store,
)


@router.get("/health")
def assistant_health():
    return {
        "status": "ok",
        "component": "conversational_voice_agent",
        "version": "2.13.1",
        "tool_count": len(tool_registry.list()),
    }


@router.get("/tools", response_model=list[ToolCatalogItem])
def list_tools():
    return [
        ToolCatalogItem(
            name=spec.name,
            description=spec.description,
            category=spec.category,
            risk=spec.risk,
            input_schema=tool_json_schema(spec.name),
            required_permissions=list(spec.required_permissions),
            requires_dataset=spec.requires_dataset,
            requires_model=spec.requires_model,
            deterministic=spec.deterministic,
        )
        for spec in tool_registry.list()
    ]


@router.post("/observe", response_model=ObserveResponse)
def observe(request: ObserveRequest):
    context = store.update(request.context, request.event)
    alerts = evaluate_proactive_event(request.event, context)

    key = context.workspaceId or "__anonymous__"
    monitor = activity_monitors[key]
    monitor.add(request.event)
    activity_alerts = alerts_from_activity(monitor.detect())

    seen = {(a.title, a.message) for a in alerts}
    for alert in activity_alerts:
        signature = (alert.title, alert.message)
        if signature not in seen:
            alerts.append(alert)
            seen.add(signature)


# Realtime delivery is handled separately by the host/event loop in production.
# The synchronous observe endpoint still returns all alerts immediately.
return ObserveResponse(alerts=alerts)


@router.post("/activity/check", response_model=ActivityObservationResponse)
def check_activity(request: ObserveRequest):
    context = store.update(request.context, request.event)
    key = context.workspaceId or "__anonymous__"
    monitor = activity_monitors[key]
    monitor.add(request.event)
    signals = monitor.detect()
    return ActivityObservationResponse(
        alerts=alerts_from_activity(signals),
        signals=[
            {
                "kind": signal.kind,
                "score": signal.score,
                "explanation": signal.explanation,
            }
            for signal in signals
        ],
    )


@router.post("/action/check", response_model=ActionCheckResponse)
def check_action(request: ActionCheckRequest):
    # Assistant gate only. Existing DataVision RBAC/RLS checks must still run.
    spec = tool_registry.get(request.action.tool)
    if spec is None:
        return ActionCheckResponse(
            decision="deny",
            reason=f"Outil non enregistré : {request.action.tool}",
        )
    canonical_action = request.action.model_copy(update={"risk": spec.risk})
    return evaluate_action_policy(canonical_action, request.context)


@router.post("/plan/validate", response_model=AgentPlanValidationResponse)
def validate_plan(request: AgentPlanValidationRequest):
    # Replace AllowAllDevelopmentAuthorization with the host RBAC/RLS bridge
    # when integrating into the real DataVision v2.12 repository.
    return validate_agent_plan(
        steps=request.steps,
        context=request.context,
        registry=tool_registry,
        authorization=AllowAllDevelopmentAuthorization(),
    )


@router.post("/actions", response_model=ActionRun)
async def propose_action(request: ActionRunCreateRequest):
    run = action_lifecycle.propose(
        action=request.action,
        context=request.context,
        session_id=request.session_id,
    )
    await realtime_hub.publish(
        request.context.workspaceId or "__anonymous__",
        RealtimeMessage.create(
            "assistant.action",
            {
                "run_id": run.id,
                "status": run.status,
                "tool": run.action.tool,
                "label": run.action.label,
            },
        ),
    )
    return run


@router.post("/actions/{run_id}/confirm", response_model=ActionRun)
async def confirm_action(run_id: str, request: ActionRunConfirmRequest):
    try:
        run = action_lifecycle.confirm(run_id, request.confirmed)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await realtime_hub.publish(
        run.context.workspaceId or "__anonymous__",
        RealtimeMessage.create(
            "assistant.action",
            {"run_id": run.id, "status": run.status},
        ),
    )
    return run


@router.post("/actions/{run_id}/execute", response_model=ActionRun)
async def execute_action(run_id: str):
    try:
        run = action_lifecycle.execute(run_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await realtime_hub.publish(
        run.context.workspaceId or "__anonymous__",
        RealtimeMessage.create(
            "assistant.action",
            {
                "run_id": run.id,
                "status": run.status,
                "result": run.result if run.status == "succeeded" else None,
                "error": run.error,
            },
        ),
    )
    return run


@router.get("/actions/{run_id}", response_model=ActionRun)
def get_action(run_id: str):
    run = action_run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Action run introuvable.")
    return run


@router.post("/actions/{run_id}/rollback", response_model=ActionRun)
async def mark_action_rolled_back(run_id: str, request: ActionRunRollbackRequest):
    """
    This endpoint records a rollback after the host DataVision engine has
    actually performed the undo/version rollback. It must not be used as a
    substitute for the real rollback operation.
    """
    try:
        run = action_lifecycle.mark_rolled_back(run_id, request.reason)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await realtime_hub.publish(
        run.context.workspaceId or "__anonymous__",
        RealtimeMessage.create(
            "assistant.action",
            {"run_id": run.id, "status": run.status},
        ),
    )
    return run


@router.get("/events")
def assistant_event_stream(workspace_id: str | None = None):
    channel = workspace_id or "__anonymous__"
    return StreamingResponse(
        realtime_hub.subscribe(channel),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tools/{tool_name}/validate")
def validate_tool_input(tool_name: str, payload: dict):
    spec = tool_registry.get(tool_name)
    if spec is None:
        raise HTTPException(status_code=404, detail="Outil inconnu.")
    try:
        normalized = validate_tool_arguments(tool_name, payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "tool": tool_name,
        "valid": True,
        "normalized": normalized,
        "schema": tool_json_schema(tool_name),
    }


@router.get("/workflows")
def assistant_workflows():
    return {"workflows": list_workflows()}


@router.post("/turn", response_model=AgentTurnResponse)
async def run_agent_turn(request: AgentTurnRequest):
    response = agent_orchestrator.run_turn(request)

    await realtime_hub.publish(
        request.context.workspaceId or "__anonymous__",
        RealtimeMessage.create(
            "assistant.message",
            {
                "session_id": request.session_id,
                "status": response.status,
                "message": response.message,
                "speak": response.speak,
                "pending_action_run_ids": response.pending_action_run_ids,
            },
        ),
    )

    return response


@router.get("/turns/{turn_run_id}", response_model=AgentTurnRun)
def get_agent_turn(turn_run_id: str):
    try:
        return agent_orchestrator.get_turn(turn_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/turns/{turn_run_id}/continue", response_model=AgentTurnResponse)
async def continue_agent_turn(
    turn_run_id: str,
    request: AgentTurnContinueRequest,
):
    try:
        response = agent_orchestrator.continue_turn(
            turn_run_id,
            confirmed_action_run_id=request.confirmed_action_run_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    turn = agent_orchestrator.get_turn(turn_run_id)
    await realtime_hub.publish(
        turn.context.workspaceId or "__anonymous__",
        RealtimeMessage.create(
            "assistant.message",
            {
                "turn_run_id": turn_run_id,
                "status": response.status,
                "message": response.message,
                "speak": response.speak,
                "pending_action_run_ids": response.pending_action_run_ids,
            },
        ),
    )
    return response


@router.post("/turns/{turn_run_id}/cancel", response_model=AgentTurnResponse)
async def cancel_agent_turn(
    turn_run_id: str,
    request: AgentTurnCancelRequest,
):
    try:
        response = agent_orchestrator.cancel_turn(turn_run_id, request.reason)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return response
