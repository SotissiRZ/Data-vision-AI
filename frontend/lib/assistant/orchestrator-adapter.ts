import type {
  AssistantActionProposal,
  AssistantAdapter,
  AssistantChatResponse,
  AssistantAttachment,
} from "./adapter";
import type { AssistantContextSnapshot } from "./event-bus";
import { assistantAuthHeaders } from "./request-auth";
import {
  continueAssistantTurn,
  runAssistantTurn,
  type AgentTurnResponse,
} from "./orchestrator";
import {
  confirmAssistantAction,
  type ActionRun,
} from "./actions";

function sessionId(): string {
  if (typeof window === "undefined") return "server-session";
  const key = "datavision_assistant_session_id";
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const value = crypto.randomUUID();
  window.sessionStorage.setItem(key, value);
  return value;
}

function riskFromStep(step: AgentTurnResponse["steps"][number]) {
  // The backend remains authoritative. This value only mirrors the validated
  // Tool Registry risk so the UI can explain what the user is confirming.
  return step.risk ?? (step.status === "waiting_confirmation" ? "reversible" : "read");
}

function turnToChatResponse(turn: AgentTurnResponse): AssistantChatResponse {
  const turnRunId =
    typeof turn.metadata?.turn_run_id === "string"
      ? turn.metadata.turn_run_id
      : undefined;

  const actions: AssistantActionProposal[] = [];

  if (turnRunId) {
    for (const step of turn.steps) {
      if (step.status !== "waiting_confirmation" || !step.action_run_id) continue;
      actions.push({
        id: step.action_run_id,
        tool: step.tool,
        label: `Confirmer : ${step.label}`,
        description: step.reason,
        risk: riskFromStep(step),
        args: step.args,
        continuation: {
          turnRunId,
          actionRunId: step.action_run_id,
        },
      });
    }
  }

  return {
    message: turn.message,
    speak: turn.speak,
    actions,
    metadata: {
      ...turn.metadata,
      intent: turn.intent,
      critic: turn.critic,
      steps: turn.steps,
      status: turn.status,
    },
  };
}

async function jsonOrThrow(response: Response) {
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export function createOrchestratorAssistantAdapter(options: {
  apiBaseUrl: string;
  observePath?: string;
  uploadPath?: string;
}): AssistantAdapter {
  const base = options.apiBaseUrl.replace(/\/$/, "");
  const observePath = options.observePath ?? "/ai/assistant/observe";

  return {
    async sendMessage(input) {
      const turn = await runAssistantTurn({
        apiBaseUrl: base,
        sessionId: sessionId(),
        message: input.message,
        context: input.context,
        attachmentIds: input.attachmentIds ?? [],
        autoExecuteSafeSteps: true,
      });
      return turnToChatResponse(turn);
    },

    async observe(input) {
      const response = await fetch(`${base}${observePath}`, {
        method: "POST",
        credentials: "include",
        headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(input),
      });
      const raw = await jsonOrThrow(response);
      return raw?.alerts ?? [];
    },

    async uploadFiles(files) {
      if (!options.uploadPath) {
        throw new Error(
          "L'endpoint d'upload réel de DataVision doit être configuré.",
        );
      }

      const uploaded: AssistantAttachment[] = [];
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);

        const response = await fetch(`${base}${options.uploadPath}`, {
          method: "POST",
          credentials: "include",
          headers: assistantAuthHeaders(),
          body: form,
        });
        const raw = await jsonOrThrow(response);
        uploaded.push({
          id:
            raw?.id ??
            raw?.file_id ??
            raw?.dataset_id ??
            raw?.dataset?.id,
          name: raw?.name ?? raw?.dataset?.name ?? file.name,
          mimeType: raw?.mime_type ?? raw?.dataset?.format ?? file.type,
          size: raw?.size ?? file.size,
        });
      }
      return uploaded;
    },

    async executeAction(action, context) {
      const continuation = action.continuation;
      if (!continuation) {
        throw new Error(
          "Cette action ne contient pas de contexte de reprise orchestrateur.",
        );
      }

      const confirmed: ActionRun = await confirmAssistantAction({
        apiBaseUrl: base,
        runId: continuation.actionRunId,
        confirmed: true,
      });

      if (confirmed.status !== "ready") {
        throw new Error(
          `L'action n'est pas prête après confirmation (${confirmed.status}).`,
        );
      }

      const resumed = await continueAssistantTurn({
        apiBaseUrl: base,
        turnRunId: continuation.turnRunId,
        confirmedActionRunId: continuation.actionRunId,
      });

      return turnToChatResponse(resumed);
    },

    async rejectAction(action, context) {
      const continuation = action.continuation;
      if (!continuation) {
        throw new Error(
          "Cette action ne contient pas de contexte de reprise orchestrateur.",
        );
      }

      const rejected: ActionRun = await confirmAssistantAction({
        apiBaseUrl: base,
        runId: continuation.actionRunId,
        confirmed: false,
      });

      if (rejected.status !== "cancelled") {
        throw new Error(
          `Le refus n'a pas été enregistré (${rejected.status}).`,
        );
      }

      const resumed = await continueAssistantTurn({
        apiBaseUrl: base,
        turnRunId: continuation.turnRunId,
        confirmedActionRunId: continuation.actionRunId,
      });

      return turnToChatResponse(resumed);
    },

    async getProjectMemory(query) {
      const suffix = query?.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
      const response = await fetch(`${base}/ai/assistant/memory${suffix}`, {
        credentials: "include",
        headers: assistantAuthHeaders(),
      });
      return jsonOrThrow(response);
    },

    async updateProjectMemoryPolicy(updates) {
      const response = await fetch(`${base}/ai/assistant/memory/policy`, {
        method: "PUT",
        credentials: "include",
        headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(updates),
      });
      return jsonOrThrow(response);
    },

    async pinProjectMemory(entryId, pinned) {
      const response = await fetch(`${base}/ai/assistant/memory/${encodeURIComponent(entryId)}/pin`, {
        method: "POST",
        credentials: "include",
        headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ pinned }),
      });
      return jsonOrThrow(response);
    },

    async duplicateProjectMemory(entryId) {
      const response = await fetch(`${base}/ai/assistant/memory/${encodeURIComponent(entryId)}/duplicate`, {
        method: "POST",
        credentials: "include",
        headers: assistantAuthHeaders(),
      });
      return jsonOrThrow(response);
    },

    async forgetProjectMemory(entryId) {
      const response = await fetch(`${base}/ai/assistant/memory/${encodeURIComponent(entryId)}`, {
        method: "DELETE",
        credentials: "include",
        headers: assistantAuthHeaders(),
      });
      await jsonOrThrow(response);
    },

    async clearProjectMemory() {
      const response = await fetch(`${base}/ai/assistant/memory`, {
        method: "DELETE",
        credentials: "include",
        headers: assistantAuthHeaders(),
      });
      return jsonOrThrow(response);
    },
  };
}
