import { assistantAuthHeaders } from "./request-auth";

const API =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8005/api/v1";

export type AssistantPrivacyMode =
  | "local_only"
  | "prefer_local"
  | "allow_external";

export type AssistantTask =
  | "planner"
  | "explanation"
  | "critic"
  | "summarization";

export type AssistantProvider = {
  id: string;
  scope_type: "local" | "workspace";
  scope_id: string;
  name: string;
  provider_type: "ollama" | "openai_compatible";
  location: "local" | "external";
  base_url: string;
  model: string;
  enabled: boolean;
  priority: number;
  structured_output: boolean;
  max_context_tokens?: number | null;
  secret_id?: string | null;
  api_key_env?: string | null;
  input_cost_per_million?: number | null;
  output_cost_per_million?: number | null;
  created_at: string;
  updated_at: string;
};

export type AssistantAISettings = {
  planner_mode: "deterministic" | "gateway";
  privacy_mode: AssistantPrivacyMode;
  allow_external_ai: boolean;
  allow_provider_fallback: boolean;
  fallback_to_deterministic: boolean;
  task_routes: Record<AssistantTask, string | null>;
  fallback_order: string[];
  monthly_budget_usd: number;
  deny_external_when_cost_unknown: boolean;
  external_data_policy: {
    include_column_names: boolean;
    include_sample_values: false;
    include_row_data: false;
    max_recent_events: number;
  };
};

export type AssistantSettingsSnapshot = {
  scope: { type: "local" | "workspace"; id: string };
  settings: AssistantAISettings;
  providers: AssistantProvider[];
  usage: {
    month_start: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
    unknown_cost_calls: number;
  };
  routes: Record<
    AssistantTask,
    {
      task: AssistantTask;
      planner_mode: string;
      privacy_mode: string;
      allow_external_ai: boolean;
      candidates: Array<{
        id: string;
        name: string;
        kind: string;
        model: string;
        location?: string | null;
        priority: number;
      }>;
      selected_provider_id?: string | null;
    }
  >;
  runtime: {
    planner: string;
    settings_live_reload: boolean;
  };
};

export type AssistantProviderInput = {
  name: string;
  provider_type: "ollama" | "openai_compatible";
  location: "local" | "external";
  base_url: string;
  model: string;
  enabled: boolean;
  priority: number;
  structured_output: boolean;
  max_context_tokens?: number | null;
  secret_id?: string | null;
  api_key_env?: string | null;
  input_cost_per_million?: number | null;
  output_cost_per_million?: number | null;
};

async function parse<T>(
  response: Response,
  fallback: string,
): Promise<T> {
  if (!response.ok) {
    let message = fallback;
    try {
      const payload = await response.json();
      message = payload?.detail ?? message;
    } catch {
      const raw = await response.text();
      if (raw) message = raw;
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getAssistantSettings() {
  return parse<AssistantSettingsSnapshot>(
    await fetch(`${API}/ai/assistant/settings`, {
      credentials: "include",
      headers: assistantAuthHeaders(),
    }),
    "Configuration IA indisponible.",
  );
}

export async function saveAssistantSettings(
  settings: AssistantAISettings,
) {
  return parse<{
    scope: AssistantSettingsSnapshot["scope"];
    settings: AssistantAISettings;
    routes: AssistantSettingsSnapshot["routes"];
  }>(
    await fetch(`${API}/ai/assistant/settings`, {
      method: "PUT",
      credentials: "include",
      headers: assistantAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(settings),
    }),
    "Enregistrement des réglages IA impossible.",
  );
}

export async function createAssistantProvider(
  provider: AssistantProviderInput,
) {
  return parse<AssistantProvider>(
    await fetch(`${API}/ai/assistant/settings/providers`, {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(provider),
    }),
    "Création du provider impossible.",
  );
}

export async function updateAssistantProvider(
  providerId: string,
  provider: AssistantProviderInput,
) {
  return parse<AssistantProvider>(
    await fetch(
      `${API}/ai/assistant/settings/providers/${encodeURIComponent(providerId)}`,
      {
        method: "PUT",
        credentials: "include",
        headers: assistantAuthHeaders({
          "Content-Type": "application/json",
        }),
        body: JSON.stringify(provider),
      },
    ),
    "Mise à jour du provider impossible.",
  );
}

export async function deleteAssistantProvider(
  providerId: string,
) {
  return parse<{ ok: boolean; provider_id: string }>(
    await fetch(
      `${API}/ai/assistant/settings/providers/${encodeURIComponent(providerId)}`,
      {
        method: "DELETE",
        credentials: "include",
        headers: assistantAuthHeaders(),
      },
    ),
    "Suppression du provider impossible.",
  );
}

export async function testAssistantProvider(
  providerId: string,
) {
  return parse<{
    ok: boolean;
    provider_id: string;
    model: string;
    latency_ms: number;
    response: string;
    note: string;
  }>(
    await fetch(
      `${API}/ai/assistant/settings/providers/${encodeURIComponent(providerId)}/test`,
      {
        method: "POST",
        credentials: "include",
        headers: assistantAuthHeaders(),
      },
    ),
    "Test de connexion du provider impossible.",
  );
}
