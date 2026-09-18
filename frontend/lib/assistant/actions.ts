import type { AssistantActionProposal } from "./adapter";
import type { AssistantContextSnapshot } from "./event-bus";

export type ActionRunStatus =
  | "proposed"
  | "waiting_confirmation"
  | "ready"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "rolled_back";

export type ActionRun = {
  id: string;
  session_id?: string;
  action: AssistantActionProposal;
  context: AssistantContextSnapshot;
  status: ActionRunStatus;
  reason?: string;
  result?: unknown;
  error?: string;
  reversible: boolean;
  rollback_token?: string;
};

async function jsonOrThrow(response: Response) {
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function proposeAssistantAction(input: {
  apiBaseUrl: string;
  action: AssistantActionProposal;
  context: AssistantContextSnapshot;
  sessionId?: string;
}): Promise<ActionRun> {
  const base = input.apiBaseUrl.replace(/\/$/, "");
  const response = await fetch(`${base}/ai/assistant/actions`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: input.action,
      context: input.context,
      session_id: input.sessionId,
    }),
  });
  return jsonOrThrow(response);
}

export async function confirmAssistantAction(input: {
  apiBaseUrl: string;
  runId: string;
  confirmed: boolean;
}): Promise<ActionRun> {
  const base = input.apiBaseUrl.replace(/\/$/, "");
  const response = await fetch(
    `${base}/ai/assistant/actions/${encodeURIComponent(input.runId)}/confirm`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: input.confirmed }),
    },
  );
  return jsonOrThrow(response);
}

export async function executeAssistantAction(input: {
  apiBaseUrl: string;
  runId: string;
}): Promise<ActionRun> {
  const base = input.apiBaseUrl.replace(/\/$/, "");
  const response = await fetch(
    `${base}/ai/assistant/actions/${encodeURIComponent(input.runId)}/execute`,
    {
      method: "POST",
      credentials: "include",
    },
  );
  return jsonOrThrow(response);
}
