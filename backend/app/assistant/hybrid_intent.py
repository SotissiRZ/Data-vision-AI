from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .model_gateway import ModelGateway, ModelRequest, RoutingPolicy
from .models import AgentIntent, AssistantContext
from .privacy import AIDataPolicy, project_context_for_model


ALLOWED_INTENTS = [
    "analyze_dataset", "data_quality", "compare_groups", "visualize",
    "predict_target", "explain_model", "root_cause_analysis", "optimize_scenarios", "geospatial_analysis", "report",
    "file_analysis", "show_results", "dataset_assessment", "capabilities", "conversation", "unknown",
]

HybridIntentName = Literal[
    "analyze_dataset",
    "data_quality",
    "compare_groups",
    "visualize",
    "predict_target",
    "explain_model",
    "root_cause_analysis",
    "optimize_scenarios",
    "geospatial_analysis",
    "report",
    "file_analysis",
    "show_results",
    "dataset_assessment",
    "capabilities",
    "conversation",
    "unknown",
]


class IntentDecisionPayload(BaseModel):
    intent: HybridIntentName
    confidence: float = Field(ge=0, le=1)
    entities: dict = Field(default_factory=dict)
    rationale: str | None = None


@dataclass
class GatewayIntentResolver:
    gateway: ModelGateway
    routing_policy: RoutingPolicy
    data_policy: AIDataPolicy
    minimum_confidence: float = 0.68

    def resolve(
        self,
        *,
        message: str,
        context: AssistantContext,
        current: AgentIntent,
    ) -> AgentIntent:
        probe = ModelRequest(
            task="planner",
            system="",
            user="",
            response_schema=IntentDecisionPayload.model_json_schema(),
            temperature=0.0,
            max_output_tokens=300,
        )
        candidates = self.gateway.candidate_providers(
            request=probe,
            policy=self.routing_policy,
        )
        if not candidates:
            return current

        external = any(
            provider.descriptor.kind != "local"
            for provider in candidates
        )
        if external and not self.data_policy.allow_external_ai:
            return current

        semantic_context = project_context_for_model(
            context,
            external=external,
            policy=self.data_policy,
        )

        request = ModelRequest(
            task="planner",
            system=(
                "Vous êtes le routeur d'intention de DataVision AI. "
                "Votre unique tâche est de classifier la demande utilisateur. "
                "N'exécutez rien, ne calculez rien et n'inventez aucune colonne. "
                "Utilisez uniquement l'une des intentions autorisées. "
                "Si la demande n'est pas suffisamment claire, choisissez unknown. "
                "conversation convient aux questions explicatives ou conversationnelles "
                "qui ne nécessitent pas l'exécution d'un outil. "
                "show_results convient aux demandes portant sur les résultats déjà calculés."
            ),
            user=json.dumps(
                {
                    "message": message,
                    "current_deterministic_intent": current.model_dump(mode="json"),
                    "context": semantic_context,
                    "allowed_intents": ALLOWED_INTENTS,
                },
                ensure_ascii=False,
            ),
            response_schema=IntentDecisionPayload.model_json_schema(),
            temperature=0.0,
            max_output_tokens=300,
        )

        response = self.gateway.generate(
            request,
            policy=self.routing_policy,
        )

        try:
            decision = IntentDecisionPayload.model_validate_json(response.text)
        except ValidationError:
            return current

        if decision.confidence < self.minimum_confidence:
            return current

        return AgentIntent(
            name=decision.intent,
            confidence=decision.confidence,
            entities=decision.entities,
            rationale=decision.rationale or "Classification hybride par Model Gateway.",
        )
