from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

ProviderKind = Literal["local", "cloud", "openai_compatible"]
PrivacyMode = Literal["local_only", "prefer_local", "allow_external"]
TaskKind = Literal["planner", "explanation", "critic", "summarization"]


class ModelRequest(BaseModel):
    task: TaskKind
    system: str
    user: str
    response_schema: dict[str, Any] | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_output_tokens: int = Field(default=2000, ge=1, le=64000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class ModelResponse(BaseModel):
    text: str
    provider_id: str
    model: str
    usage: ModelUsage = Field(default_factory=ModelUsage)
    raw: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCapabilities:
    structured_output: bool = False
    tools: bool = False
    streaming: bool = False
    max_context_tokens: int | None = None


@dataclass
class ProviderDescriptor:
    id: str
    kind: ProviderKind
    model: str
    enabled: bool = True
    priority: int = 100
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    descriptor: ProviderDescriptor

    def generate(self, request: ModelRequest) -> ModelResponse:
        ...


class ModelGatewayError(RuntimeError):
    pass


class NoEligibleProvider(ModelGatewayError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        provider_id = provider.descriptor.id
        if provider_id in self._providers:
            raise ValueError(f"Provider déjà enregistré : {provider_id}")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> ModelProvider | None:
        return self._providers.get(provider_id)

    def list(self) -> list[ModelProvider]:
        return sorted(
            self._providers.values(),
            key=lambda p: (p.descriptor.priority, p.descriptor.id),
        )


@dataclass(frozen=True)
class RoutingPolicy:
    privacy_mode: PrivacyMode = "local_only"
    allow_external_ai: bool = False
    require_structured_output: bool = True
    preferred_provider_id: str | None = None
    fallback_provider_ids: tuple[str, ...] = ()
    allow_fallback: bool = True


class ModelGateway:
    """
    Provider-agnostic gateway with explicit privacy routing and ordered fallback.

    Provider selection never grants tool permissions. It only chooses which
    model may plan/explain. DataVision's Tool Registry/RBAC/RLS remains
    authoritative for every application action.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        provider_guard: Callable[[ModelProvider, ModelRequest], None] | None = None,
        response_hook: Callable[[ModelProvider, ModelRequest, ModelResponse], None] | None = None,
    ) -> None:
        self.registry = registry
        self.provider_guard = provider_guard
        self.response_hook = response_hook

    def candidate_providers(
        self,
        *,
        request: ModelRequest,
        policy: RoutingPolicy,
    ) -> list[ModelProvider]:
        providers = [p for p in self.registry.list() if p.descriptor.enabled]
        by_id = {p.descriptor.id: p for p in providers}

        ordered: list[ModelProvider] = []
        seen: set[str] = set()

        def push(provider_id: str | None) -> None:
            if not provider_id or provider_id in seen:
                return
            provider = by_id.get(provider_id)
            if provider is not None:
                ordered.append(provider)
                seen.add(provider_id)

        push(policy.preferred_provider_id)
        for provider_id in policy.fallback_provider_ids:
            push(provider_id)
        for provider in providers:
            push(provider.descriptor.id)

        eligible: list[ModelProvider] = []
        for provider in ordered:
            d = provider.descriptor

            if policy.require_structured_output and request.response_schema is not None:
                if not d.capabilities.structured_output:
                    continue

            if policy.privacy_mode == "local_only" and d.kind != "local":
                continue

            if d.kind != "local" and not policy.allow_external_ai:
                continue

            eligible.append(provider)

        if policy.privacy_mode == "prefer_local":
            preferred = policy.preferred_provider_id
            fallback_rank = {
                provider_id: index
                for index, provider_id in enumerate(policy.fallback_provider_ids)
            }
            eligible.sort(
                key=lambda p: (
                    0 if p.descriptor.id == preferred else 1,
                    0 if p.descriptor.kind == "local" else 1,
                    fallback_rank.get(p.descriptor.id, 10_000),
                    p.descriptor.priority,
                    p.descriptor.id,
                )
            )

        return eligible

    def select_provider(
        self,
        *,
        request: ModelRequest,
        policy: RoutingPolicy,
    ) -> ModelProvider:
        eligible = self.candidate_providers(request=request, policy=policy)
        if not eligible:
            raise NoEligibleProvider(
                "Aucun provider IA n'est autorisé par la politique de confidentialité/capacités."
            )
        return eligible[0]

    @staticmethod
    def _apply_pricing(provider: ModelProvider, response: ModelResponse) -> None:
        if response.usage.estimated_cost_usd is not None:
            return
        pricing = provider.descriptor.metadata.get("pricing") or {}
        input_rate = pricing.get("input_cost_per_million")
        output_rate = pricing.get("output_cost_per_million")
        if input_rate is None or output_rate is None:
            return
        if response.usage.input_tokens is None or response.usage.output_tokens is None:
            return
        response.usage.estimated_cost_usd = round(
            (float(response.usage.input_tokens) / 1_000_000.0) * float(input_rate)
            + (float(response.usage.output_tokens) / 1_000_000.0) * float(output_rate),
            8,
        )

    def generate(
        self,
        request: ModelRequest,
        *,
        policy: RoutingPolicy,
    ) -> ModelResponse:
        candidates = self.candidate_providers(request=request, policy=policy)
        if not candidates:
            raise NoEligibleProvider(
                "Aucun provider IA n'est autorisé par la politique de confidentialité/capacités."
            )

        if not policy.allow_fallback:
            candidates = candidates[:1]

        errors: list[str] = []
        for provider in candidates:
            try:
                if self.provider_guard is not None:
                    self.provider_guard(provider, request)
                response = provider.generate(request)
                self._apply_pricing(provider, response)
                if self.response_hook is not None:
                    self.response_hook(provider, request, response)
                return response
            except Exception as exc:
                errors.append(f"{provider.descriptor.id}: {exc}")

        raise ModelGatewayError(
            "Tous les providers autorisés ont échoué. " + " | ".join(errors[:5])
        )
