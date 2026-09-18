"use client";

import { useEffect } from "react";
import {
  assistantEventBus,
  type AssistantSeverity,
  type SelectedEntity,
} from "./event-bus";

export function useAssistantScreenContext(input: {
  workspaceId?: string;
  organizationId?: string;
  route?: string;
  screen: string;
  activeDatasetId?: string;
  activeDatasetVersionId?: string;
  activeModelId?: string;
  activeChartId?: string;
  activeReportId?: string;
}) {
  useEffect(() => {
    assistantEventBus.setContext(input);
    assistantEventBus.emit({
      type: "screen.entered",
      severity: "info",
      payload: { screen: input.screen, route: input.route },
    });

    return () => {
      assistantEventBus.emit({
        type: "screen.left",
        severity: "info",
        payload: { screen: input.screen, route: input.route },
      });
    };
  }, [
    input.workspaceId,
    input.organizationId,
    input.route,
    input.screen,
    input.activeDatasetId,
    input.activeDatasetVersionId,
    input.activeModelId,
    input.activeChartId,
    input.activeReportId,
  ]);
}

export function setAssistantSelection(entity: SelectedEntity | null) {
  assistantEventBus.setContext({ selectedEntity: entity });
  assistantEventBus.emit({
    type: entity ? "selection.changed" : "selection.cleared",
    severity: "info",
    payload: entity ? { entity } : {},
  });
}

export function reportAssistantEvent(
  type: string,
  payload?: Record<string, unknown>,
  severity: AssistantSeverity = "info",
) {
  assistantEventBus.emit({
    type,
    severity,
    payload,
  });
}

export const DataVisionAgentEvents = {
  DATASET_LOADED: "dataset.loaded",
  DATASET_SELECTED: "dataset.selected",
  DATASET_QUALITY_ISSUE: "dataset.quality.issue",
  COLUMN_SELECTED: "column.selected",
  TRANSFORM_PREVIEWED: "transform.previewed",
  TRANSFORM_APPLIED: "transform.applied",
  TRANSFORM_FAILED: "transform.failed",
  VISUALIZATION_CREATED: "visualization.created",
  VISUALIZATION_ERROR: "visualization.error",
  ANALYSIS_STARTED: "analysis.started",
  ANALYSIS_COMPLETED: "analysis.completed",
  ANALYSIS_FAILED: "analysis.failed",
  QUERY_FAILED: "query.failed",
  ML_TRAINING_STARTED: "ml.training.started",
  ML_TRAINING_COMPLETED: "ml.training.completed",
  ML_TRAINING_FAILED: "ml.training.failed",
  ML_LEAKAGE_DETECTED: "ml.leakage.detected",
  REPORT_GENERATED: "report.generated",
  FILE_UPLOADED: "file.uploaded",
  JOB_RETRIED: "job.retried",
} as const;
