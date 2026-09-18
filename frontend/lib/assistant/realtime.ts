export type AssistantRealtimeEvent = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
};

export class AssistantRealtimeClient {
  private source: EventSource | null = null;

  connect(options: {
    apiBaseUrl: string;
    workspaceId?: string;
    onEvent: (event: AssistantRealtimeEvent) => void;
    onConnection?: (connected: boolean) => void;
  }) {
    this.disconnect();

    const base = options.apiBaseUrl.replace(/\/$/, "");
    const query = options.workspaceId
      ? `?workspace_id=${encodeURIComponent(options.workspaceId)}`
      : "";
    const source = new EventSource(`${base}/ai/assistant/events${query}`, {
      withCredentials: true,
    });

    source.onopen = () => options.onConnection?.(true);
    source.onerror = () => options.onConnection?.(false);

    const eventTypes = [
      "assistant.action",
      "assistant.alert",
      "assistant.message",
      "assistant.speaking",
    ];

    for (const type of eventTypes) {
      source.addEventListener(type, (raw) => {
        const message = raw as MessageEvent;
        try {
          const data = JSON.parse(message.data) as AssistantRealtimeEvent;
          options.onEvent(data);
        } catch {
          // malformed realtime events are ignored rather than breaking the UI
        }
      });
    }

    this.source = source;
  }

  disconnect() {
    this.source?.close();
    this.source = null;
  }
}
