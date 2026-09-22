from __future__ import annotations

import json

from app.assistant.model_gateway import (
    ModelGateway,
    ModelRequest,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    RoutingPolicy,
)
from app.assistant.model_gateway_config import build_model_gateway_from_env
from app.assistant.providers.anthropic import AnthropicProvider
from app.assistant.providers.gemini import GeminiProvider


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _descriptor(provider_id: str, model: str) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        kind="cloud",
        model=model,
        priority=20,
        capabilities=ProviderCapabilities(structured_output=True),
        metadata={"provider_type": provider_id, "location": "external"},
    )


def test_v273_anthropic_native_adapter_uses_messages_and_structured_output(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Response({
            "id": "msg_123",
            "type": "message",
            "model": "claude-test",
            "content": [{"type": "text", "text": '{"ok":true}'}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 5},
        })

    monkeypatch.setattr(
        "app.assistant.providers.anthropic.urllib_request.urlopen", fake_urlopen
    )
    provider = AnthropicProvider(
        descriptor=_descriptor("anthropic", "claude-test"),
        api_key="secret",
    )
    response = provider.generate(ModelRequest(
        task="planner",
        system="system",
        user="user",
        response_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        temperature=0.0,
        max_output_tokens=100,
    ))

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert "temperature" not in captured["body"]
    assert captured["body"]["output_config"]["format"]["type"] == "json_schema"
    assert captured["body"]["output_config"]["format"]["schema"]["required"] == ["ok"]
    assert response.text == '{"ok":true}'
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 5


def test_v273_gemini_native_adapter_uses_generate_content_and_json_schema(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Response({
            "responseId": "resp_123",
            "modelVersion": "gemini-test-001",
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": '{"ok":true}'}]},
            }],
            "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4},
        })

    monkeypatch.setattr(
        "app.assistant.providers.gemini.urllib_request.urlopen", fake_urlopen
    )
    provider = GeminiProvider(
        descriptor=_descriptor("gemini", "models/gemini-test"),
        api_key="secret",
    )
    response = provider.generate(ModelRequest(
        task="planner",
        system="system",
        user="user",
        response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        temperature=0.2,
        max_output_tokens=100,
    ))

    assert captured["url"].endswith("/models/gemini-test:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "secret"
    config = captured["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["type"] == "object"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "system"
    assert response.text == '{"ok":true}'
    assert response.usage.input_tokens == 9
    assert response.usage.output_tokens == 4


def test_v273_env_gateway_registers_native_providers(monkeypatch):
    monkeypatch.setenv("DATAVISION_ANTHROPIC_MODEL", "claude-test")
    monkeypatch.setenv("DATAVISION_ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("DATAVISION_GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("DATAVISION_GEMINI_API_KEY", "gemini-secret")
    monkeypatch.delenv("DATAVISION_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("DATAVISION_OPENAI_COMPATIBLE_BASE_URL", raising=False)
    monkeypatch.delenv("DATAVISION_OPENAI_COMPATIBLE_MODEL", raising=False)

    gateway = build_model_gateway_from_env()
    providers = {provider.descriptor.id: provider for provider in gateway.registry.list()}
    assert set(providers) == {"anthropic-native", "gemini-native"}
    assert isinstance(providers["anthropic-native"], AnthropicProvider)
    assert isinstance(providers["gemini-native"], GeminiProvider)
    assert all(p.descriptor.capabilities.structured_output for p in providers.values())


def test_v273_privacy_policy_still_blocks_native_cloud_providers():
    registry = ProviderRegistry()
    registry.register(AnthropicProvider(
        descriptor=_descriptor("anthropic", "claude-test"), api_key="x"
    ))
    registry.register(GeminiProvider(
        descriptor=_descriptor("gemini", "gemini-test"), api_key="x"
    ))
    gateway = ModelGateway(registry)
    request = ModelRequest(task="planner", system="", user="", response_schema={"type": "object"})

    assert gateway.candidate_providers(
        request=request,
        policy=RoutingPolicy(privacy_mode="local_only", allow_external_ai=False),
    ) == []
    allowed = gateway.candidate_providers(
        request=request,
        policy=RoutingPolicy(privacy_mode="allow_external", allow_external_ai=True),
    )
    assert [provider.descriptor.id for provider in allowed] == ["anthropic", "gemini"]


def test_v273_frontend_exposes_native_provider_types():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    client = (root / "frontend/lib/assistant/settings-client.ts").read_text(encoding="utf-8")
    center = (root / "frontend/components/assistant/AIProviderControlCenter.tsx").read_text(encoding="utf-8")
    assert '"anthropic"' in client and '"gemini"' in client
    assert 'value="anthropic"' in center and 'value="gemini"' in center
    assert "https://api.anthropic.com" in center
    assert "https://generativelanguage.googleapis.com/v1beta" in center
