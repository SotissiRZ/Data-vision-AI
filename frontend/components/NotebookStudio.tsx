"use client";

import { useEffect, useMemo, useState } from "react";

import { assistantEventBus } from "../lib/assistant/event-bus";
import {
  addNotebookCell,
  createNotebook,
  deleteNotebook,
  deleteNotebookCell,
  downloadNotebookArtifact,
  getNotebook,
  getNotebookRuntime,
  listNotebooks,
  runNotebookCell,
  updateNotebook,
  updateNotebookCell,
  type NotebookCell,
  type NotebookDocument,
  type NotebookLanguage,
  type NotebookRun,
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
  const [drafts, setDrafts] = useState<Record<string, string>>({});

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

  useEffect(() => {
    void loadList();
    getNotebookRuntime()
      .then(setRuntime)
      .catch(() => setRuntime(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset?.id]);

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
        },
      },
      uiState: {
        ...(current.uiState ?? {}),
        activeNotebookId: active.id,
        activeNotebookName: active.name,
      },
    });
  }, [active?.id, active?.name]);

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
            Exécutez des analyses reproductibles. Python et R s'exécutent
            dans un sandbox isolé ; SQL reste strictement read-only.
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
                <div>
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
        />
      )}
    </article>
  );
}

function RunOutput({
  run,
  onDownload,
}: {
  run: NotebookRun;
  onDownload: (path: string, name: string) => void;
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
            <button
              type="button"
              key={artifact.name}
              onClick={() =>
                onDownload(
                  artifact.download_path,
                  artifact.name,
                )
              }
            >
              ↓ {artifact.name}
            </button>
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
