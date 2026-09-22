import type { AssistantChatResponse } from "./adapter";
import { assistantEventBus, type AssistantContextSnapshot } from "./event-bus";

type StepResult = {
  tool?: string;
  status?: string;
  result?: Record<string, unknown> | null;
};

const DATASET_MUTATION_TOOLS = new Set([
  "apply_reversible_transform",
  "merge_datasets",
  "delete_column",
]);

const MODEL_CREATION_TOOLS = new Set([
  "run_regression",
  "run_automl",
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function responseSteps(response: AssistantChatResponse): StepResult[] {
  const raw = response.metadata?.steps;
  if (!Array.isArray(raw)) return [];
  return raw.filter(isObject) as StepResult[];
}

export function applyAssistantHostEffects(
  response: AssistantChatResponse,
  fallbackContext?: AssistantContextSnapshot,
) {
  if (typeof window === "undefined") return;

  const context = assistantEventBus.getContext();
  const current = context.screen ? context : (fallbackContext ?? context);
  const steps = responseSteps(response).filter((step) => step.status === "succeeded");
  if (!steps.length) return;

  let datasetId: string | undefined;
  let datasetVersion: string | undefined;
  let modelId: string | undefined;
  let chartId: string | undefined;
  let reportId: string | undefined;
  let preferredView: string | undefined;
  let forceDatasetReload = false;

  for (const step of steps) {
    if (!isObject(step.result)) continue;
    const result = step.result;
    const tool = String(step.tool ?? "");

    if (DATASET_MUTATION_TOOLS.has(tool) && typeof result.dataset_id === "string") {
      datasetId = result.dataset_id;
      datasetVersion = result.version == null ? undefined : String(result.version);
      preferredView = current.screen || "prepare";
      forceDatasetReload = true;
    }

    if (MODEL_CREATION_TOOLS.has(tool) && typeof result.model_id === "string") {
      modelId = result.model_id;
      preferredView = "model";
    }

    if (tool === "transition_model_stage" && current.activeModelId) {
      modelId = current.activeModelId;
      preferredView = "registry";
    }

    if (tool === "generate_report" && typeof result.report_id === "string") {
      reportId = result.report_id;
      preferredView = "report";
    }

    if (tool === "create_visualization") {
      if (typeof result.chart_id === "string") chartId = result.chart_id;
      else if (typeof result.visualization_id === "string") chartId = result.visualization_id;
      preferredView = "visual";
    }

    if (tool === "execute_notebook_cell") {
      preferredView = "notebook";
    }
  }

  if (datasetId) {
    assistantEventBus.setContext({
      activeDatasetId: datasetId,
      activeDatasetVersionId: datasetVersion,
    });
    assistantEventBus.emit({
      type: "assistant.dataset.changed",
      severity: "info",
      payload: { datasetId, datasetVersion },
    });
  }

  if (modelId) {
    assistantEventBus.setContext({ activeModelId: modelId });
    assistantEventBus.emit({
      type: "assistant.model.changed",
      severity: "info",
      payload: { modelId },
    });
  }

  if (chartId) {
    assistantEventBus.setContext({ activeChartId: chartId });
    assistantEventBus.emit({
      type: "assistant.chart.changed",
      severity: "info",
      payload: { chartId },
    });
  }

  if (reportId) {
    assistantEventBus.setContext({ activeReportId: reportId });
    assistantEventBus.emit({
      type: "assistant.report.changed",
      severity: "info",
      payload: { reportId },
    });
  }

  if (datasetId || modelId || chartId || reportId || preferredView) {
    window.dispatchEvent(
      new CustomEvent("datavision:assistant-navigate", {
        detail: {
          view: preferredView ?? current.screen ?? "home",
          datasetId,
          datasetVersion,
          modelId,
          chartId,
          reportId,
          refreshDataset: forceDatasetReload,
          source: "assistant-action",
        },
      }),
    );
  }
}
