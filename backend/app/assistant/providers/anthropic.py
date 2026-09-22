from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from ..model_gateway import (
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderDescriptor,
)


@dataclass
class AnthropicProvider:
    """Native Anthropic Messages API adapter.

    Structured output uses the current ``output_config.format`` JSON-schema
    contract. The adapter deliberately exposes no provider-side tools: all
    DataVision actions still pass through the governed Tool Registry.
    """

    descriptor: ProviderDescriptor
    base_url: str = "https://api.anthropic.com"
    api_key: str | None = None
    timeout_seconds: int = 60
    anthropic_version: str = "2023-06-01"

    def generate(self, model_request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ModelGatewayError("Clé API Anthropic absente.")

        url = self.base_url.rstrip("/") + "/v1/messages"
        body: dict[str, object] = {
            "model": self.descriptor.model,
            "max_tokens": model_request.max_output_tokens,
            "system": model_request.system,
            "messages": [{"role": "user", "content": model_request.user}],
        }
        # Recent Claude models may reject non-default temperature values. The
        # gateway therefore lets the provider use its model default.
        if model_request.response_schema is not None:
            body["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": model_request.response_schema,
                }
            }

        req = urllib_request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ModelGatewayError(
                f"Provider {self.descriptor.id} indisponible: {exc}"
            ) from exc

        content = payload.get("content") or []
        parts = [
            block.get("text")
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        text = "\n".join(parts).strip()
        if not text:
            raise ModelGatewayError("Réponse Anthropic sans contenu texte exploitable.")

        usage_raw = payload.get("usage") or {}
        return ModelResponse(
            text=text,
            provider_id=self.descriptor.id,
            model=str(payload.get("model") or self.descriptor.model),
            usage=ModelUsage(
                input_tokens=usage_raw.get("input_tokens"),
                output_tokens=usage_raw.get("output_tokens"),
                estimated_cost_usd=None,
            ),
            raw={
                "id": payload.get("id"),
                "stop_reason": payload.get("stop_reason"),
                "type": payload.get("type"),
            },
        )
