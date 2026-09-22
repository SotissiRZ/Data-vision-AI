from __future__ import annotations

import os

from .model_gateway import (
    ModelGateway,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
)
from .providers.anthropic import AnthropicProvider
from .providers.gemini import GeminiProvider
from .providers.ollama import OllamaProvider
from .providers.openai_compatible import OpenAICompatibleProvider


def build_model_gateway_from_env() -> ModelGateway:
    registry = ProviderRegistry()

    ollama_model = os.getenv("DATAVISION_OLLAMA_MODEL")
    if ollama_model:
        registry.register(
            OllamaProvider(
                descriptor=ProviderDescriptor(
                    id="ollama-local",
                    kind="local",
                    model=ollama_model,
                    priority=10,
                    capabilities=ProviderCapabilities(
                        structured_output=True,
                        tools=False,
                        streaming=False,
                    ),
                ),
                base_url=os.getenv(
                    "DATAVISION_OLLAMA_BASE_URL",
                    "http://127.0.0.1:11434",
                ),
            )
        )


    anthropic_model = os.getenv("DATAVISION_ANTHROPIC_MODEL")
    if anthropic_model:
        registry.register(
            AnthropicProvider(
                descriptor=ProviderDescriptor(
                    id="anthropic-native",
                    kind="cloud",
                    model=anthropic_model,
                    priority=40,
                    capabilities=ProviderCapabilities(
                        structured_output=True,
                        tools=False,
                        streaming=False,
                    ),
                    metadata={"provider_type": "anthropic", "location": "external"},
                ),
                base_url=os.getenv("DATAVISION_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                api_key=os.getenv("DATAVISION_ANTHROPIC_API_KEY"),
            )
        )

    gemini_model = os.getenv("DATAVISION_GEMINI_MODEL")
    if gemini_model:
        registry.register(
            GeminiProvider(
                descriptor=ProviderDescriptor(
                    id="gemini-native",
                    kind="cloud",
                    model=gemini_model,
                    priority=45,
                    capabilities=ProviderCapabilities(
                        structured_output=True,
                        tools=False,
                        streaming=False,
                    ),
                    metadata={"provider_type": "gemini", "location": "external"},
                ),
                base_url=os.getenv(
                    "DATAVISION_GEMINI_BASE_URL",
                    "https://generativelanguage.googleapis.com/v1beta",
                ),
                api_key=os.getenv("DATAVISION_GEMINI_API_KEY"),
            )
        )

    compatible_url = os.getenv("DATAVISION_OPENAI_COMPATIBLE_BASE_URL")
    compatible_model = os.getenv("DATAVISION_OPENAI_COMPATIBLE_MODEL")
    if compatible_url and compatible_model:
        registry.register(
            OpenAICompatibleProvider(
                descriptor=ProviderDescriptor(
                    id="openai-compatible",
                    kind="openai_compatible",
                    model=compatible_model,
                    priority=50,
                    capabilities=ProviderCapabilities(
                        structured_output=True,
                        tools=False,
                        streaming=False,
                    ),
                ),
                base_url=compatible_url,
                api_key=os.getenv("DATAVISION_OPENAI_COMPATIBLE_API_KEY"),
            )
        )

    return ModelGateway(registry)
