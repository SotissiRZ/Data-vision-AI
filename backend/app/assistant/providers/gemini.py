from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from ..model_gateway import (
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderDescriptor,
)


@dataclass
class GeminiProvider:
    """Native Gemini ``models.generateContent`` REST adapter."""

    descriptor: ProviderDescriptor
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    api_key: str | None = None
    timeout_seconds: int = 60

    def generate(self, model_request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ModelGatewayError("Clé API Gemini absente.")

        model = self.descriptor.model.strip()
        if model.startswith("models/"):
            model = model[len("models/"):]
        model_path = quote(model, safe="-._")
        url = self.base_url.rstrip("/") + f"/models/{model_path}:generateContent"

        generation_config: dict[str, object] = {
            "temperature": model_request.temperature,
            "maxOutputTokens": model_request.max_output_tokens,
        }
        if model_request.response_schema is not None:
            generation_config.update({
                "responseMimeType": "application/json",
                "responseJsonSchema": model_request.response_schema,
            })

        body = {
            "systemInstruction": {
                "parts": [{"text": model_request.system}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": model_request.user}],
                }
            ],
            "generationConfig": generation_config,
        }
        req = urllib_request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
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

        candidates = payload.get("candidates") or []
        if not candidates:
            feedback = payload.get("promptFeedback") or {}
            reason = feedback.get("blockReason")
            suffix = f" ({reason})" if reason else ""
            raise ModelGatewayError(f"Réponse Gemini sans candidat{suffix}.")

        first = candidates[0] if isinstance(candidates[0], dict) else {}
        content = first.get("content") or {}
        parts = content.get("parts") or [] if isinstance(content, dict) else []
        text_parts = [
            part.get("text")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        text = "\n".join(text_parts).strip()
        if not text:
            raise ModelGatewayError("Réponse Gemini sans contenu texte exploitable.")

        usage_raw = payload.get("usageMetadata") or {}
        return ModelResponse(
            text=text,
            provider_id=self.descriptor.id,
            model=str(payload.get("modelVersion") or self.descriptor.model),
            usage=ModelUsage(
                input_tokens=usage_raw.get("promptTokenCount"),
                output_tokens=usage_raw.get("candidatesTokenCount"),
                estimated_cost_usd=None,
            ),
            raw={
                "response_id": payload.get("responseId"),
                "finish_reason": first.get("finishReason"),
                "model_version": payload.get("modelVersion"),
            },
        )
