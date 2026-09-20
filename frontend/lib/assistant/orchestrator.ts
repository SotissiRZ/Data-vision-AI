import { assistantAuthHeaders } from "./request-auth";
import type { AssistantContextSnapshot } from "./event-bus";

export type AgentIntent = {
  name:
    | "analyze_dataset"
    | "data_quality"
    | "compare_groups"
    | "visualize"
    | "predict_target"
    | "explain_model"
    | "model_registry"
    | "monitor_model"
    | "retraining_check"
    | "fairness_analysis"
    | "model_risk"
    | "root_cause_analysis"
    | "optimize_scenarios"
    | "geospatial_analysis"
    | "report"
    | "file_analysis"
    | "show_results"
    | "dataset_assessment"
    | "dataset_context"
    | "artifact_context"
    | "explain_previous"
    | "capabilities"
    | "conversation"
    | "unknown";
  confidence: number;
  entities: Record<string, unknown>;
  rationale?: string;
};

export type AgentTurnStep = {
  id: string;
  tool: string;
  label: string;
  args: Record<string, unknown>;
  reason?: string;
  risk?: "read" | "reversible" | "destructive" | "external";
  status:
    | "planned"
    | "ready"
    | "waiting_confirmation"
    | "running"
    | "succeeded"
    | "failed"
    | "skipped";
  action_run_id?: string;
  result?: unknown;
  error?: string;
};


export type AgentTurnAttachment = {
  id: string;
  name: string;
  mime_type?: string;
  size?: number;
  download_path: string;
  kind?: string;
  step_id?: string;
};

export type AgentTurnResponse = {
  session_id: string;
  intent: AgentIntent;
  message: string;
  speak: boolean;
  status:
    | "completed"
    | "waiting_confirmation"
    | "partial"
    | "failed"
    | "needs_clarification";
  steps: AgentTurnStep[];
  pending_action_run_ids: string[];
  attachments?: AgentTurnAttachment[];
  critic?: {
    status: "pass" | "warning" | "fail";
    findings: Array<{
      severity: "info" | "suggestion" | "warning" | "critical";
      code: string;
      message: string;
      step_id?: string;
    }>;
  };
  metadata: Record<string, unknown>;
};

export async function runAssistantTurn(input: {
  apiBaseUrl: string;
  sessionId: string;
  message: string;
  context: AssistantContextSnapshot;
  attachmentIds?: string[];
  autoExecuteSafeSteps?: boolean;
}): Promise<AgentTurnResponse> {
  const response = await fetch(
    `${input.apiBaseUrl.replace(/\/$/, "")}/ai/assistant/turn`,
    {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        session_id: input.sessionId,
        message: input.message,
        context: input.context,
        attachment_ids: input.attachmentIds ?? [],
        auto_execute_safe_steps: input.autoExecuteSafeSteps ?? true,
      }),
    },
  );

  if (!response.ok) throw new Error(await response.text());
  return response.json();
}


export async function continueAssistantTurn(input: {
  apiBaseUrl: string;
  turnRunId: string;
  confirmedActionRunId?: string;
}): Promise<AgentTurnResponse> {
  const response = await fetch(
    `${input.apiBaseUrl.replace(/\/$/, "")}/ai/assistant/turns/${encodeURIComponent(input.turnRunId)}/continue`,
    {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        confirmed_action_run_id: input.confirmedActionRunId,
      }),
    },
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function cancelAssistantTurn(input: {
  apiBaseUrl: string;
  turnRunId: string;
  reason?: string;
}): Promise<AgentTurnResponse> {
  const response = await fetch(
    `${input.apiBaseUrl.replace(/\/$/, "")}/ai/assistant/turns/${encodeURIComponent(input.turnRunId)}/cancel`,
    {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ reason: input.reason }),
    },
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
