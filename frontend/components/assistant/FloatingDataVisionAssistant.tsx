"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type {
  AssistantAdapter,
  AssistantActionProposal,
  AssistantAttachment,
  ProactiveAlert,
} from "@/lib/assistant/adapter";
import {
  assistantEventBus,
  type AssistantContextSnapshot,
} from "@/lib/assistant/event-bus";
import {
  BrowserVoiceController,
  type VoiceState,
} from "@/lib/assistant/voice";

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
    // locale intentionally rebuilds the voice controller
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

        const mostImportant = newAlerts.find((a) => a.severity === "critical") ?? newAlerts[0];
        if (shouldSpeakAlert(mostImportant, proactiveVoiceMode)) {
          voice.speak(`${mostImportant.title}. ${mostImportant.message}`, {
            language: locale,
          });
        }
      } catch {
        // Observation is best-effort and must never break the host UI.
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
        voice.speak(response.message, { language: locale });
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
          text: "Le connecteur d'upload doit être raccordé à l'endpoint de fichiers existant de DataVision.",
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
          text:
            "Cette action doit être raccordée au moteur d'actions gouverné de DataVision.",
        },
      ]);
      return;
    }

    const sensitive = action.risk === "destructive" || action.risk === "external";
    if (sensitive) {
      const accepted = window.confirm(
        `Confirmer l'action : ${action.label}\n\n${action.description ?? ""}`,
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
        voice.speak(response.message, { language: locale });
      }
    } finally {
      setBusy(false);
    }
  }

  function toggleListening() {
    if (voiceState === "listening" || voiceState === "requesting_permission") {
      voice.stopListening();
      return;
    }
    voice.listen({ continuous: continuousVoice });
  }

  return (
    <>
      <button
        type="button"
        aria-label="Ouvrir DataVision AI"
        onClick={() => setOpen((value) => !value)}
        className="fixed bottom-6 right-6 z-[100] flex h-14 w-14 items-center justify-center rounded-full bg-slate-950 text-white shadow-2xl ring-1 ring-white/10 transition hover:scale-105"
      >
        <span className="text-lg font-semibold">AI</span>
        {alerts.some((a) => a.severity === "critical") && (
          <span className="absolute -right-1 -top-1 h-4 w-4 rounded-full bg-red-500 ring-2 ring-white" />
        )}
      </button>

      {open && (
        <section className="fixed bottom-24 right-6 z-[99] flex h-[min(720px,78vh)] w-[min(440px,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
          <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <div>
              <div className="font-semibold text-slate-950">DataVision AI</div>
              <div className="text-xs text-slate-500">
                {statusLabel(voiceState, busy)}
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                voice.stopSpeaking();
                setOpen(false);
              }}
              className="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100"
            >
              ✕
            </button>
          </header>

          {alerts.length > 0 && (
            <div className="max-h-36 space-y-2 overflow-y-auto border-b border-slate-200 bg-slate-50 p-3">
              {alerts.map((alert) => (
                <div key={alert.id} className="rounded-xl border bg-white p-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {alert.severity}
                  </div>
                  <div className="mt-1 text-sm font-semibold">{alert.title}</div>
                  <div className="mt-1 text-sm text-slate-600">{alert.message}</div>
                  {alert.action && (
                    <button
                      type="button"
                      onClick={() => void executeAction(alert.action!)}
                      className="mt-2 rounded-lg bg-slate-950 px-3 py-1.5 text-xs font-medium text-white"
                    >
                      {alert.actionLabel ?? alert.action.label}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={
                  message.role === "user"
                    ? "ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-slate-950 px-3 py-2 text-sm text-white"
                    : message.role === "system"
                      ? "max-w-[92%] rounded-2xl bg-amber-50 px-3 py-2 text-sm text-amber-900"
                      : "max-w-[92%] rounded-2xl rounded-bl-md bg-slate-100 px-3 py-2 text-sm text-slate-900"
                }
              >
                <div className="whitespace-pre-wrap">{message.text}</div>
                {Array.isArray(message.metadata?.steps) && (
                  <div className="mt-3 rounded-xl border border-slate-200 bg-white/70 p-2">
                    <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                      Plan DataVision
                    </div>
                    <div className="space-y-1">
                      {(message.metadata.steps as Array<any>).map((step) => (
                        <div key={step.id} className="flex items-center gap-2 text-xs">
                          <span>{stepStatusIcon(step.status)}</span>
                          <span className="min-w-0 flex-1 truncate">{step.label}</span>
                          <span className="text-[10px] text-slate-400">{step.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {!!message.attachments?.length && (
                  <div className="mt-2 space-y-1 text-xs opacity-80">
                    {message.attachments.map((file) => (
                      <div key={file.id}>📎 {file.name}</div>
                    ))}
                  </div>
                )}
                {!!message.actions?.length && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {message.actions.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        onClick={() => void executeAction(action)}
                        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-900"
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && (
              <div className="max-w-[92%] rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-600">
                Analyse en cours…
              </div>
            )}
          </div>

          {!!attachments.length && (
            <div className="flex gap-2 overflow-x-auto border-t border-slate-200 px-3 py-2">
              {attachments.map((file) => (
                <div
                  key={file.id}
                  className="whitespace-nowrap rounded-full bg-slate-100 px-3 py-1 text-xs"
                >
                  📎 {file.name}
                </div>
              ))}
            </div>
          )}

          <div className="border-t border-slate-200 p-3">
            <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
              <label className="flex items-center gap-2">
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
                className="hover:text-slate-950"
              >
                Arrêter la voix
              </button>
            </div>

            <div className="flex items-end gap-2">
              <label className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-slate-200 hover:bg-slate-50">
                📎
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(event) => {
                    if (event.target.files) void handleFiles(event.target.files);
                    event.target.value = "";
                  }}
                />
              </label>

              <button
                type="button"
                onClick={toggleListening}
                className={
                  voiceState === "listening"
                    ? "flex h-10 w-10 items-center justify-center rounded-xl bg-red-500 text-white"
                    : "flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 hover:bg-slate-50"
                }
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
                className="max-h-28 min-h-10 flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
              />

              <button
                type="button"
                disabled={busy || !input.trim()}
                onClick={() => void sendMessage()}
                className="h-10 rounded-xl bg-slate-950 px-3 text-sm font-medium text-white disabled:opacity-40"
              >
                Envoyer
              </button>
            </div>

            <div className="mt-2 truncate text-[11px] text-slate-400">
              Contexte : {context.screen ?? context.route ?? "application"}
              {context.activeDatasetId ? ` · dataset ${context.activeDatasetId}` : ""}
            </div>
          </div>
        </section>
      )}
    </>
  );
}

function statusLabel(voiceState: VoiceState, busy: boolean) {
  if (busy) return "Analyse…";
  if (voiceState === "listening") return "Écoute…";
  if (voiceState === "speaking") return "Parle…";
  if (voiceState === "requesting_permission") return "Autorisation microphone…";
  if (voiceState === "unsupported") return "Voix navigateur non disponible";
  if (voiceState === "error") return "Erreur vocale";
  return "Prêt";
}

function shouldSpeakAlert(alert: ProactiveAlert, mode: ProactiveVoiceMode) {
  if (mode === "off") return false;
  if (mode === "critical_only") return alert.severity === "critical";
  if (mode === "important") {
    return alert.severity === "critical" || alert.severity === "warning";
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
