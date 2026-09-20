import type {
  AssistantContextSnapshot,
  AssistantEvent,
  AssistantSeverity,
} from "./event-bus";

export type AssistantAttachment = {
  id: string;
  name: string;
  mimeType?: string;
  size?: number;
  downloadPath?: string;
  kind?: "uploaded" | "generated" | string;
  stepId?: string;
};

export type AssistantActionProposal = {
  id: string;
  tool: string;
  label: string;
  description?: string;
  risk?: "read" | "reversible" | "destructive" | "external";
  args?: Record<string, unknown>;
  continuation?: {
    turnRunId: string;
    actionRunId: string;
  };
};

export type AssistantChatResponse = {
  message: string;
  speak?: boolean;
  actions?: AssistantActionProposal[];
  attachments?: AssistantAttachment[];
  metadata?: Record<string, unknown>;
};


export type ProjectMemoryEntry = {
  id: string;
  artifact_id?: string;
  dataset_id?: string;
  kind?: string;
  title?: string;
  summary?: string;
  pinned?: boolean;
  created_at?: string;
  updated_at?: string;
  last_used_at?: string;
  payload?: Record<string, unknown>;
  search_score?: number;
  match_reasons?: string[];
  search_mode?: "semantic_local" | "recency";
};

export type ProjectMemoryPolicy = {
  enabled: boolean;
  auto_recall: boolean;
  retention_days: number;
  max_entries: number;
  allowed_kinds: string[];
};

export type ProjectMemoryResponse = {
  scope: string;
  policy: ProjectMemoryPolicy;
  entries: ProjectMemoryEntry[];
  count: number;
  can_manage?: boolean;
  query?: string | null;
  search_mode?: "semantic_local" | "recency";
};

export type ProactiveAlert = {
  id: string;
  title: string;
  message: string;
  severity: AssistantSeverity;
  speak: boolean;
  actionLabel?: string;
  action?: AssistantActionProposal;
  fingerprint?: string;
  sourceEventId?: string;
  cooldownSeconds?: number;
};

export interface AssistantAdapter {
  sendMessage(input: {
    message: string;
    context: AssistantContextSnapshot;
    attachmentIds?: string[];
  }): Promise<AssistantChatResponse>;

  observe(input: {
    event: AssistantEvent;
    context: AssistantContextSnapshot;
  }): Promise<ProactiveAlert[]>;

  uploadFiles?(files: File[]): Promise<AssistantAttachment[]>;

  executeAction?(
    action: AssistantActionProposal,
    context: AssistantContextSnapshot,
  ): Promise<AssistantChatResponse>;

  rejectAction?(
    action: AssistantActionProposal,
    context: AssistantContextSnapshot,
  ): Promise<AssistantChatResponse>;

  getProjectMemory?(query?: string): Promise<ProjectMemoryResponse>;

  updateProjectMemoryPolicy?(
    updates: Partial<ProjectMemoryPolicy>,
  ): Promise<{ scope: string; policy: ProjectMemoryPolicy }>;

  pinProjectMemory?(entryId: string, pinned: boolean): Promise<ProjectMemoryEntry>;

  duplicateProjectMemory?(entryId: string): Promise<ProjectMemoryEntry>;

  forgetProjectMemory?(entryId: string): Promise<void>;

  clearProjectMemory?(): Promise<{ deleted: number; pinned_preserved: boolean }>;
}

function authHeaders(): Record<string, string> {
  // L'application hôte peut remplacer cette stratégie.
  // Aucun token n'est stocké ici.
  return {};
}

async function readJsonOrThrow(response: Response) {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `HTTP ${response.status}`);
  }
  return response.json();
}

export function normalizeChatResponse(raw: any): AssistantChatResponse {
  if (typeof raw === "string") return { message: raw };

  return {
    message:
      raw?.message ??
      raw?.answer ??
      raw?.response ??
      "Réponse reçue, mais le contrat API doit être adapté.",
    speak: raw?.speak ?? true,
    actions: raw?.actions ?? [],
    attachments: raw?.attachments ?? [],
    metadata: raw?.metadata ?? {},
  };
}

export function createRestAssistantAdapter(options: {
  apiBaseUrl: string;
  chatPath: string;
  observePath: string;
  uploadPath?: string;
  executeActionPath?: string;
}): AssistantAdapter {
  const base = options.apiBaseUrl.replace(/\/$/, "");

  return {
    async sendMessage(input) {
      const response = await fetch(`${base}${options.chatPath}`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify(input),
      });
      return normalizeChatResponse(await readJsonOrThrow(response));
    },

    async observe(input) {
      const response = await fetch(`${base}${options.observePath}`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify(input),
      });
      const raw = await readJsonOrThrow(response);
      return raw?.alerts ?? [];
    },

    async uploadFiles(files) {
      if (!options.uploadPath) {
        throw new Error(
          "L'endpoint d'upload DataVision n'est pas encore raccordé à l'assistant.",
        );
      }

      const uploaded: AssistantAttachment[] = [];

      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch(`${base}${options.uploadPath}`, {
          method: "POST",
          credentials: "include",
          headers: authHeaders(),
          body: form,
        });
        const raw = await readJsonOrThrow(response);
        uploaded.push({
          id: raw?.id ?? raw?.file_id ?? raw?.dataset_id,
          name: raw?.name ?? file.name,
          mimeType: raw?.mime_type ?? file.type,
          size: raw?.size ?? file.size,
        });
      }

      return uploaded;
    },

    async executeAction(action, context) {
      if (!options.executeActionPath) {
        throw new Error(
          "L'exécution d'actions doit être raccordée à l'orchestrateur gouverné de DataVision.",
        );
      }

      const response = await fetch(`${base}${options.executeActionPath}`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ action, context }),
      });

      return normalizeChatResponse(await readJsonOrThrow(response));
    },
  };
}
