from __future__ import annotations

from dataclasses import dataclass

from ..model_gateway import ModelRequest, ModelResponse, ProviderDescriptor


@dataclass
class StaticModelProvider:
    descriptor: ProviderDescriptor
    response_text: str

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text=self.response_text,
            provider_id=self.descriptor.id,
            model=self.descriptor.model,
            raw={"mock": True},
        )
