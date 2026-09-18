export type AssistantSeverity = "info" | "suggestion" | "warning" | "critical";

export type SelectedEntity = {
  type: string;
  id?: string;
  label?: string;
  metadata?: Record<string, unknown>;
};

export type AssistantContextSnapshot = {
  workspaceId?: string;
  organizationId?: string;
  route?: string;
  screen?: string;
  activeDatasetId?: string;
  activeDatasetVersionId?: string;
  activeModelId?: string;
  activeChartId?: string;
  activeReportId?: string;
  selectedEntity?: SelectedEntity | null;
  recentEvents: AssistantEvent[];
  uiState?: Record<string, unknown>;
};

export type AssistantEvent = {
  id?: string;
  type: string;
  severity?: AssistantSeverity;
  timestamp?: string;
  payload?: Record<string, unknown>;
};

type EventListener = (event: AssistantEvent, context: AssistantContextSnapshot) => void;
type ContextListener = (context: AssistantContextSnapshot) => void;

class AssistantEventBus {
  private context: AssistantContextSnapshot = { recentEvents: [] };
  private eventListeners = new Set<EventListener>();
  private contextListeners = new Set<ContextListener>();
  private maxEvents = 25;

  getContext(): AssistantContextSnapshot {
    return {
      ...this.context,
      recentEvents: [...this.context.recentEvents],
    };
  }

  setContext(patch: Partial<Omit<AssistantContextSnapshot, "recentEvents">>) {
    this.context = { ...this.context, ...patch };
    const snapshot = this.getContext();
    this.contextListeners.forEach((listener) => listener(snapshot));
  }

  emit(input: AssistantEvent) {
    const event: AssistantEvent = {
      ...input,
      id: input.id ?? crypto.randomUUID(),
      timestamp: input.timestamp ?? new Date().toISOString(),
      severity: input.severity ?? "info",
    };

    this.context = {
      ...this.context,
      recentEvents: [...this.context.recentEvents, event].slice(-this.maxEvents),
    };

    const snapshot = this.getContext();
    this.eventListeners.forEach((listener) => listener(event, snapshot));
    this.contextListeners.forEach((listener) => listener(snapshot));
  }

  onEvent(listener: EventListener) {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  onContext(listener: ContextListener) {
    this.contextListeners.add(listener);
    return () => this.contextListeners.delete(listener);
  }

  clearTransientContext() {
    this.context = {
      ...this.context,
      selectedEntity: null,
      uiState: undefined,
      recentEvents: [],
    };
    const snapshot = this.getContext();
    this.contextListeners.forEach((listener) => listener(snapshot));
  }
}

export const assistantEventBus = new AssistantEventBus();
