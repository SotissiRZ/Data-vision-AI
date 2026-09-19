from __future__ import annotations

import json
from dataclasses import dataclass

from .ai_settings import (
    build_model_gateway_for_scope,
    get_ai_settings,
    routing_policy_for_settings,
    scope_for_context,
)
from .model_gateway import ModelRequest
from .models import AssistantContext
from .privacy import AIDataPolicy, project_context_for_model
from .result_composer import compose_run_results
from .turn_runs import AgentTurnRunStore
from .artifact_memory import project_artifacts_for_model


@dataclass
class SettingsAwareConversationEngine:
    turn_store: AgentTurnRunStore

    def answer(
        self,
        *,
        session_id: str,
        message: str,
        context: AssistantContext,
    ) -> str | None:
        try:
            scope_type, scope_id, actor_id = scope_for_context(
                context.workspaceId
            )
            settings = get_ai_settings(scope_type, scope_id)
            if settings.planner_mode != "gateway":
                return None

            gateway = build_model_gateway_for_scope(
                scope_type,
                scope_id,
                actor_id=actor_id,
            )
            routing = routing_policy_for_settings(
                settings,
                task="explanation",
            )

            probe = ModelRequest(
                task="explanation",
                system="",
                user="",
                max_output_tokens=800,
            )
            candidates = gateway.candidate_providers(
                request=probe,
                policy=routing,
            )
            if not candidates:
                return None

            external = any(
                provider.descriptor.kind != "local"
                for provider in candidates
            )
            data_policy = AIDataPolicy(
                allow_external_ai=settings.allow_external_ai,
                include_column_names_external=(
                    settings.external_data_policy.include_column_names
                ),
                include_sample_values_external=False,
                include_row_data_external=False,
                max_recent_events_external=(
                    settings.external_data_policy.max_recent_events
                ),
            )
            if external and not data_policy.allow_external_ai:
                return None

            semantic_context = project_context_for_model(
                context,
                external=external,
                policy=data_policy,
            )

            latest = self.turn_store.latest_for_session(
                session_id,
                statuses={"completed", "partial"},
            )
            last_results = (
                compose_run_results(latest)
                if latest is not None
                else "Aucun résultat analytique antérieur dans cette session."
            )

            memory_artifacts = []
            try:
                # The orchestrator persists compact artifact memory in metadata;
                # grounded LLM answers receive only these governed summaries.
                from .persistent_memory import PersistentSessionMemoryStore
                memory_artifacts = project_artifacts_for_model(
                    PersistentSessionMemoryStore().get_or_create(session_id, context.workspaceId),
                    external=external,
                    include_column_names_external=data_policy.include_column_names_external,
                )
            except Exception:
                memory_artifacts = []

            request = ModelRequest(
                task="explanation",
                system=(
                    "Vous êtes DataVision AI, assistant d'analyse de données. "
                    "Répondez en français de manière concise, utile et techniquement correcte. "
                    "Pour toute affirmation spécifique au dataset, utilisez uniquement le contexte "
                    "ou les résultats déterministes fournis. "
                    "N'inventez jamais une statistique, une colonne, une métrique, un modèle ou un résultat. "
                    "Si l'information requise n'est pas disponible, dites-le clairement et proposez "
                    "l'analyse DataVision appropriée. "
                    "Vous n'avez pas de navigateur Web général dans ce produit."
                ),
                user=json.dumps(
                    {
                        "question": message,
                        "context": semantic_context,
                        "last_deterministic_results": last_results,
                        "recent_analytical_artifacts": memory_artifacts,
                    },
                    ensure_ascii=False,
                ),
                temperature=0.15,
                max_output_tokens=800,
            )
            response = gateway.generate(
                request,
                policy=routing,
            )
            answer = response.text.strip()
            return answer or None
        except Exception:
            return None
