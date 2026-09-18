"use client";

import { useMemo } from "react";

import { FloatingDataVisionAssistant } from "./FloatingDataVisionAssistant";
import { createOrchestratorAssistantAdapter } from "@/lib/assistant/orchestrator-adapter";

export function DataVisionAssistantRoot() {
  const adapter = useMemo(
    () =>
      createOrchestratorAssistantAdapter({
        apiBaseUrl:
          process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8005",
        // Replace with the real DataVision upload endpoint during host integration.
        uploadPath: process.env.NEXT_PUBLIC_ASSISTANT_UPLOAD_PATH || undefined,
      }),
    [],
  );

  return (
    <FloatingDataVisionAssistant
      adapter={adapter}
      locale="fr-FR"
      proactiveVoiceMode="critical_only"
    />
  );
}
