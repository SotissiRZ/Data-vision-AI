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
class OllamaProvider:
    descriptor: ProviderDescriptor
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 120

    def generate(self, model_request: ModelRequest) -> ModelResponse:
        url = self.base_url.rstrip("/") + "/api/chat"
        body = {
            "model": self.descriptor.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": model_request.system},
                {"role": "user", "content": model_request.user},
            ],
            "options": {"temperature": model_request.temperature},
        }

        if model_request.response_schema is not None:
            body["format"] = model_request.response_schema

        req = urllib_request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ModelGatewayError(f"Provider local indisponible: {exc}") from exc

        content = payload.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ModelGatewayError("Réponse locale sans contenu exploitable.")

        return ModelResponse(
            text=content,
            provider_id=self.descriptor.id,
            model=self.descriptor.model,
            usage=ModelUsage(
                input_tokens=payload.get("prompt_eval_count"),
                output_tokens=payload.get("eval_count"),
                estimated_cost_usd=0.0,
            ),
            raw={
                "done_reason": payload.get("done_reason"),
                "eval_count": payload.get("eval_count"),
                "prompt_eval_count": payload.get("prompt_eval_count"),
            },
        )
