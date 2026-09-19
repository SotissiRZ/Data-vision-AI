from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .activity import ActivityMonitor, alerts_from_activity
from .contracts import tool_json_schema, validate_tool_arguments
from .action_runs import ActionLifecycleManager, ActionRunStore
from .executor import GovernedToolExecutor
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
from .model_gateway_config import build_model_gateway_from_env
from .model_gateway import RoutingPolicy, NoEligibleProvider, ModelRequest
from .planner_config import build_planner_from_env
from .settings_planner import SettingsAwarePlanner
from .tools import build_default_registry
from .workflows import list_workflows
from .host_v212 import V212HostAuthorization, bind_v212_host
from .plugin_runtime import attach_plugin_registry, safe_refresh_runtime_plugins
from app.services.tenant_access import current_access_context
from .ai_settings import (
    AssistantAISettings,
    ProviderProfileInput,
    delete_provider_profile,
    get_ai_settings,
    list_provider_profiles,
    monthly_usage,
    route_preview,
    save_ai_settings,
    save_provider_profile,
    scope_from_access,
    test_provider_connection,
)

router = APIRouter(prefix="/ai/assistant", tags=["assistant-v2.13"])
store = InMemoryAssistantContextStore()
tool_registry = build_default_registry()
activity_monitors: dict[str, ActivityMonitor] = defaultdict(ActivityMonitor)

bind_v212_host(tool_registry)
attach_plugin_registry(tool_registry)
authorization = V212HostAuthorization()
tool_executor = GovernedToolExecutor(tool_registry, authorization)
action_run_store = ActionRunStore()
action_lifecycle = ActionLifecycleManager(
    executor=tool_executor,
    store=action_run_store,
)
realtime_hub = AssistantRealtimeHub()
model_gateway = build_model_gateway_from_env()
turn_run_store = AgentTurnRunStore()
# v2.16: settings are resolved per local/workspace context at runtime.
# No server restart is required after changing Model Gateway settings.
configured_planner = SettingsAwarePlanner(tool_registry)

agent_orchestrator = build_orchestrator(
    registry=tool_registry,
    authorization=authorization,
    action_lifecycle=action_lifecycle,
    turn_store=turn_run_store,
    planner=configured_planner,
)


@router.get("/health")
def assistant_health():
    return {
        "status": "ok",
        "component": "conversational_voice_agent",
        "version": "2.26.1",
        "tool_count": len([spec for spec in tool_registry.list() if spec.metadata.get("origin") != "plugin"]),
        "plugin_tools": "tenant_scoped",
    }


@router.get("/tools", response_model=list[ToolCatalogItem])
def list_tools():
    safe_refresh_runtime_plugins()
    access = current_access_context()
    workspace_id = str(access.workspace_id) if access is not None else None
    class _Context:
        workspaceId = workspace_id
    visible_tools = tool_registry.list_for_context(_Context()) if workspace_id else tool_registry.list_for_context(None)
    return [
        ToolCatalogItem(
            name=spec.name,
            description=spec.description,
            category=spec.category,
            risk=spec.risk,
            input_schema=spec.input_schema or tool_json_schema(spec.name),
            required_permissions=list(spec.required_permissions),
            requires_dataset=spec.requires_dataset,
            requires_model=spec.requires_model,
            deterministic=spec.deterministic,
        )
        for spec in visible_tools
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
    safe_refresh_runtime_plugins()
    # Assistant gate only. Existing DataVision RBAC/RLS checks must still run.
    spec = tool_registry.get(request.action.tool)
    if spec is None:
        return ActionCheckResponse(
            decision="deny",
            reason=f"Outil non enregistré : {request.action.tool}",
        )
    if spec.metadata.get("origin") == "plugin":
        plugin_workspace = spec.metadata.get("workspace_id")
        if not request.context.workspaceId or str(plugin_workspace) != str(request.context.workspaceId):
            return ActionCheckResponse(
                decision="deny",
                reason="Tool plugin non disponible dans ce workspace.",
            )
    canonical_action = request.action.model_copy(update={"risk": spec.risk})
    return evaluate_action_policy(canonical_action, request.context)


@router.post("/plan/validate", response_model=AgentPlanValidationResponse)
def validate_plan(request: AgentPlanValidationRequest):
    safe_refresh_runtime_plugins()
    # Replace AllowAllDevelopmentAuthorization with the host RBAC/RLS bridge
    # when integrating into the real DataVision v2.12 repository.
    return validate_agent_plan(
        steps=request.steps,
        context=request.context,
        registry=tool_registry,
        authorization=authorization,
    )


@router.post("/actions", response_model=ActionRun)
async def propose_action(request: ActionRunCreateRequest):
    safe_refresh_runtime_plugins()
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
    if workspace_id:
        access = current_access_context()
        if access is None or str(access.workspace_id) != str(workspace_id):
            raise HTTPException(
                status_code=403,
                detail="Flux realtime workspace non autorisé.",
            )
        channel = workspace_id
    else:
        channel = "__anonymous__"
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
    safe_refresh_runtime_plugins()
    spec = tool_registry.get(tool_name)
    if spec is None:
        raise HTTPException(status_code=404, detail="Outil inconnu.")
    if spec.metadata.get("origin") == "plugin":
        access = current_access_context()
        if access is None or str(spec.metadata.get("workspace_id")) != str(access.workspace_id):
            raise HTTPException(status_code=404, detail="Outil inconnu.")
    try:
        normalized = validate_tool_arguments(tool_name, payload, spec.input_schema)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "tool": tool_name,
        "valid": True,
        "normalized": normalized,
        "schema": spec.input_schema or tool_json_schema(tool_name),
    }


@router.get("/workflows")
def assistant_workflows():
    return {"workflows": list_workflows()}


@router.post("/turn", response_model=AgentTurnResponse)
async def run_agent_turn(request: AgentTurnRequest):
    safe_refresh_runtime_plugins()
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
    safe_refresh_runtime_plugins()
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


@router.get("/models/providers")
def list_model_providers():
    providers = []
    for provider in model_gateway.registry.list():
        d = provider.descriptor
        providers.append(
            {
                "id": d.id,
                "kind": d.kind,
                "model": d.model,
                "enabled": d.enabled,
                "priority": d.priority,
                "capabilities": {
                    "structured_output": d.capabilities.structured_output,
                    "tools": d.capabilities.tools,
                    "streaming": d.capabilities.streaming,
                    "max_context_tokens": d.capabilities.max_context_tokens,
                },
            }
        )
    return {
        "providers": providers,
        "planner": agent_orchestrator.planner.__class__.__name__,
    }


@router.post("/models/route")
def preview_model_route(payload: dict):
    policy = RoutingPolicy(
        privacy_mode=payload.get("privacy_mode", "local_only"),
        allow_external_ai=bool(payload.get("allow_external_ai", False)),
        require_structured_output=bool(
            payload.get("require_structured_output", True)
        ),
        preferred_provider_id=payload.get("preferred_provider_id"),
    )

    req = ModelRequest(
        task=payload.get("task", "planner"),
        system="",
        user="",
        response_schema=(
            {"type": "object"}
            if policy.require_structured_output
            else None
        ),
    )

    try:
        provider = model_gateway.select_provider(
            request=req,
            policy=policy,
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "provider_id": provider.descriptor.id,
        "kind": provider.descriptor.kind,
        "model": provider.descriptor.model,
    }


def _assistant_settings_scope(require_manage: bool = True):
    try:
        return scope_from_access(require_manage=require_manage)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/settings")
def get_assistant_ai_settings():
    scope_type, scope_id, _actor = _assistant_settings_scope(True)
    settings = get_ai_settings(scope_type, scope_id)
    providers = list_provider_profiles(scope_type, scope_id)
    return {
        "scope": {"type": scope_type, "id": scope_id},
        "settings": settings.model_dump(mode="json"),
        "providers": [p.model_dump(mode="json") for p in providers],
        "usage": monthly_usage(scope_type, scope_id),
        "routes": {
            task: route_preview(scope_type, scope_id, task=task)
            for task in ["planner", "explanation", "critic", "summarization"]
        },
        "runtime": {
            "planner": agent_orchestrator.planner.__class__.__name__,
            "settings_live_reload": True,
        },
    }


@router.put("/settings")
def update_assistant_ai_settings(payload: AssistantAISettings):
    scope_type, scope_id, actor_id = _assistant_settings_scope(True)
    provider_ids = {
        p.id for p in list_provider_profiles(scope_type, scope_id)
    }

    unknown_routes = [
        provider_id
        for provider_id in payload.task_routes.values()
        if provider_id and provider_id not in provider_ids
    ]
    unknown_fallbacks = [
        provider_id
        for provider_id in payload.fallback_order
        if provider_id not in provider_ids
    ]
    if unknown_routes or unknown_fallbacks:
        raise HTTPException(
            status_code=422,
            detail="Les routes/fallbacks doivent référencer des providers du contexte actif.",
        )

    saved = save_ai_settings(
        scope_type,
        scope_id,
        payload,
        actor_id=actor_id,
    )
    return {
        "scope": {"type": scope_type, "id": scope_id},
        "settings": saved.model_dump(mode="json"),
        "routes": {
            task: route_preview(scope_type, scope_id, task=task)
            for task in ["planner", "explanation", "critic", "summarization"]
        },
    }


@router.post("/settings/providers")
def create_assistant_model_provider(payload: ProviderProfileInput):
    scope_type, scope_id, actor_id = _assistant_settings_scope(True)
    try:
        profile = save_provider_profile(
            scope_type,
            scope_id,
            payload,
            actor_id=actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return profile.model_dump(mode="json")


@router.put("/settings/providers/{provider_id}")
def update_assistant_model_provider(
    provider_id: str,
    payload: ProviderProfileInput,
):
    scope_type, scope_id, actor_id = _assistant_settings_scope(True)
    try:
        profile = save_provider_profile(
            scope_type,
            scope_id,
            payload,
            actor_id=actor_id,
            provider_id=provider_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return profile.model_dump(mode="json")


@router.delete("/settings/providers/{provider_id}")
def remove_assistant_model_provider(provider_id: str):
    scope_type, scope_id, actor_id = _assistant_settings_scope(True)
    try:
        delete_provider_profile(
            scope_type,
            scope_id,
            provider_id,
            actor_id=actor_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    settings = get_ai_settings(scope_type, scope_id)
    settings.task_routes = {
        task: (None if value == provider_id else value)
        for task, value in settings.task_routes.items()
    }
    settings.fallback_order = [
        value for value in settings.fallback_order
        if value != provider_id
    ]
    save_ai_settings(
        scope_type,
        scope_id,
        settings,
        actor_id=actor_id,
    )
    return {"ok": True, "provider_id": provider_id}


@router.post("/settings/providers/{provider_id}/test")
def test_assistant_model_provider(provider_id: str):
    scope_type, scope_id, actor_id = _assistant_settings_scope(True)
    try:
        return test_provider_connection(
            scope_type,
            scope_id,
            provider_id,
            actor_id=actor_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/settings/route/{task}")
def preview_assistant_task_route(task: str):
    if task not in {"planner", "explanation", "critic", "summarization"}:
        raise HTTPException(status_code=404, detail="Tâche IA inconnue.")
    scope_type, scope_id, _actor_id = _assistant_settings_scope(True)
    return route_preview(scope_type, scope_id, task=task)
