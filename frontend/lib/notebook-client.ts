import { assistantAuthHeaders } from "./assistant/request-auth";

const API =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8005/api/v1";

export type NotebookLanguage = "markdown" | "python" | "sql" | "r";

export type NotebookRun = {
  id: string;
  notebook_id: string;
  cell_id: string;
  dataset_id?: string | null;
  dataset_version?: string | null;
  language: NotebookLanguage;
  status: "succeeded" | "failed";
  engine?: string | null;
  stdout: string;
  stderr: string;
  result?: {
    type?: string;
    value?: unknown;
    columns?: string[];
    rows?: Array<Record<string, unknown>>;
    shape?: number[];
    truncated?: boolean;
    query?: string;
  } | null;
  artifacts: Array<{
    name: string;
    size: number;
    extension: string;
    download_path: string;
  }>;
  provenance: Record<string, unknown>;
  error_type?: string | null;
  elapsed_ms?: number | null;
  started_at: string;
  finished_at: string;
};

export type NotebookCell = {
  id: string;
  position: number;
  language: NotebookLanguage;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_run?: NotebookRun | null;
};

export type DatasetVersionRef = {
  id: string;
  version: number;
  name?: string | null;
  parent_id?: string | null;
  created_at?: string | null;
};

export type NotebookKernel = {
  language: "python" | "r";
  session_id: string;
  status?: string;
  state_status?: "new" | "ready" | "reset" | "lost" | string;
  execution_count: number;
  generation?: string | null;
  persistent: boolean;
  variables?: string[];
};

export type WorkspaceEnvironment = {
  scope_type: "local" | "workspace" | string;
  scope_id: string;
  python_requirements: string[];
  r_requirements: string[];
  python_lock: Record<string, string>;
  r_lock: Record<string, string>;
  manifest: Record<string, unknown>;
  fingerprint_sha256: string;
  inventory_sha256?: string | null;
  status: string;
  reproducible: boolean;
  policy: Record<string, unknown>;
  missing_python?: string[];
  missing_r?: string[];
  lock_drift?: Array<{ language: string; package: string; expected?: string | null; actual?: string | null }>;
  verified?: boolean;
};

export type NotebookEnvironment = {
  notebook_id: string;
  python_requirements: string[];
  r_requirements: string[];
  effective_python_requirements?: string[];
  effective_r_requirements?: string[];
  python_lock: Record<string, string>;
  r_lock: Record<string, string>;
  fingerprint_sha256?: string;
  reproducible?: boolean;
  workspace_environment?: Pick<WorkspaceEnvironment, "scope_type" | "scope_id" | "status" | "fingerprint_sha256" | "python_requirements" | "r_requirements">;
  manifest?: Record<string, unknown>;
  policy: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
  status?: string;
  missing_python?: string[];
  missing_r?: string[];
  inventory_policy?: string;
  dynamic_install?: boolean;
};

export type NotebookDocument = {
  id: string;
  dataset_id?: string | null;
  dataset_version?: string | null;
  dataset_binding?: {
    id: string;
    root_id: string;
    parent_id?: string | null;
    version: number;
    name?: string | null;
    created_at?: string | null;
    operation?: Record<string, unknown> | null;
  } | null;
  environment?: NotebookEnvironment | null;
  kernels?: { python?: NotebookKernel; r?: NotebookKernel };
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  cells?: NotebookCell[];
};

async function parse<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    let message = fallback;
    try {
      const payload = await response.json();
      message = payload?.detail ?? message;
    } catch {
      const text = await response.text();
      if (text) message = text;
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function headers(json = false) {
  return assistantAuthHeaders(
    json ? { "Content-Type": "application/json" } : {},
  );
}

export async function getNotebookRuntime() {
  return parse<{
    sql: { status: string; boundary: string };
    python: { status: string; boundary: string; persistent?: boolean };
    r: { status: string; boundary: string; persistent?: boolean };
    sandbox: Record<string, unknown>;
    environment?: { install_mode: string; dynamic_install: boolean };
  }>(
    await fetch(`${API}/notebooks/runtime`, {
      credentials: "include",
      headers: headers(),
    }),
    "Runtime notebook indisponible.",
  );
}

export async function listNotebooks(datasetId?: string) {
  const query = datasetId
    ? `?dataset_id=${encodeURIComponent(datasetId)}`
    : "";
  return parse<{ items: NotebookDocument[] }>(
    await fetch(`${API}/notebooks${query}`, {
      credentials: "include",
      headers: headers(),
    }),
    "Liste des notebooks indisponible.",
  );
}

export async function createNotebook(input: {
  name: string;
  dataset_id?: string | null;
  description?: string;
}) {
  return parse<NotebookDocument>(
    await fetch(`${API}/notebooks`, {
      method: "POST",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify(input),
    }),
    "Création du notebook impossible.",
  );
}

export async function getNotebook(id: string) {
  return parse<NotebookDocument>(
    await fetch(`${API}/notebooks/${encodeURIComponent(id)}`, {
      credentials: "include",
      headers: headers(),
    }),
    "Notebook indisponible.",
  );
}

export async function updateNotebook(
  id: string,
  input: { name?: string; description?: string },
) {
  return parse<NotebookDocument>(
    await fetch(`${API}/notebooks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify(input),
    }),
    "Mise à jour du notebook impossible.",
  );
}

export async function bindNotebookDataset(
  notebookId: string,
  datasetId: string | null,
) {
  return parse<NotebookDocument>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/bind`, {
      method: "POST",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify({ dataset_id: datasetId }),
    }),
    "Liaison du notebook au dataset impossible.",
  );
}

export async function runNotebook(
  notebookId: string,
  continueOnError = false,
) {
  return parse<{
    notebook_id: string;
    dataset_id?: string | null;
    dataset_version?: string | null;
    status: "succeeded" | "failed";
    executed: number;
    succeeded: number;
    failed: number;
    stopped_early: boolean;
    runs: NotebookRun[];
  }>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/run`, {
      method: "POST",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify({ continue_on_error: continueOnError }),
    }),
    "Exécution du notebook impossible.",
  );
}

export async function getNotebookDatasetVersions(datasetId: string) {
  return parse<{
    current_id: string;
    root_id: string;
    versions: DatasetVersionRef[];
  }>(
    await fetch(`${API}/datasets/${encodeURIComponent(datasetId)}/versions`, {
      credentials: "include",
      headers: headers(),
    }),
    "Historique des versions indisponible.",
  );
}

export async function promoteNotebookArtifact(
  notebookId: string,
  runId: string,
  filename: string,
) {
  return parse<{
    dataset: {
      id: string;
      root_id: string;
      parent_id?: string | null;
      version: number;
      name?: string | null;
      operation?: Record<string, unknown> | null;
    };
  }>(
    await fetch(
      `${API}/notebooks/${encodeURIComponent(notebookId)}/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(filename)}/promote`,
      {
        method: "POST",
        credentials: "include",
        headers: headers(),
      },
    ),
    "Promotion de l'artefact impossible.",
  );
}

export async function deleteNotebook(id: string) {
  return parse<{ ok: boolean }>(
    await fetch(`${API}/notebooks/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "include",
      headers: headers(),
    }),
    "Suppression du notebook impossible.",
  );
}

export async function addNotebookCell(
  notebookId: string,
  language: NotebookLanguage,
  source = "",
) {
  return parse<NotebookDocument>(
    await fetch(
      `${API}/notebooks/${encodeURIComponent(notebookId)}/cells`,
      {
        method: "POST",
        credentials: "include",
        headers: headers(true),
        body: JSON.stringify({ language, source }),
      },
    ),
    "Ajout de cellule impossible.",
  );
}

export async function updateNotebookCell(
  notebookId: string,
  cellId: string,
  input: {
    language?: NotebookLanguage;
    source?: string;
    position?: number;
  },
) {
  return parse<NotebookDocument>(
    await fetch(
      `${API}/notebooks/${encodeURIComponent(notebookId)}/cells/${encodeURIComponent(cellId)}`,
      {
        method: "PATCH",
        credentials: "include",
        headers: headers(true),
        body: JSON.stringify(input),
      },
    ),
    "Mise à jour de cellule impossible.",
  );
}

export async function deleteNotebookCell(
  notebookId: string,
  cellId: string,
) {
  return parse<NotebookDocument>(
    await fetch(
      `${API}/notebooks/${encodeURIComponent(notebookId)}/cells/${encodeURIComponent(cellId)}`,
      {
        method: "DELETE",
        credentials: "include",
        headers: headers(),
      },
    ),
    "Suppression de cellule impossible.",
  );
}

export async function runNotebookCell(
  notebookId: string,
  cellId: string,
) {
  return parse<NotebookRun>(
    await fetch(
      `${API}/notebooks/${encodeURIComponent(notebookId)}/cells/${encodeURIComponent(cellId)}/run`,
      {
        method: "POST",
        credentials: "include",
        headers: headers(),
      },
    ),
    "Exécution de cellule impossible.",
  );
}

export async function downloadNotebookArtifact(
  artifactPath: string,
  filename: string,
) {
  const url = artifactPath.startsWith("http")
    ? artifactPath
    : `${API.replace(/\/api\/v1$/, "")}${artifactPath}`;

  const response = await fetch(url, {
    credentials: "include",
    headers: headers(),
  });
  if (!response.ok) {
    throw new Error("Téléchargement de l'artefact impossible.");
  }

  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export async function getWorkspaceEnvironment() {
  return parse<WorkspaceEnvironment>(
    await fetch(`${API}/notebooks/workspace-environment`, { credentials: "include", headers: headers() }),
    "Environnement workspace indisponible.",
  );
}

export async function updateWorkspaceEnvironment(input: { python_requirements?: string[]; r_requirements?: string[] }) {
  return parse<WorkspaceEnvironment>(
    await fetch(`${API}/notebooks/workspace-environment`, {
      method: "PUT",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify(input),
    }),
    "Mise à jour de l'environnement workspace impossible.",
  );
}

export async function syncWorkspaceEnvironment() {
  return parse<WorkspaceEnvironment>(
    await fetch(`${API}/notebooks/workspace-environment/sync`, { method: "POST", credentials: "include", headers: headers() }),
    "Synchronisation de l'environnement workspace impossible.",
  );
}

export async function verifyWorkspaceEnvironment() {
  return parse<WorkspaceEnvironment>(
    await fetch(`${API}/notebooks/workspace-environment/verify`, { method: "POST", credentials: "include", headers: headers() }),
    "Vérification de reproductibilité impossible.",
  );
}

export async function getNotebookEnvironment(notebookId: string) {
  return parse<NotebookEnvironment>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/environment`, {
      credentials: "include",
      headers: headers(),
    }),
    "Environnement notebook indisponible.",
  );
}

export async function updateNotebookEnvironment(
  notebookId: string,
  input: { python_requirements?: string[]; r_requirements?: string[] },
) {
  return parse<NotebookEnvironment>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/environment`, {
      method: "PUT",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify(input),
    }),
    "Mise à jour de l'environnement notebook impossible.",
  );
}

export async function syncNotebookEnvironment(notebookId: string) {
  return parse<NotebookEnvironment>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/environment/sync`, {
      method: "POST",
      credentials: "include",
      headers: headers(),
    }),
    "Validation des packages notebook impossible.",
  );
}

export async function getNotebookKernels(notebookId: string) {
  return parse<{ notebook_id: string; persistent: boolean; kernels: { python: NotebookKernel; r: NotebookKernel } }>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/kernels`, {
      credentials: "include",
      headers: headers(),
    }),
    "État des kernels indisponible.",
  );
}

export async function restartNotebookKernel(notebookId: string, language: "python" | "r") {
  return parse<NotebookKernel>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/kernels/${language}/restart`, {
      method: "POST",
      credentials: "include",
      headers: headers(),
    }),
    "Redémarrage du kernel impossible.",
  );
}

export async function restartNotebookKernels(notebookId: string, replay = false) {
  return parse<{ notebook_id: string; kernels: Record<string, NotebookKernel>; replayed: boolean; replay_result?: unknown }>(
    await fetch(`${API}/notebooks/${encodeURIComponent(notebookId)}/kernels/restart`, {
      method: "POST",
      credentials: "include",
      headers: headers(true),
      body: JSON.stringify({ replay }),
    }),
    "Redémarrage des kernels impossible.",
  );
}
