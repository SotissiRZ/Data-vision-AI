"use client";

import { useEffect, useMemo, useState } from "react";

import { assistantEventBus } from "../lib/assistant/event-bus";
import {
  addNotebookCell,
  bindNotebookDataset,
  createNotebook,
  deleteNotebook,
  deleteNotebookCell,
  downloadNotebookArtifact,
  getNotebook,
  getNotebookDatasetVersions,
  getNotebookRuntime,
  getNotebookKernels,
  getWorkspaceEnvironment,
  listNotebooks,
  restartNotebookKernel,
  restartNotebookKernels,
  syncNotebookEnvironment,
  syncWorkspaceEnvironment,
  updateNotebookEnvironment,
  updateWorkspaceEnvironment,
  verifyWorkspaceEnvironment,
  promoteNotebookArtifact,
  runNotebook,
  runNotebookCell,
  updateNotebook,
  updateNotebookCell,
  type NotebookCell,
  type NotebookDocument,
  type NotebookLanguage,
  type NotebookRun,
  type DatasetVersionRef,
  type WorkspaceEnvironment,
} from "../lib/notebook-client";

import styles from "./NotebookStudio.module.css";

type DatasetRef = {
  id: string;
  name?: string;
  version?: number | string;
};

export function NotebookStudio({
  dataset,
  setError,
}: {
  dataset?: DatasetRef | null;
  setError: (message: string) => void;
}) {
  const [items, setItems] = useState<NotebookDocument[]>([]);
  const [active, setActive] = useState<NotebookDocument | null>(null);
  const [runtime, setRuntime] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  const [runningCell, setRunningCell] = useState<string | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<DatasetVersionRef[]>([]);
  const [message, setMessage] = useState("");
  const [pythonRequirements, setPythonRequirements] = useState("");
  const [rRequirements, setRRequirements] = useState("");
  const [environmentStatus, setEnvironmentStatus] = useState<string | null>(null);
  const [workspaceEnvironment, setWorkspaceEnvironment] = useState<WorkspaceEnvironment | null>(null);
  const [workspacePythonRequirements, setWorkspacePythonRequirements] = useState("");
  const [workspaceRRequirements, setWorkspaceRRequirements] = useState("");

  async function loadList(selectId?: string) {
    try {
      const response = await listNotebooks(dataset?.id);
      setItems(response.items);
      const target =
        selectId ??
        active?.id ??
        response.items[0]?.id;

      if (target) {
        const notebook = await getNotebook(target);
        setActive(notebook);
        setDrafts(
          Object.fromEntries(
            (notebook.cells ?? []).map((cell) => [cell.id, cell.source]),
          ),
        );
      } else {
        setActive(null);
        setDrafts({});
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function loadVersions(datasetId?: string | null) {
    if (!datasetId) {
      setVersions([]);
      return;
    }
    try {
      const response = await getNotebookDatasetVersions(datasetId);
      setVersions(response.versions ?? []);
    } catch {
      setVersions([]);
    }
  }

  useEffect(() => {
    void loadList();
    void loadVersions(dataset?.id);
    getNotebookRuntime()
      .then(setRuntime)
      .catch(() => setRuntime(null));
    getWorkspaceEnvironment()
      .then((environment) => {
        setWorkspaceEnvironment(environment);
        setWorkspacePythonRequirements((environment.python_requirements ?? []).join("\n"));
        setWorkspaceRRequirements((environment.r_requirements ?? []).join("\n"));
      })
      .catch(() => setWorkspaceEnvironment(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset?.id]);

  useEffect(() => {
    void loadVersions(active?.dataset_id ?? dataset?.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.dataset_id, dataset?.id]);

  useEffect(() => {
    if (!active?.id) return;
    let cancelled = false;
    getNotebookKernels(active.id)
      .then((payload) => {
        if (!cancelled) {
          setActive((current) => current?.id === active.id ? { ...current, kernels: payload.kernels } : current);
        }
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [active?.id]);

  useEffect(() => {
    setPythonRequirements((active?.environment?.python_requirements ?? []).join("\n"));
    setRRequirements((active?.environment?.r_requirements ?? []).join("\n"));
    setEnvironmentStatus(active?.environment?.status ?? null);
  }, [active?.id, active?.environment?.updated_at]);

  useEffect(() => {
    if (!active) return;
    const current = assistantEventBus.getContext();
    assistantEventBus.setContext({
      selectedEntity: {
        type: "notebook",
        id: active.id,
        label: active.name,
        metadata: {
          datasetId: active.dataset_id,
          datasetVersion: active.dataset_version,
          pythonKernelState: active.kernels?.python?.state_status ?? "new",
          rKernelState: active.kernels?.r?.state_status ?? "new",
          pythonKernelVariables: active.kernels?.python?.variables?.slice(0, 30) ?? [],
          rKernelVariables: active.kernels?.r?.variables?.slice(0, 30) ?? [],
          pythonRequirements: active.environment?.effective_python_requirements ?? active.environment?.python_requirements ?? [],
          rRequirements: active.environment?.effective_r_requirements ?? active.environment?.r_requirements ?? [],
          environmentFingerprint: active.environment?.fingerprint_sha256 ?? null,
          workspaceEnvironmentFingerprint: active.environment?.workspace_environment?.fingerprint_sha256 ?? null,
        },
      },
      uiState: {
        ...(current.uiState ?? {}),
        activeNotebookId: active.id,
        activeNotebookName: active.name,
      },
    });
  }, [active?.id, active?.name, active?.dataset_id, active?.dataset_version, active?.kernels?.python?.state_status, active?.kernels?.r?.state_status, active?.environment?.updated_at]);

  async function openNotebook(id: string) {
    try {
      const notebook = await getNotebook(id);
      setActive(notebook);
      setDrafts(
        Object.fromEntries(
          (notebook.cells ?? []).map((cell) => [cell.id, cell.source]),
        ),
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function create() {
    setBusy(true);
    try {
      const notebook = await createNotebook({
        name: dataset?.name
          ? `Analyse · ${dataset.name}`
          : "Notebook DataVision",
        dataset_id: dataset?.id ?? null,
        description:
          "Notebook reproductible Python / SQL / R lié au contexte DataVision.",
      });
      await loadList(notebook.id);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function rename() {
    if (!active) return;
    const name = window.prompt("Nom du notebook", active.name);
    if (!name?.trim()) return;
    try {
      const notebook = await updateNotebook(active.id, {
        name: name.trim(),
      });
      setActive(notebook);
      await loadList(notebook.id);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function removeNotebook() {
    if (!active) return;
    if (
      !window.confirm(
        `Supprimer « ${active.name} » et son historique d'exécution ?`,
      )
    ) {
      return;
    }

    try {
      await deleteNotebook(active.id);
      setActive(null);
      await loadList();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function addCell(language: NotebookLanguage) {
    if (!active) return;
    try {
      const notebook = await addNotebookCell(
        active.id,
        language,
        defaultSource(language),
      );
      setActive(notebook);
      setDrafts(
        Object.fromEntries(
          (notebook.cells ?? []).map((cell) => [cell.id, cell.source]),
        ),
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function persistCell(cell: NotebookCell) {
    if (!active) return active;
    const source = drafts[cell.id] ?? cell.source;
    const notebook = await updateNotebookCell(
      active.id,
      cell.id,
      { source },
    );
    setActive(notebook);
    return notebook;
  }

  async function run(cell: NotebookCell) {
    if (!active) return;
    setRunningCell(cell.id);
    try {
      await persistCell(cell);
      const result = await runNotebookCell(active.id, cell.id);
      const notebook = await getNotebook(active.id);
      setActive(notebook);

      assistantEventBus.emit({
        type:
          result.status === "succeeded"
            ? "notebook.cell.executed"
            : "notebook.cell.failed",
        severity:
          result.status === "succeeded" ? "info" : "warning",
        payload: {
          notebookId: active.id,
          cellId: cell.id,
          language: cell.language,
          runId: result.id,
          status: result.status,
          elapsedMs: result.elapsed_ms ?? null,
        },
      });
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setRunningCell(null);
    }
  }

  async function bindVersion(datasetId: string) {
    if (!active) return;
    setBusy(true);
    setMessage("");
    try {
      const notebook = await bindNotebookDataset(
        active.id,
        datasetId || null,
      );
      setActive(notebook);
      setMessage(
        datasetId
          ? `Notebook lié au dataset v${notebook.dataset_version ?? "—"}.`
          : "Notebook détaché du dataset.",
      );
      await loadList(notebook.id);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function runAll() {
    if (!active) return;
    setRunningAll(true);
    setMessage("");
    try {
      for (const cell of cells) {
        const source = drafts[cell.id] ?? cell.source;
        if (source !== cell.source) {
          await updateNotebookCell(active.id, cell.id, { source });
        }
      }
      const summary = await runNotebook(active.id, false);
      const notebook = await getNotebook(active.id);
      setActive(notebook);
      setMessage(
        summary.failed
          ? `${summary.succeeded} cellule(s) réussie(s), ${summary.failed} en échec.`
          : `${summary.succeeded} cellule(s) exécutée(s) avec succès.`,
      );
      assistantEventBus.emit({
        type: summary.failed ? "notebook.run.failed" : "notebook.run.succeeded",
        severity: summary.failed ? "warning" : "info",
        payload: {
          notebookId: active.id,
          datasetId: active.dataset_id,
          datasetVersion: active.dataset_version,
          executed: summary.executed,
          failed: summary.failed,
        },
      });
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setRunningAll(false);
    }
  }

  async function promoteArtifact(run: NotebookRun, filename: string) {
    if (!active) return;
    if (!window.confirm(`Créer une nouvelle version du dataset depuis « ${filename} » ?`)) {
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const promoted = await promoteNotebookArtifact(
        active.id,
        run.id,
        filename,
      );
      setMessage(
        `Artefact promu en dataset v${promoted.dataset.version} · ${promoted.dataset.id.slice(0, 8)}…`,
      );
      await loadVersions(promoted.dataset.id);
      assistantEventBus.emit({
        type: "notebook.artifact.promoted",
        severity: "info",
        payload: {
          notebookId: active.id,
          runId: run.id,
          artifact: filename,
          datasetId: promoted.dataset.id,
          datasetVersion: promoted.dataset.version,
        },
      });
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function removeCell(cell: NotebookCell) {
    if (!active) return;
    if (!window.confirm("Supprimer cette cellule ?")) return;
    try {
      const notebook = await deleteNotebookCell(active.id, cell.id);
      setActive(notebook);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function restartKernel(language: "python" | "r") {
    if (!active) return;
    setBusy(true);
    setMessage("");
    try {
      await restartNotebookKernel(active.id, language);
      const notebook = await getNotebook(active.id);
      setActive(notebook);
      setMessage(`Kernel ${language.toUpperCase()} redémarré. Réexécutez les cellules nécessaires pour reconstruire son état.`);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function restartAllKernels(replay = false) {
    if (!active) return;
    if (replay && !window.confirm("Redémarrer les kernels puis réexécuter le notebook depuis le début ?")) return;
    setBusy(true);
    setMessage("");
    try {
      await restartNotebookKernels(active.id, replay);
      const notebook = await getNotebook(active.id);
      setActive(notebook);
      setMessage(replay ? "Kernels redémarrés et état reconstruit par réexécution." : "Kernels redémarrés. Leur namespace est vide.");
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveWorkspaceEnvironment() {
    setBusy(true);
    setMessage("");
    try {
      const parseLines = (value: string) => value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
      await updateWorkspaceEnvironment({
        python_requirements: parseLines(workspacePythonRequirements),
        r_requirements: parseLines(workspaceRRequirements),
      });
      const synced = await syncWorkspaceEnvironment();
      const verified = synced.status === "ready" ? await verifyWorkspaceEnvironment() : synced;
      setWorkspaceEnvironment(verified);
      if (active?.id) setActive(await getNotebook(active.id));
      const missing = [...(synced.missing_python ?? []), ...(synced.missing_r ?? [])];
      setMessage(
        missing.length
          ? `Environnement workspace incomplet · packages absents: ${missing.join(", ")}`
          : `Environnement workspace verrouillé · ${synced.fingerprint_sha256.slice(0, 12)}…`,
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveEnvironment() {
    if (!active) return;
    setBusy(true);
    setEnvironmentStatus(null);
    try {
      const parseLines = (value: string) => value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
      await updateNotebookEnvironment(active.id, {
        python_requirements: parseLines(pythonRequirements),
        r_requirements: parseLines(rRequirements),
      });
      const synced = await syncNotebookEnvironment(active.id);
      setEnvironmentStatus(synced.status ?? "ready");
      const notebook = await getNotebook(active.id);
      setActive(notebook);
      const missing = [...(synced.missing_python ?? []), ...(synced.missing_r ?? [])];
      setMessage(missing.length ? `Environnement enregistré · packages absents: ${missing.join(", ")}` : "Environnement notebook verrouillé sur les packages disponibles.");
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  const cells = useMemo(
    () => [...(active?.cells ?? [])].sort((a, b) => a.position - b.position),
    [active?.cells],
  );

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>
        <div>
          <span className={styles.eyebrow}>
            NOTEBOOK · PYTHON · SQL · R
          </span>
          <h1>Notebook Workspace</h1>
          <p>
            Exécutez des analyses reproductibles. Python et R disposent maintenant
            de kernels persistants isolés ; SQL reste strictement read-only.
          </p>
        </div>
        <div className={styles.runtime}>
          <RuntimeBadge label="Python" state={runtime?.python?.status} />
          <RuntimeBadge label="SQL" state={runtime?.sql?.status} />
          <RuntimeBadge label="R" state={runtime?.r?.status} />
        </div>
      </div>

      {!dataset && (
        <div className={styles.notice}>
          Aucun dataset actif. Vous pouvez créer un notebook documentaire,
          mais les cellules Python, SQL et R nécessitent un dataset lié.
        </div>
      )}

      {message && <div className={styles.successNotice}>{message}</div>}

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHead}>
            <strong>Notebooks</strong>
            <button type="button" onClick={() => void create()} disabled={busy}>
              +
            </button>
          </div>

          <div className={styles.notebookList}>
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void openNotebook(item.id)}
                className={item.id === active?.id ? styles.activeNotebook : ""}
              >
                <strong>{item.name}</strong>
                <small>
                  {item.dataset_version
                    ? `Dataset v${item.dataset_version}`
                    : "Sans dataset"}
                </small>
              </button>
            ))}

            {!items.length && (
              <div className={styles.emptySide}>
                Aucun notebook.
              </div>
            )}
          </div>
        </aside>

        <main className={styles.workspace}>
          {!active ? (
            <div className={styles.emptyWorkspace}>
              <div>⌘</div>
              <h3>Créez votre premier notebook</h3>
              <p>
                Il sera automatiquement relié au dataset et à sa version
                actuelle.
              </p>
              <button type="button" onClick={() => void create()}>
                Créer un notebook
              </button>
            </div>
          ) : (
            <>
              <header className={styles.notebookHeader}>
                <div>
                  <h2>{active.name}</h2>
                  <p>
                    {active.dataset_id
                      ? `Dataset ${active.dataset_id.slice(0, 8)}… · version ${active.dataset_version ?? "—"}`
                      : "Notebook sans dataset"}
                  </p>
                </div>
                <div className={styles.headerActions}>
                  {!!versions.length && (
                    <label className={styles.bindingSelect}>
                      <span>Version liée</span>
                      <select
                        value={active.dataset_id ?? ""}
                        disabled={busy || runningAll}
                        onChange={(event) => void bindVersion(event.target.value)}
                      >
                        <option value="">Sans dataset</option>
                        {versions.map((version) => (
                          <option key={version.id} value={version.id}>
                            v{version.version} · {version.name ?? version.id.slice(0, 8)}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button
                    type="button"
                    onClick={() => void runAll()}
                    disabled={runningAll || busy || !active.dataset_id}
                  >
                    {runningAll ? "Exécution…" : "▶ Tout exécuter"}
                  </button>
                  <button type="button" onClick={() => void rename()}>
                    Renommer
                  </button>
                  <button
                    type="button"
                    className={styles.danger}
                    onClick={() => void removeNotebook()}
                  >
                    Supprimer
                  </button>
                </div>
              </header>

              <section className={styles.kernelPanel}>
                <div className={styles.kernelPanelHead}>
                  <div>
                    <strong>Runtime persistant</strong>
                    <small>Les variables restent disponibles entre les cellules d'un même langage.</small>
                  </div>
                  <div className={styles.kernelActions}>
                    <button type="button" disabled={busy} onClick={() => void restartAllKernels(false)}>Redémarrer</button>
                    <button type="button" disabled={busy || !active.dataset_id} onClick={() => void restartAllKernels(true)}>Redémarrer + reconstruire</button>
                  </div>
                </div>
                <div className={styles.kernelGrid}>
                  {(["python", "r"] as const).map((language) => {
                    const kernel = active.kernels?.[language];
                    return (
                      <article key={language} className={styles.kernelCard}>
                        <div><b>{language.toUpperCase()}</b><span className={kernel?.state_status === "ready" ? styles.kernelReady : styles.kernelReset}>{kernel?.state_status ?? "new"}</span></div>
                        <small>{kernel?.execution_count ?? 0} exécution(s) · {kernel?.persistent ? "persistant" : "stateless"}</small>
                        {!!kernel?.variables?.length && <p>Variables: {kernel.variables.slice(0, 8).join(", ")}{kernel.variables.length > 8 ? "…" : ""}</p>}
                        <button type="button" disabled={busy} onClick={() => void restartKernel(language)}>Réinitialiser {language.toUpperCase()}</button>
                      </article>
                    );
                  })}
                </div>
                <details className={styles.environmentPanel}>
                  <summary>Environnement workspace · {workspaceEnvironment?.status ?? "chargement"}</summary>
                  <p>Socle Python/R partagé par le workspace. Aucun package n'est installé dynamiquement : le manifest est résolu contre l'image sandbox puis verrouillé par SHA-256.</p>
                  <div className={styles.environmentGrid}>
                    <label><span>Python workspace</span><textarea value={workspacePythonRequirements} onChange={(event) => setWorkspacePythonRequirements(event.target.value)} rows={4} placeholder="pandas>=2.3\nscikit-learn" /></label>
                    <label><span>R workspace</span><textarea value={workspaceRRequirements} onChange={(event) => setWorkspaceRRequirements(event.target.value)} rows={4} placeholder="dplyr\nggplot2" /></label>
                  </div>
                  <div className={styles.environmentMeta}>
                    <span>Isolation: {String(workspaceEnvironment?.policy?.isolation ?? "workspace-sandbox")}</span>
                    <span>Reproductible: {workspaceEnvironment?.reproducible ? "oui" : "non"}</span>
                    <span>SHA: {workspaceEnvironment?.fingerprint_sha256 ? `${workspaceEnvironment.fingerprint_sha256.slice(0, 12)}…` : "—"}</span>
                    <button type="button" disabled={busy} onClick={() => void saveWorkspaceEnvironment()}>Verrouiller le workspace</button>
                  </div>
                </details>
                <details className={styles.environmentPanel}>
                  <summary>Overlay notebook & packages {environmentStatus ? `· ${environmentStatus}` : ""}</summary>
                  <p>Ces dépendances s'ajoutent au manifest du workspace. Le notebook conserve ensuite une empreinte effective dans la provenance de chaque run Python/R.</p>
                  <div className={styles.environmentGrid}>
                    <label><span>Python · une dépendance par ligne</span><textarea value={pythonRequirements} onChange={(event) => setPythonRequirements(event.target.value)} rows={4} placeholder="pandas>=2.3\nscikit-learn" /></label>
                    <label><span>R · une dépendance par ligne</span><textarea value={rRequirements} onChange={(event) => setRRequirements(event.target.value)} rows={4} placeholder="dplyr\nggplot2" /></label>
                  </div>
                  <div className={styles.environmentMeta}>
                    <span>Mode: {String(active.environment?.policy?.install_mode ?? "image-managed")}</span>
                    <span>Python lock: {Object.keys(active.environment?.python_lock ?? {}).length}</span>
                    <span>R lock: {Object.keys(active.environment?.r_lock ?? {}).length}</span>
                    <span>Reproductible: {active.environment?.reproducible ? "oui" : "non"}</span>
                    <span>SHA: {active.environment?.fingerprint_sha256 ? `${active.environment.fingerprint_sha256.slice(0, 12)}…` : "—"}</span>
                    <button type="button" disabled={busy} onClick={() => void saveEnvironment()}>Enregistrer & valider</button>
                  </div>
                </details>
              </section>

              <div className={styles.cellToolbar}>
                <span>Ajouter :</span>
                {(["markdown", "python", "sql", "r"] as NotebookLanguage[]).map(
                  (language) => (
                    <button
                      key={language}
                      type="button"
                      onClick={() => void addCell(language)}
                    >
                      + {language.toUpperCase()}
                    </button>
                  ),
                )}
              </div>

              <div className={styles.cells}>
                {cells.map((cell, index) => (
                  <CellEditor
                    key={cell.id}
                    index={index + 1}
                    cell={cell}
                    source={drafts[cell.id] ?? cell.source}
                    running={runningCell === cell.id}
                    onSource={(source) =>
                      setDrafts((current) => ({
                        ...current,
                        [cell.id]: source,
                      }))
                    }
                    onBlur={() => {
                      void persistCell(cell).catch((error) =>
                        setError(
                          error instanceof Error
                            ? error.message
                            : String(error),
                        ),
                      );
                    }}
                    onRun={() => void run(cell)}
                    onDelete={() => void removeCell(cell)}
                    onDownload={(path, name) =>
                      void downloadNotebookArtifact(path, name).catch(
                        (error) =>
                          setError(
                            error instanceof Error
                              ? error.message
                              : String(error),
                          ),
                      )
                    }
                    onPromote={(run, name) => void promoteArtifact(run, name)}
                  />
                ))}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function CellEditor({
  index,
  cell,
  source,
  running,
  onSource,
  onBlur,
  onRun,
  onDelete,
  onDownload,
  onPromote,
}: {
  index: number;
  cell: NotebookCell;
  source: string;
  running: boolean;
  onSource: (source: string) => void;
  onBlur: () => void;
  onRun: () => void;
  onDelete: () => void;
  onDownload: (path: string, name: string) => void;
  onPromote: (run: NotebookRun, name: string) => void;
}) {
  const run = cell.last_run;

  return (
    <article className={styles.cell}>
      <header className={styles.cellHead}>
        <div>
          <span className={styles.cellNumber}>{index}</span>
          <span className={styles.language}>{cell.language}</span>
        </div>
        <div>
          {cell.language !== "markdown" && (
            <button
              type="button"
              className={styles.runButton}
              disabled={running}
              onClick={onRun}
            >
              {running ? "Exécution…" : "▶ Exécuter"}
            </button>
          )}
          {cell.language === "markdown" && (
            <button
              type="button"
              className={styles.runButton}
              disabled={running}
              onClick={onRun}
            >
              Enregistrer
            </button>
          )}
          <button type="button" className={styles.deleteCell} onClick={onDelete}>
            ×
          </button>
        </div>
      </header>

      <textarea
        value={source}
        onChange={(event) => onSource(event.target.value)}
        onBlur={onBlur}
        spellCheck={cell.language === "markdown"}
        className={styles.editor}
        rows={Math.max(4, Math.min(18, source.split("\n").length + 1))}
      />

      {run && (
        <RunOutput
          run={run}
          onDownload={onDownload}
          onPromote={onPromote}
        />
      )}
    </article>
  );
}

function RunOutput({
  run,
  onDownload,
  onPromote,
}: {
  run: NotebookRun;
  onDownload: (path: string, name: string) => void;
  onPromote: (run: NotebookRun, name: string) => void;
}) {
  const result = run.result;
  return (
    <div
      className={`${styles.output} ${
        run.status === "failed" ? styles.failed : ""
      }`}
    >
      <div className={styles.outputMeta}>
        <span>{run.status}</span>
        <span>{run.engine ?? run.language}</span>
        <span>
          {run.elapsed_ms != null
            ? `${Number(run.elapsed_ms).toFixed(1)} ms`
            : "—"}
        </span>
        <span>dataset v{run.dataset_version ?? "—"}</span>
      </div>

      {result?.type === "dataframe" && result.columns && result.rows ? (
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                {result.columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 100).map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {result.columns!.map((column) => (
                    <td key={column}>
                      {renderValue(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.truncated && (
            <small>Résultat tronqué dans l'interface.</small>
          )}
        </div>
      ) : result != null ? (
        <pre className={styles.resultPre}>
          {JSON.stringify(
            result.value !== undefined ? result.value : result,
            null,
            2,
          )}
        </pre>
      ) : null}

      {run.stdout && (
        <details>
          <summary>stdout</summary>
          <pre>{run.stdout}</pre>
        </details>
      )}

      {run.stderr && (
        <details open={run.status === "failed"}>
          <summary>stderr</summary>
          <pre>{run.stderr}</pre>
        </details>
      )}

      {!!run.artifacts?.length && (
        <div className={styles.artifacts}>
          {run.artifacts.map((artifact) => (
            <div className={styles.artifactActions} key={artifact.name}>
              <button
                type="button"
                onClick={() =>
                  onDownload(
                    artifact.download_path,
                    artifact.name,
                  )
                }
              >
                ↓ {artifact.name}
              </button>
              {[".csv", ".json"].includes(artifact.extension) && (
                <button
                  type="button"
                  className={styles.promoteArtifact}
                  onClick={() => onPromote(run, artifact.name)}
                >
                  ↗ Promouvoir en dataset
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <details className={styles.provenance}>
        <summary>Provenance</summary>
        <pre>{JSON.stringify(run.provenance, null, 2)}</pre>
      </details>
    </div>
  );
}

function RuntimeBadge({
  label,
  state,
}: {
  label: string;
  state?: string;
}) {
  const ok = state === "ok";
  return (
    <span className={ok ? styles.runtimeOk : styles.runtimeOff}>
      <i />
      {label}
    </span>
  );
}

function defaultSource(language: NotebookLanguage) {
  if (language === "python") {
    return "# DataFrame gouverné disponible dans `df`.\ndf.describe(include='all').T";
  }
  if (language === "sql") {
    return "SELECT * FROM dataset LIMIT 20";
  }
  if (language === "r") {
    return "# Dataset gouverné disponible dans `data`.\nsummary(data)";
  }
  return "## Nouvelle section\n\nDécrivez ici votre analyse.";
}

function renderValue(value: unknown) {
  if (value == null) return "—";
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}
