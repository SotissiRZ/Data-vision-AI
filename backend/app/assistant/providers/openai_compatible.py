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
class OpenAICompatibleProvider:
    descriptor: ProviderDescriptor
    base_url: str
    api_key: str | None = None
    timeout_seconds: int = 60

    def generate(self, model_request: ModelRequest) -> ModelResponse:
        url = self.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.descriptor.model,
            "messages": [
                {"role": "system", "content": model_request.system},
                {"role": "user", "content": model_request.user},
            ],
            "temperature": model_request.temperature,
            "max_tokens": model_request.max_output_tokens,
        }

        if model_request.response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "datavision_response",
                    "schema": model_request.response_schema,
                    "strict": True,
                },
            }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib_request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ModelGatewayError(
                f"Provider {self.descriptor.id} indisponible: {exc}"
            ) from exc

        choices = payload.get("choices") or []
        if not choices:
            raise ModelGatewayError("Réponse provider sans choices.")

        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise ModelGatewayError("Réponse provider sans contenu texte exploitable.")

        usage_raw = payload.get("usage") or {}
        return ModelResponse(
            text=content,
            provider_id=self.descriptor.id,
            model=self.descriptor.model,
            usage=ModelUsage(
                input_tokens=usage_raw.get("prompt_tokens"),
                output_tokens=usage_raw.get("completion_tokens"),
                estimated_cost_usd=None,
            ),
            raw={
                "id": payload.get("id"),
                "finish_reason": choices[0].get("finish_reason"),
            },
        )
