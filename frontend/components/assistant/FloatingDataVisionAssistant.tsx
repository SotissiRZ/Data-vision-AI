"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type {
  AssistantAdapter,
  AssistantActionProposal,
  AssistantAttachment,
  ProactiveAlert,
  ProjectMemoryEntry,
  ProjectMemoryPolicy,
} from "../../lib/assistant/adapter";
import {
  assistantEventBus,
  type AssistantContextSnapshot,
} from "../../lib/assistant/event-bus";
import {
  BrowserVoiceController,
  type VoiceState,
} from "../../lib/assistant/voice";
import { toSpeechText } from "../../lib/assistant/speech-text";
import { applyAssistantHostEffects } from "../../lib/assistant/effects";
import styles from "./FloatingDataVisionAssistant.module.css";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  actions?: AssistantActionProposal[];
  attachments?: AssistantAttachment[];
  metadata?: Record<string, unknown>;
};

type ProactiveVoiceMode = "off" | "critical_only" | "important" | "active";

export function FloatingDataVisionAssistant({
  adapter,
  locale = "fr-FR",
  proactiveVoiceMode = "critical_only",
}: {
  adapter: AssistantAdapter;
  locale?: string;
  proactiveVoiceMode?: ProactiveVoiceMode;
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [continuousVoice, setContinuousVoice] = useState(false);
  const [speechEnabled, setSpeechEnabled] = useState(false);
  const [voiceAlertMode, setVoiceAlertMode] = useState<ProactiveVoiceMode>(proactiveVoiceMode);
  const [context, setContext] = useState<AssistantContextSnapshot>(
    assistantEventBus.getContext(),
  );
  const [contextOpen, setContextOpen] = useState(false);
  const [recentArtifacts, setRecentArtifacts] = useState<Array<Record<string, any>>>([]);
  const [lastReference, setLastReference] = useState<Record<string, any> | null>(null);
  const [projectMemoryEntries, setProjectMemoryEntries] = useState<ProjectMemoryEntry[]>([]);
  const [projectMemoryPolicy, setProjectMemoryPolicy] = useState<ProjectMemoryPolicy | null>(null);
  const [projectMemoryCanManage, setProjectMemoryCanManage] = useState(true);
  const [projectMemoryLoading, setProjectMemoryLoading] = useState(false);
  const [projectMemoryQuery, setProjectMemoryQuery] = useState("");
  const [projectMemorySearchMode, setProjectMemorySearchMode] = useState<"semantic_local" | "recency">("recency");
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [alerts, setAlerts] = useState<ProactiveAlert[]>([]);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: crypto.randomUUID(),
      role: "assistant",
      text: "Je suis DataVision AI. Je peux vous aider à comprendre, analyser et agir sur votre projet.",
    },
  ]);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const observeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingObservationRef = useRef<{ event: any; context: AssistantContextSnapshot } | null>(null);
  const lastObservationKeyRef = useRef("");
  const lastObservationAtRef = useRef(0);
  const snoozedAlertsRef = useRef<Map<string, number>>(new Map());

  const contextDetails = useMemo(() => {
    const ui = context.uiState ?? {};
    const temporal = ui.temporalCoverage as
      | { primary?: { column?: string; start?: string; end?: string } | null }
      | undefined;
    const primary = temporal?.primary ?? null;
    return {
      datasetName: String(ui.datasetName ?? ""),
      datasetVersion: ui.datasetVersion ?? context.activeDatasetVersionId,
      rowCount: ui.rowCount,
      columnCount: ui.columnCount,
      qualityScore: ui.qualityScore,
      selected: context.selectedEntity?.label ?? context.selectedEntity?.id ?? "",
      screen: context.screen ?? context.route ?? "application",
      period:
        primary?.start && primary?.end
          ? `${formatContextDate(primary.start)} → ${formatContextDate(primary.end)}`
          : "",
      periodColumn: primary?.column ?? "",
    };
  }, [context]);

  const hasGroundedContext = Boolean(
    context.activeDatasetId || context.activeModelId || context.selectedEntity,
  );

  const voice = useMemo(
    () =>
      new BrowserVoiceController({
        language: locale,
        onState: setVoiceState,
        onFinalText: (text) => {
          setInput(text);
          void sendMessage(text);
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [locale],
  );


useEffect(() => {
  try {
    setSpeechEnabled(
      window.localStorage.getItem(
        "datavision.assistant.tts.enabled",
      ) === "true",
    );
    setContinuousVoice(
      window.localStorage.getItem("datavision.assistant.voice.continuous") === "true",
    );
    const storedMode = window.localStorage.getItem("datavision.assistant.voice.proactive_mode") as ProactiveVoiceMode | null;
    if (storedMode && ["off", "critical_only", "important", "active"].includes(storedMode)) {
      setVoiceAlertMode(storedMode);
    }
  } catch {
    setSpeechEnabled(false);
  }
}, []);

  useEffect(() => {
    const offContext = assistantEventBus.onContext(setContext);

    const deliverObservation = async (
      event: any,
      currentContext: AssistantContextSnapshot,
    ) => {
      try {
        const dataset = currentContext.activeDatasetId ?? "";
        const entity = currentContext.selectedEntity?.id ?? "";
        const key = `${event.type}|${dataset}|${entity}`;
        const now = Date.now();
        if (
          event.severity !== "critical" &&
          key === lastObservationKeyRef.current &&
          now - lastObservationAtRef.current < 1500
        ) {
          return;
        }
        lastObservationKeyRef.current = key;
        lastObservationAtRef.current = now;

        const newAlerts = await adapter.observe({
          event,
          context: currentContext,
        });
        if (!newAlerts.length) return;
        const nowMs = Date.now();
        const visibleAlerts = newAlerts.filter((alert) => {
          const key = alert.fingerprint ?? alert.id;
          return (snoozedAlertsRef.current.get(key) ?? 0) <= nowMs;
        });
        if (!visibleAlerts.length) return;

        setAlerts((prev) => {
          const seen = new Set<string>();
          return [...visibleAlerts, ...prev]
            .filter((alert) => {
              if (seen.has(alert.id)) return false;
              seen.add(alert.id);
              return true;
            })
            .slice(0, 5);
        });

        const mostImportant =
          visibleAlerts.find((a) => a.severity === "critical") ?? visibleAlerts[0];

        if (mostImportant.severity === "critical") setOpen(true);

        if (
          speechEnabled &&
          shouldSpeakAlert(mostImportant, voiceAlertMode)
        ) {
          voice.speak(
            toSpeechText(`${mostImportant.title}. ${mostImportant.message}`),
            { language: locale },
          );
        }
      } catch {
        // Best-effort only: the host UI must remain usable.
      }
    };

    const offEvent = assistantEventBus.onEvent((event, currentContext) => {
      if (event.severity === "critical") {
        if (observeTimerRef.current) clearTimeout(observeTimerRef.current);
        pendingObservationRef.current = null;
        void deliverObservation(event, currentContext);
        return;
      }

      pendingObservationRef.current = { event, context: currentContext };
      if (observeTimerRef.current) clearTimeout(observeTimerRef.current);
      observeTimerRef.current = setTimeout(() => {
        const pending = pendingObservationRef.current;
        pendingObservationRef.current = null;
        if (pending) {
          void deliverObservation(pending.event, pending.context);
        }
      }, 280);
    });

    return () => {
      offContext();
      offEvent();
      if (observeTimerRef.current) clearTimeout(observeTimerRef.current);
      voice.destroy();
    };
  }, [adapter, locale, speechEnabled, voice, voiceAlertMode]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, busy]);

  async function refreshProjectMemory(queryOverride?: string) {
    if (!adapter.getProjectMemory) return;
    setProjectMemoryLoading(true);
    try {
      const query = queryOverride !== undefined ? queryOverride : projectMemoryQuery;
      const response = await adapter.getProjectMemory(query.trim() || undefined);
      setProjectMemoryEntries(response.entries ?? []);
      setProjectMemoryPolicy(response.policy ?? null);
      setProjectMemoryCanManage(response.can_manage !== false);
      setProjectMemorySearchMode(response.search_mode ?? "recency");
    } catch {
      // Project memory is optional; session context remains usable.
    } finally {
      setProjectMemoryLoading(false);
    }
  }

  useEffect(() => {
    if (!open || !contextOpen || !adapter.getProjectMemory) return;
    void refreshProjectMemory();
    // Refresh when the governed workspace changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contextOpen, adapter, context.workspaceId]);

  async function toggleProjectMemoryAutoRecall() {
    if (!adapter.updateProjectMemoryPolicy || !projectMemoryPolicy) return;
    try {
      const response = await adapter.updateProjectMemoryPolicy({
        auto_recall: !projectMemoryPolicy.auto_recall,
      });
      setProjectMemoryPolicy(response.policy);
    } catch {
      // Keep the current policy visible if persistence fails.
    }
  }

  async function toggleProjectMemoryPin(entry: ProjectMemoryEntry) {
    if (!adapter.pinProjectMemory) return;
    try {
      await adapter.pinProjectMemory(entry.id, !entry.pinned);
      await refreshProjectMemory();
    } catch {
      // Governed backend remains authoritative.
    }
  }

  async function forgetProjectMemory(entry: ProjectMemoryEntry) {
    if (!adapter.forgetProjectMemory) return;
    try {
      await adapter.forgetProjectMemory(entry.id);
      await refreshProjectMemory();
    } catch {
      // Governed backend remains authoritative.
    }
  }

  function openProjectMemory(entry: ProjectMemoryEntry) {
    const payload = entry.payload ?? {};
    const kind = String(entry.kind ?? "analysis_result");
    const view =
      kind === "chart" ? "visual" :
      kind === "model" ? "registry" :
      kind === "report" ? "report" :
      kind === "statistical_result" ? "tests" :
      kind === "explanation" ? "xai" :
      kind === "root_cause" || kind === "decision_scenario" ? "decision" :
      "ai";
    window.dispatchEvent(new CustomEvent("datavision:assistant-navigate", {
      detail: {
        view,
        datasetId: entry.dataset_id,
        modelId: typeof payload.model_id === "string" ? payload.model_id : undefined,
        artifactId: entry.artifact_id,
        projectMemoryId: entry.id,
        title: entry.title,
      },
    }));
  }

  async function duplicateProjectMemory(entry: ProjectMemoryEntry) {
    if (!adapter.duplicateProjectMemory) return;
    try {
      await adapter.duplicateProjectMemory(entry.id);
      await refreshProjectMemory();
    } catch {
      // Governed backend remains authoritative.
    }
  }

  function replayProjectMemory(entry: ProjectMemoryEntry, onActiveDataset = false) {
    const suffix = onActiveDataset ? " sur le dataset actif" : "";
    void sendMessage(`Relance cet artefact project-memory:${entry.id}${suffix}.`);
  }

  async function sendMessage(explicitText?: string) {
    const text = (explicitText ?? input).trim();
    if (!text || busy) return;

    voice.stopSpeaking();
    setBusy(true);
    setInput("");

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        text,
        attachments,
      },
    ]);

    try {
      const liveContext = assistantEventBus.getContext();
      const response = await adapter.sendMessage({
        message: text,
        context: liveContext,
        attachmentIds: attachments.map((item) => item.id),
      });
      applyAssistantHostEffects(response, liveContext);

      const artifacts = Array.isArray(response.metadata?.recent_artifacts)
        ? (response.metadata?.recent_artifacts as Array<Record<string, any>>)
        : [];
      if (artifacts.length) setRecentArtifacts(artifacts);
      const resolvedReference = response.metadata?.last_reference_resolution;
      if (resolvedReference && typeof resolvedReference === "object") {
        setLastReference(resolvedReference as Record<string, any>);
      }
      if (contextOpen) void refreshProjectMemory();

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.message,
          actions: response.actions,
          attachments: response.attachments,
          metadata: response.metadata,
        },
      ]);

      setAttachments([]);

      if (speechEnabled && response.speak !== false) {
        voice.speak(toSpeechText(response.message), { language: locale });
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text:
            error instanceof Error
              ? error.message
              : "Erreur pendant la communication avec DataVision AI.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function handleFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (!list.length) return;

    if (!adapter.uploadFiles) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text: "Le connecteur d'upload DataVision n'est pas disponible.",
        },
      ]);
      return;
    }

    try {
      const uploaded = await adapter.uploadFiles(list);
      setAttachments((prev) => [...prev, ...uploaded]);
      assistantEventBus.emit({
        type: "file.uploaded",
        severity: "info",
        payload: {
          files: uploaded.map((item) => ({
            id: item.id,
            name: item.name,
            mimeType: item.mimeType,
          })),
        },
      });
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text: error instanceof Error ? error.message : "Échec de l'upload.",
        },
      ]);
    }
  }

  async function executeAction(action: AssistantActionProposal) {
    if (!adapter.executeAction) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text: "Cette action n'est pas raccordée au moteur gouverné.",
        },
      ]);
      return;
    }

    const sensitive =
      action.risk === "destructive" || action.risk === "external";

    // A continuation action is already rendered as an explicit governed
    // confirmation card. Keep window.confirm only for legacy/fallback actions.
    if (sensitive && !action.continuation) {
      const accepted = window.confirm(
        `DataVision demande votre confirmation.\n\n${action.label}\n\n${action.description ?? ""}\n\nL'action sera contrôlée à nouveau côté serveur avant exécution.`,
      );
      if (!accepted) return;
    }

    setBusy(true);
    try {
      const liveContext = assistantEventBus.getContext();
      const response = await adapter.executeAction(action, liveContext);
      applyAssistantHostEffects(response, liveContext);
      const artifacts = Array.isArray(response.metadata?.recent_artifacts)
        ? (response.metadata?.recent_artifacts as Array<Record<string, any>>)
        : [];
      if (artifacts.length) setRecentArtifacts(artifacts);
      const resolvedReference = response.metadata?.last_reference_resolution;
      if (resolvedReference && typeof resolvedReference === "object") {
        setLastReference(resolvedReference as Record<string, any>);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.message,
          actions: response.actions,
          attachments: response.attachments,
          metadata: response.metadata,
        },
      ]);

      if (speechEnabled && response.speak !== false) {
        voice.speak(toSpeechText(response.message), { language: locale });
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text:
            error instanceof Error
              ? error.message
              : "L'action DataVision AI a échoué.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function rejectAction(action: AssistantActionProposal) {
    if (!adapter.rejectAction) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text: "Le refus explicite n'est pas raccordé au moteur gouverné.",
        },
      ]);
      return;
    }

    setBusy(true);
    try {
      const liveContext = assistantEventBus.getContext();
      const response = await adapter.rejectAction(action, liveContext);
      const resolvedReference = response.metadata?.last_reference_resolution;
      if (resolvedReference && typeof resolvedReference === "object") {
        setLastReference(resolvedReference as Record<string, any>);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.message,
          actions: response.actions,
          attachments: response.attachments,
          metadata: response.metadata,
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          text:
            error instanceof Error
              ? error.message
              : "Le refus de l'action n'a pas pu être enregistré.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function toggleListening() {
    if (
      voiceState === "listening" ||
      voiceState === "requesting_permission"
    ) {
      voice.stopListening();
      return;
    }

    voice.listen({ continuous: continuousVoice });
  }

  const hasCriticalAlert = alerts.some(
    (alert) => alert.severity === "critical",
  );

  return (
    <div className={styles.portal} data-datavis-assistant="mounted">
      <button
        type="button"
        aria-label={open ? "Fermer DataVision AI" : "Ouvrir DataVision AI"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={`${styles.launcher} ${open ? styles.launcherOpen : ""}`}
      >
        <span className={styles.launcherMark}>DV</span>
        <span className={styles.launcherText}>AI</span>
        {hasCriticalAlert && <span className={styles.criticalDot} />}
      </button>

      {open && (
        <section
          className={styles.panel}
          role="dialog"
          aria-label="Assistant DataVision AI"
        >
          <header className={styles.header}>
            <div className={styles.headerIdentity}>
              <div className={styles.logo}>DV</div>
              <div>
                <div className={styles.title}>DataVision AI</div>
                <div className={styles.status}>
                  {statusLabel(voiceState, busy)}{speechEnabled ? " · voix active" : " · voix coupée"}
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                voice.stopSpeaking();
                setOpen(false);
              }}
              className={styles.closeButton}
              aria-label="Fermer"
            >
              ×
            </button>
          </header>

          <div className={styles.contextStrip}>
            <button
              type="button"
              className={styles.contextToggle}
              onClick={() => setContextOpen((value) => !value)}
              aria-expanded={contextOpen}
            >
              <span className={hasGroundedContext ? styles.contextOk : styles.contextMuted}>
                {hasGroundedContext ? "✓" : "○"}
              </span>
              <span>
                <b>{hasGroundedContext ? "Contexte actif" : "Contexte limité"}</b>
                <small>
                  {contextDetails.datasetName || contextDetails.screen}
                  {contextDetails.selected ? ` · ${contextDetails.selected}` : ""}
                </small>
              </span>
              <i>{contextOpen ? "⌃" : "⌄"}</i>
            </button>

            {contextOpen && (
              <div className={styles.contextDetails}>
                <div><span>Vue</span><b>{contextDetails.screen}</b></div>
                <div><span>Dataset</span><b>{contextDetails.datasetName || "Aucun dataset actif"}</b></div>
                {contextDetails.datasetVersion != null && (
                  <div><span>Version</span><b>v{String(contextDetails.datasetVersion)}</b></div>
                )}
                {contextDetails.rowCount != null && (
                  <div><span>Lignes</span><b>{String(contextDetails.rowCount)}</b></div>
                )}
                {contextDetails.columnCount != null && (
                  <div><span>Variables</span><b>{String(contextDetails.columnCount)}</b></div>
                )}
                {contextDetails.qualityScore != null && (
                  <div><span>Qualité</span><b>{String(contextDetails.qualityScore)}/100</b></div>
                )}
                {contextDetails.selected && (
                  <div><span>Variable</span><b>{contextDetails.selected}</b></div>
                )}
                {contextDetails.period && (
                  <div className={styles.contextWide}>
                    <span>Période{contextDetails.periodColumn ? ` · ${contextDetails.periodColumn}` : ""}</span>
                    <b>{contextDetails.period}</b>
                  </div>
                )}
                {recentArtifacts.length > 0 && (
                  <div className={styles.contextWide}>
                    <span>Résultats mémorisés</span>
                    <div className={styles.artifactList}>
                      {recentArtifacts.slice(0, 5).map((artifact, index) => (
                        <div className={styles.artifactItem} key={String(artifact.id ?? index)}>
                          <b>{String(artifact.reference_name ?? artifact.label ?? `Résultat ${index + 1}`)}</b>
                          <small>{String(artifact.label ?? artifact.summary ?? "Résultat analytique")}</small>
                          {(artifact.model_id || artifact.chart_id || artifact.report_id) && (
                            <code>{String(artifact.model_id ?? artifact.chart_id ?? artifact.report_id)}</code>
                          )}
                        </div>
                      ))}
                    </div>
                    <small className={styles.artifactSummary}>
                      Vous pouvez dire « le deuxième graphique », « ce modèle » ou citer un identifiant.
                    </small>
                  </div>
                )}
                {adapter.getProjectMemory && (
                  <div className={styles.contextWide}>
                    <div className={styles.projectMemoryHeader}>
                      <span>Mémoire projet</span>
                      {projectMemoryPolicy && projectMemoryCanManage && adapter.updateProjectMemoryPolicy && (
                        <button
                          type="button"
                          className={projectMemoryPolicy.auto_recall ? styles.memoryPolicyOn : styles.memoryPolicyOff}
                          onClick={toggleProjectMemoryAutoRecall}
                        >
                          {projectMemoryPolicy.auto_recall ? "Rappel auto" : "Rappel manuel"}
                        </button>
                      )}
                    </div>
                    <form
                      className={styles.projectMemorySearch}
                      onSubmit={(event) => {
                        event.preventDefault();
                        void refreshProjectMemory(projectMemoryQuery);
                      }}
                    >
                      <input
                        value={projectMemoryQuery}
                        onChange={(event) => setProjectMemoryQuery(event.target.value)}
                        placeholder="Rechercher : ventes, Profit, régions…"
                        aria-label="Rechercher dans la mémoire projet"
                      />
                      <button type="submit" disabled={projectMemoryLoading}>⌕</button>
                      {projectMemoryQuery && (
                        <button
                          type="button"
                          title="Effacer la recherche"
                          onClick={() => {
                            setProjectMemoryQuery("");
                            void refreshProjectMemory("");
                          }}
                        >×</button>
                      )}
                    </form>
                    {projectMemoryQuery && (
                      <small className={styles.projectMemorySearchMode}>
                        Recherche sémantique locale · aucun embedding externe
                      </small>
                    )}
                    {projectMemoryLoading ? (
                      <small className={styles.artifactSummary}>Chargement…</small>
                    ) : projectMemoryEntries.length ? (
                      <div className={styles.projectMemoryList}>
                        {projectMemoryEntries.slice(0, 5).map((entry) => (
                          <div className={styles.projectMemoryItem} key={entry.id}>
                            <div>
                              <b>{entry.title || entry.kind || "Résultat"}</b>
                              <small>{entry.summary || "Artefact analytique déterministe"}</small>
                              {typeof entry.search_score === "number" && (
                                <small className={styles.projectMemoryScore}>
                                  Pertinence {Math.round(entry.search_score * 100)} %
                                  {entry.match_reasons?.length ? ` · ${entry.match_reasons.slice(0, 2).join(" · ")}` : ""}
                                </small>
                              )}
                            </div>
                            <div className={styles.projectMemoryActions}>
                              <button type="button" className={styles.memoryActionText} onClick={() => openProjectMemory(entry)} title="Ouvrir dans le module correspondant">Ouvrir</button>
                              <button type="button" className={styles.memoryActionText} onClick={() => replayProjectMemory(entry)} title="Relancer la recette sur son dataset source">Relancer</button>
                              {context.activeDatasetId && (
                                <button type="button" className={styles.memoryActionText} onClick={() => replayProjectMemory(entry, true)} title="Réutiliser cette recette sur le dataset actif">Actif</button>
                              )}
                              {projectMemoryCanManage && adapter.duplicateProjectMemory && (
                                <button type="button" onClick={() => void duplicateProjectMemory(entry)} title="Dupliquer la recette mémoire">⧉</button>
                              )}
                              {projectMemoryCanManage && adapter.pinProjectMemory && (
                                <button type="button" onClick={() => void toggleProjectMemoryPin(entry)} title={entry.pinned ? "Désépingler" : "Épingler"}>
                                  {entry.pinned ? "★" : "☆"}
                                </button>
                              )}
                              {projectMemoryCanManage && adapter.forgetProjectMemory && (
                                <button type="button" onClick={() => void forgetProjectMemory(entry)} title="Oublier cet élément">×</button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <small className={styles.artifactSummary}>Aucun résultat antérieur mémorisé dans ce projet.</small>
                    )}
                    {projectMemoryPolicy && (
                      <small className={styles.artifactSummary}>
                        Rétention {projectMemoryPolicy.retention_days} jours · maximum {projectMemoryPolicy.max_entries} éléments · transcript brut non stocké{projectMemoryCanManage ? "" : " · gestion réservée aux administrateurs"}.
                      </small>
                    )}
                  </div>
                )}
                {lastReference && (
                  <div className={styles.contextWide}>
                    <span>Référence résolue</span>
                    <b>{referenceLabel(lastReference)}</b>
                    <small className={styles.artifactSummary}>
                      {lastReference.model_id ? `model_id ${String(lastReference.model_id)}` : "Contexte de session"}
                      {lastReference.target_stage ? ` · cible ${String(lastReference.target_stage)}` : ""}
                    </small>
                  </div>
                )}
                <small className={styles.contextNote}>
                  Contexte sémantique + mémoire projet gouvernée + rappel local explicable. Aucun transcript brut n’est utilisé comme mémoire longue.
                </small>
              </div>
            )}
          </div>

          {alerts.length > 0 && (
            <div className={styles.alerts}>
              {alerts.map((alert) => (
                <div key={alert.id} className={styles.alertCard}>
                  <div className={styles.alertSeverity}>
                    {alert.severity}
                  </div>
                  <div className={styles.alertTitle}>{alert.title}</div>
                  <div className={styles.alertMessage}>{alert.message}</div>

                  <div className={styles.alertActions}>
                    {alert.action && (
                      <button
                        type="button"
                        onClick={() => void executeAction(alert.action!)}
                        className={styles.darkButton}
                      >
                        {alert.actionLabel ?? alert.action.label}
                      </button>
                    )}
                    <button
                      type="button"
                      className={styles.alertSecondaryButton}
                      onClick={() => {
                        const key = alert.fingerprint ?? alert.id;
                        snoozedAlertsRef.current.set(key, Date.now() + 5 * 60 * 1000);
                        setAlerts((prev) => prev.filter((item) => item.id !== alert.id));
                      }}
                    >
                      5 min
                    </button>
                    <button
                      type="button"
                      className={styles.alertSecondaryButton}
                      onClick={() => setAlerts((prev) => prev.filter((item) => item.id !== alert.id))}
                    >
                      Masquer
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div ref={scrollRef} className={styles.messages}>
            {messages.map((message) => (
              <div
                key={message.id}
                className={
                  message.role === "user"
                    ? `${styles.message} ${styles.userMessage}`
                    : message.role === "system"
                      ? `${styles.message} ${styles.systemMessage}`
                      : `${styles.message} ${styles.assistantMessage}`
                }
              >
                <div className={styles.messageText}>{message.text}</div>

                {getPlanSteps(message.metadata).length > 0 && (
                  <div className={styles.plan}>
                    <div className={styles.planTitle}>Plan DataVision</div>
                    <div className={styles.planSteps}>
                      {getPlanSteps(message.metadata).map((step) => (
                        <div key={step.id} className={styles.planStep}>
                          <span className={styles.planIcon}>
                            {stepStatusIcon(step.status)}
                          </span>
                          <span className={styles.planLabel}>
                            {step.label}
                          </span>
                          <span className={styles.planStatus}>
                            {step.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {!!message.attachments?.length && (
                  <div className={styles.messageAttachments}>
                    {message.attachments.map((file) => (
                      <div key={file.id}>
                        {file.downloadPath ? (
                          <a href={file.downloadPath} className={styles.attachmentLink} download>
                            📎 {file.name}
                          </a>
                        ) : (
                          <>📎 {file.name}</>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {!!message.actions?.length && (
                  <div className={styles.actionCards}>
                    {message.actions.map((action) => (
                      <div key={action.id} className={styles.actionCard}>
                        <div className={styles.actionCardHead}>
                          <span>Action gouvernée</span>
                          <b data-risk={action.risk ?? "read"}>
                            {riskLabel(action.risk)}
                          </b>
                        </div>
                        <strong>{action.label.replace(/^Confirmer\s*:\s*/i, "")}</strong>
                        {action.description && <small>{action.description}</small>}
                        <div className={styles.actionCardButtons}>
                          <button
                            type="button"
                            onClick={() => void executeAction(action)}
                            className={styles.actionButton}
                            disabled={busy}
                          >
                            ✓ Confirmer
                          </button>
                          {action.continuation && adapter.rejectAction && (
                            <button
                              type="button"
                              onClick={() => void rejectAction(action)}
                              className={styles.rejectActionButton}
                              disabled={busy}
                            >
                              Refuser
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {busy && (
              <div className={`${styles.message} ${styles.assistantMessage}`}>
                Analyse en cours…
              </div>
            )}
          </div>

          {!!attachments.length && (
            <div className={styles.pendingAttachments}>
              {attachments.map((file) => (
                <div key={file.id} className={styles.attachmentChip}>
                  📎 {file.name}
                </div>
              ))}
            </div>
          )}

          <footer className={styles.footer}>
            <div className={styles.voiceOptions}>
              <div className={styles.voiceToggles}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={speechEnabled}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setSpeechEnabled(checked);
                      if (!checked) {
                        voice.stopSpeaking();
                      }
                      try {
                        window.localStorage.setItem(
                          "datavision.assistant.tts.enabled",
                          String(checked),
                        );
                      } catch {
                        // Local preference persistence is best-effort only.
                      }
                    }}
                  />
                  Synthèse vocale
                </label>

                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={continuousVoice}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setContinuousVoice(checked);
                      if (!checked) voice.stopListening();
                      try {
                        window.localStorage.setItem("datavision.assistant.voice.continuous", String(checked));
                      } catch {}
                    }}
                  />
                  Conversation continue
                </label>
                <label className={styles.checkboxLabel}>
                  Alertes vocales
                  <select
                    value={voiceAlertMode}
                    onChange={(event) => {
                      const mode = event.target.value as ProactiveVoiceMode;
                      setVoiceAlertMode(mode);
                      try {
                        window.localStorage.setItem("datavision.assistant.voice.proactive_mode", mode);
                      } catch {}
                    }}
                    className={styles.voiceModeSelect}
                  >
                    <option value="off">Off</option>
                    <option value="critical_only">Critiques</option>
                    <option value="important">Critiques + warnings</option>
                    <option value="active">Toutes signalées</option>
                  </select>
                </label>
              </div>

              {voiceState === "speaking" && (
                <button
                  type="button"
                  onClick={() => voice.stopSpeaking()}
                  className={styles.textButton}
                >
                  Arrêter la voix
                </button>
              )}
            </div>

            <div className={styles.composer}>
              <label className={styles.iconButton} title="Ajouter un fichier">
                📎
                <input
                  type="file"
                  multiple
                  className={styles.hiddenInput}
                  onChange={(event) => {
                    if (event.target.files) {
                      void handleFiles(event.target.files);
                    }
                    event.target.value = "";
                  }}
                />
              </label>

              <button
                type="button"
                onClick={toggleListening}
                className={`${styles.iconButton} ${
                  voiceState === "listening" ? styles.listening : ""
                }`}
                title="Parler à DataVision AI"
              >
                🎙️
              </button>

              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder="Écrivez ou parlez à DataVision AI…"
                rows={1}
                className={styles.textarea}
              />

              <button
                type="button"
                disabled={busy || !input.trim()}
                onClick={() => void sendMessage()}
                className={styles.sendButton}
              >
                Envoyer
              </button>
            </div>

            <div className={styles.contextLine}>
              {hasGroundedContext ? "✓ Contexte lié" : "○ Contexte limité"} : {context.screen ?? context.route ?? "application"}
              {context.activeDatasetId
                ? ` · ${String(context.uiState?.datasetName ?? "dataset actif")}`
                : ""}
              {context.selectedEntity?.label
                ? ` · variable ${context.selectedEntity.label}`
                : ""}
            </div>
          </footer>
        </section>
      )}
    </div>
  );
}

function formatContextDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function referenceLabel(reference: Record<string, any>) {
  const intent = String(reference.intent ?? "contexte");
  if (intent === "model_registry" && reference.target_stage) {
    return `Model Registry → ${String(reference.target_stage)}`;
  }
  if (intent === "retraining_check" && reference.create_request) {
    return "Demande de réentraînement";
  }
  if (intent === "monitor_model") return "Monitoring du modèle";
  if (intent === "fairness_analysis") return "Audit d'équité du modèle";
  if (intent === "model_risk") return "Risque du modèle";
  if (intent === "explain_model") return "Explication du modèle";
  if (intent === "artifact_context" && Array.isArray(reference.artifact_ids)) return "Comparaison de résultats";
  if (intent === "artifact_context" && reference.artifact_id) return "Résultat analytique référencé";
  return intent.replace(/_/g, " ");
}

function riskLabel(risk?: AssistantActionProposal["risk"]) {
  if (risk === "destructive") return "Risque élevé";
  if (risk === "external") return "Action externe";
  if (risk === "reversible") return "Réversible";
  return "Lecture";
}

function statusLabel(voiceState: VoiceState, busy: boolean) {
  if (busy) return "Analyse…";
  if (voiceState === "listening") return "Écoute…";
  if (voiceState === "speaking") return "Parle…";
  if (voiceState === "requesting_permission") {
    return "Autorisation microphone…";
  }
  if (voiceState === "unsupported") {
    return "Voix navigateur non disponible";
  }
  if (voiceState === "error") return "Erreur vocale";
  return "Prêt";
}

function shouldSpeakAlert(
  alert: ProactiveAlert,
  mode: ProactiveVoiceMode,
) {
  if (mode === "off") return false;
  if (mode === "critical_only") {
    return alert.severity === "critical";
  }
  if (mode === "important") {
    return (
      alert.severity === "critical" ||
      alert.severity === "warning"
    );
  }
  return alert.speak;
}

function stepStatusIcon(status: string) {
  if (status === "succeeded") return "✓";
  if (status === "failed") return "✕";
  if (status === "waiting_confirmation") return "!";
  if (status === "running") return "…";
  if (status === "skipped") return "–";
  return "○";
}

type PlanStepView = {
  id: string;
  label: string;
  status: string;
};

function getPlanSteps(
  metadata?: Record<string, unknown>,
): PlanStepView[] {
  const steps = metadata?.steps;
  if (!Array.isArray(steps)) return [];

  return steps.filter((step): step is PlanStepView => {
    if (!step || typeof step !== "object") return false;
    const value = step as Record<string, unknown>;
    return (
      typeof value.id === "string" &&
      typeof value.label === "string" &&
      typeof value.status === "string"
    );
  });
}
