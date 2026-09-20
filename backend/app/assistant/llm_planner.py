from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from .contracts import tool_json_schema
from .model_gateway import ModelGateway, ModelRequest, RoutingPolicy
from .models import AgentIntent, AgentPlanStep, AssistantContext
from .planner_runtime import PlannerProvider
from .privacy import AIDataPolicy, project_context_for_model
from .tools import AssistantToolRegistry


class PlannedStepPayload(BaseModel):
    tool: str
    label: str
    reason: str | None = None
    args: dict = Field(default_factory=dict)


class PlannerPayload(BaseModel):
    steps: list[PlannedStepPayload] = Field(default_factory=list)


@dataclass
class GatewayPlannerProvider(PlannerProvider):
    gateway: ModelGateway
    registry: AssistantToolRegistry
    routing_policy: RoutingPolicy
    data_policy: AIDataPolicy = AIDataPolicy()

    def plan(
        self,
        *,
        message: str,
        intent: AgentIntent,
        context: AssistantContext,
        attachment_ids: list[str],
    ) -> list[AgentPlanStep]:
        probe = ModelRequest(
            task="planner",
            system="",
            user="",
            response_schema=PlannerPayload.model_json_schema(),
            temperature=0.0,
        )
        candidates = self.gateway.candidate_providers(
            request=probe,
            policy=self.routing_policy,
        )
        if not candidates:
            from .model_gateway import NoEligibleProvider
            raise NoEligibleProvider(
                "Aucun provider compatible avec la politique du planner."
            )

        # Conservative projection: if any authorized fallback could be external,
        # prepare an external-safe context before the first call.
        external = any(
            provider.descriptor.kind != "local"
            for provider in candidates
        )

        if external and not self.data_policy.allow_external_ai:
            raise PermissionError(
                "La politique DataVision interdit l'envoi de contexte à un provider externe."
            )

        catalog = []
        for spec in self.registry.list_for_context(context, executable_only=True):
            catalog.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "category": spec.category,
                    "risk": spec.risk,
                    "requires_dataset": spec.requires_dataset,
                    "requires_model": spec.requires_model,
                    "input_schema": spec.input_schema or tool_json_schema(spec.name),
                }
            )

        semantic_context = project_context_for_model(
            context,
            external=external,
            policy=self.data_policy,
        )

        system = (
            "Vous êtes le planner de DataVision AI. "
            "Vous ne calculez aucune statistique et vous n'exécutez rien. "
            "Vous construisez uniquement un plan utilisant les outils fournis. "
            "N'inventez jamais de colonne, cible, couche, fichier ou modèle absent du contexte. "
            "Si les informations sont insuffisantes, retournez une liste steps vide. "
            "Les opérations destructives ne doivent jamais être déguisées en opérations sûres."
        )

        user_payload = {
            "message": message,
            "intent": intent.model_dump(mode="json"),
            "context": semantic_context,
            "attachment_ids": attachment_ids,
            "tools": catalog,
        }

        request = ModelRequest(
            task="planner",
            system=system,
            user=json.dumps(user_payload, ensure_ascii=False),
            response_schema=PlannerPayload.model_json_schema(),
            temperature=0.0,
            max_output_tokens=3000,
        )

        response = self.gateway.generate(
            request,
            policy=self.routing_policy,
        )

        try:
            parsed = PlannerPayload.model_validate_json(response.text)
        except ValidationError as exc:
            raise ValueError(f"Plan LLM non conforme au schéma: {exc}") from exc

        steps: list[AgentPlanStep] = []
        for item in parsed.steps:
            if self.registry.get(item.tool) is None or not self.registry.has_handler(item.tool):
                continue
            steps.append(
                AgentPlanStep(
                    tool=item.tool,
                    label=item.label,
                    reason=item.reason,
                    args=item.args,
                )
            )

        return steps
