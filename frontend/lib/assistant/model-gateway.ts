import { assistantAuthHeaders } from "./request-auth";
export type PrivacyMode = "local_only" | "prefer_local" | "allow_external";

export type ModelProviderDescriptor = {
  id: string;
  kind: "local" | "cloud" | "openai_compatible";
  model: string;
  enabled: boolean;
  priority: number;
  capabilities: {
    structured_output: boolean;
    tools: boolean;
    streaming: boolean;
    max_context_tokens?: number | null;
  };
};

export async function listAssistantModelProviders(apiBaseUrl: string) {
  const response = await fetch(
    `${apiBaseUrl.replace(/\/$/, "")}/ai/assistant/models/providers`,
    { credentials: "include", headers: assistantAuthHeaders() },
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{
    providers: ModelProviderDescriptor[];
    planner: string;
  }>;
}

export async function previewAssistantModelRoute(input: {
  apiBaseUrl: string;
  privacyMode: PrivacyMode;
  allowExternalAi: boolean;
  task?: "planner" | "explanation" | "critic" | "summarization";
  preferredProviderId?: string;
}) {
  const response = await fetch(
    `${input.apiBaseUrl.replace(/\/$/, "")}/ai/assistant/models/route`,
    {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        privacy_mode: input.privacyMode,
        allow_external_ai: input.allowExternalAi,
        require_structured_output: true,
        preferred_provider_id: input.preferredProviderId,
        task: input.task ?? "planner",
      }),
    },
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{
    provider_id: string;
    kind: string;
    model: string;
  }>;
}
