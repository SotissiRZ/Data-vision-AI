import { assistantAuthHeaders } from "./request-auth";
import type { AssistantContextSnapshot } from "./event-bus";

export type AgentPlanStep = {
  id: string;
  tool: string;
  label: string;
  reason?: string;
  args?: Record<string, unknown>;
};

export type AgentPlanStepValidation = {
  id: string;
  tool: string;
  status: "ready" | "confirmation_required" | "deny";
  reason: string;
  risk?: "read" | "reversible" | "destructive" | "external";
};

export type AgentPlanValidation = {
  valid: boolean;
  executable_without_confirmation: boolean;
  steps: AgentPlanStepValidation[];
};

export async function validateAssistantPlan(input: {
  apiBaseUrl: string;
  steps: AgentPlanStep[];
  context: AssistantContextSnapshot;
}): Promise<AgentPlanValidation> {
  const response = await fetch(
    `${input.apiBaseUrl.replace(/\/$/, "")}/ai/assistant/plan/validate`,
    {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        steps: input.steps,
        context: input.context,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}
