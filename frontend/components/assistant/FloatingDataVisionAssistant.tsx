"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type {
  AssistantAdapter,
  AssistantActionProposal,
  AssistantAttachment,
  ProactiveAlert,
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
  const [context, setContext] = useState<AssistantContextSnapshot>(
    assistantEventBus.getContext(),
  );
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
    const offContext = assistantEventBus.onContext(setContext);
    const offEvent = assistantEventBus.onEvent(async (event, currentContext) => {
      try {
        const newAlerts = await adapter.observe({
          event,
          context: currentContext,
        });
        if (!newAlerts.length) return;

        setAlerts((prev) => [...newAlerts, ...prev].slice(0, 5));

        const mostImportant =
          newAlerts.find((a) => a.severity === "critical") ?? newAlerts[0];

        if (shouldSpeakAlert(mostImportant, proactiveVoiceMode)) {
          voice.speak(toSpeechText(`${mostImportant.title}. ${mostImportant.message}`), {
            language: locale,
          });
        }
      } catch {
        // Best-effort only: the host UI must remain usable.
      }
    });

    return () => {
      offContext();
      offEvent();
      voice.destroy();
    };
  }, [adapter, locale, proactiveVoiceMode, voice]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, busy]);

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
      const response = await adapter.sendMessage({
        message: text,
        context,
        attachmentIds: attachments.map((item) => item.id),
      });

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

      if (response.speak !== false) {
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

    if (sensitive) {
      const accepted = window.confirm(
        `DataVision demande votre confirmation.\n\n${action.label}\n\n${action.description ?? ""}\n\nL'action sera contrôlée à nouveau côté serveur avant exécution.`,
      );
      if (!accepted) return;
    }

    setBusy(true);
    try {
      const response = await adapter.executeAction(action, context);
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

      if (response.speak !== false) {
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
                  {statusLabel(voiceState, busy)}
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

          {alerts.length > 0 && (
            <div className={styles.alerts}>
              {alerts.map((alert) => (
                <div key={alert.id} className={styles.alertCard}>
                  <div className={styles.alertSeverity}>
                    {alert.severity}
                  </div>
                  <div className={styles.alertTitle}>{alert.title}</div>
                  <div className={styles.alertMessage}>{alert.message}</div>

                  {alert.action && (
                    <button
                      type="button"
                      onClick={() => void executeAction(alert.action!)}
                      className={styles.darkButton}
                    >
                      {alert.actionLabel ?? alert.action.label}
                    </button>
                  )}
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
                      <div key={file.id}>📎 {file.name}</div>
                    ))}
                  </div>
                )}

                {!!message.actions?.length && (
                  <div className={styles.actionRow}>
                    {message.actions.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        onClick={() => void executeAction(action)}
                        className={styles.actionButton}
                      >
                        {action.label}
                      </button>
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
              <label className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={continuousVoice}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setContinuousVoice(checked);
                    if (!checked) voice.stopListening();
                  }}
                />
                Conversation continue
              </label>

              <button
                type="button"
                onClick={() => voice.stopSpeaking()}
                className={styles.textButton}
              >
                Arrêter la voix
              </button>
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
              Contexte : {context.screen ?? context.route ?? "application"}
              {context.activeDatasetId
                ? ` · dataset ${context.activeDatasetId}`
                : ""}
            </div>
          </footer>
        </section>
      )}
    </div>
  );
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
