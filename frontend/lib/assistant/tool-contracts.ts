import { assistantAuthHeaders } from "./request-auth";
export type JsonSchema = {
  title?: string;
  type?: string;
  properties?: Record<string, JsonSchema & {
    description?: string;
    enum?: unknown[];
    default?: unknown;
    minimum?: number;
    maximum?: number;
    items?: JsonSchema;
  }>;
  required?: string[];
  enum?: unknown[];
  default?: unknown;
  items?: JsonSchema;
};

export type AssistantToolCatalogItem = {
  name: string;
  description: string;
  category: string;
  risk: "read" | "reversible" | "destructive" | "external";
  input_schema?: JsonSchema | null;
  required_permissions: string[];
  requires_dataset: boolean;
  requires_model: boolean;
  deterministic: boolean;
};

export async function getAssistantToolCatalog(apiBaseUrl: string) {
  const response = await fetch(
    `${apiBaseUrl.replace(/\/$/, "")}/ai/assistant/tools`,
    { credentials: "include", headers: assistantAuthHeaders() },
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<AssistantToolCatalogItem[]>;
}

export async function validateAssistantToolArguments(input: {
  apiBaseUrl: string;
  tool: string;
  args: Record<string, unknown>;
}) {
  const response = await fetch(
    `${input.apiBaseUrl.replace(/\/$/, "")}/ai/assistant/tools/${encodeURIComponent(input.tool)}/validate`,
    {
      method: "POST",
      credentials: "include",
      headers: assistantAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(input.args),
    },
  );
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
