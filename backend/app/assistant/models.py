from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Severity = Literal["info", "suggestion", "warning", "critical"]
ActionRisk = Literal["read", "reversible", "destructive", "external"]


class SelectedEntity(BaseModel):
    type: str
    id: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssistantEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    severity: Severity = "info"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class AssistantContext(BaseModel):
    workspaceId: str | None = None
    organizationId: str | None = None
    route: str | None = None
    screen: str | None = None
    activeDatasetId: str | None = None
    activeDatasetVersionId: str | None = None
    activeModelId: str | None = None
    activeChartId: str | None = None
    activeReportId: str | None = None
    selectedEntity: SelectedEntity | None = None
    recentEvents: list[AssistantEvent] = Field(default_factory=list)
    uiState: dict[str, Any] = Field(default_factory=dict)


class ObserveRequest(BaseModel):
    event: AssistantEvent
    context: AssistantContext


class AssistantAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str
    label: str
    description: str | None = None
    risk: ActionRisk = "read"
    args: dict[str, Any] = Field(default_factory=dict)


class ProactiveAlert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    message: str
    severity: Severity
    speak: bool = False
    actionLabel: str | None = None
    action: AssistantAction | None = None


class ObserveResponse(BaseModel):
    alerts: list[ProactiveAlert] = Field(default_factory=list)


class ActionCheckRequest(BaseModel):
    action: AssistantAction
    context: AssistantContext


class ActionCheckResponse(BaseModel):
    decision: Literal["allow", "confirmation_required", "deny"]
    reason: str


class ActivityObservationResponse(BaseModel):
    alerts: list[ProactiveAlert] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)


class ToolCatalogItem(BaseModel):
    name: str
    description: str
    category: str
    risk: ActionRisk
    input_schema: dict[str, Any] | None = None
    required_permissions: list[str] = Field(default_factory=list)
    requires_dataset: bool = False
    requires_model: bool = False
    deterministic: bool = True


class AgentPlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str
    label: str
    reason: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)


class AgentPlanValidationRequest(BaseModel):
    context: AssistantContext
    steps: list[AgentPlanStep] = Field(default_factory=list)


class AgentPlanStepValidation(BaseModel):
    id: str
    tool: str
    status: Literal["ready", "confirmation_required", "deny"]
    reason: str
    risk: ActionRisk | None = None


class AgentPlanValidationResponse(BaseModel):
    valid: bool
    executable_without_confirmation: bool
    steps: list[AgentPlanStepValidation] = Field(default_factory=list)


ActionRunStatus = Literal[
    "proposed",
    "waiting_confirmation",
    "ready",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "rolled_back",
]


class ActionRunCreateRequest(BaseModel):
    action: AssistantAction
    context: AssistantContext
    session_id: str | None = None


class ActionRunConfirmRequest(BaseModel):
    confirmed: bool = True


class ActionRunRollbackRequest(BaseModel):
    reason: str | None = None


class ActionRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    action: AssistantAction
    context: AssistantContext
    status: ActionRunStatus = "proposed"
    reason: str | None = None
    result: Any = None
    error: str | None = None
    reversible: bool = False
    rollback_token: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


AgentIntentName = Literal[
    "analyze_dataset",
    "data_quality",
    "compare_groups",
    "visualize",
    "predict_target",
    "explain_model",
    "model_registry",
    "monitor_model",
    "retraining_check",
    "fairness_analysis",
    "model_risk",
    "root_cause_analysis",
    "optimize_scenarios",
    "geospatial_analysis",
    "report",
    "file_analysis",
    "show_results",
    "dataset_assessment",
    "dataset_context",
    "artifact_context",
    "replay_artifact",
    "project_memory",
    "explain_previous",
    "capabilities",
    "conversation",
    "unknown",
]


class AgentIntent(BaseModel):
    name: AgentIntentName
    confidence: float = Field(ge=0, le=1)
    entities: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None


class AgentTurnRequest(BaseModel):
    session_id: str
    message: str
    context: AssistantContext
    attachment_ids: list[str] = Field(default_factory=list)
    auto_execute_safe_steps: bool = True


class AgentTurnStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str
    label: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    risk: ActionRisk | None = None
    status: Literal[
        "planned",
        "ready",
        "waiting_confirmation",
        "running",
        "succeeded",
        "failed",
        "skipped",
    ] = "planned"
    action_run_id: str | None = None
    result: Any = None
    error: str | None = None


class CriticFinding(BaseModel):
    severity: Severity
    code: str
    message: str
    step_id: str | None = None


class CriticReport(BaseModel):
    status: Literal["pass", "warning", "fail"]
    findings: list[CriticFinding] = Field(default_factory=list)


class AgentTurnResponse(BaseModel):
    session_id: str
    intent: AgentIntent
    message: str
    speak: bool = True
    status: Literal[
        "completed",
        "waiting_confirmation",
        "partial",
        "failed",
        "needs_clarification",
    ]
    steps: list[AgentTurnStep] = Field(default_factory=list)
    critic: CriticReport | None = None
    pending_action_run_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


AgentTurnRunStatus = Literal[
    "created",
    "running",
    "waiting_confirmation",
    "completed",
    "partial",
    "failed",
    "cancelled",
]


class AgentTurnRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    request_message: str
    context: AssistantContext
    attachment_ids: list[str] = Field(default_factory=list)
    intent: AgentIntent
    steps: list[AgentTurnStep] = Field(default_factory=list)
    current_step_index: int = 0
    status: AgentTurnRunStatus = "created"
    critic: CriticReport | None = None
    final_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentTurnContinueRequest(BaseModel):
    confirmed_action_run_id: str | None = None


class AgentTurnCancelRequest(BaseModel):
    reason: str | None = None
