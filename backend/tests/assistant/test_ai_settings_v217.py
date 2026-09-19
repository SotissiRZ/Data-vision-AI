from app.assistant.ai_settings import (
    AssistantAISettings,
    ExternalDataPolicy,
    ProviderProfileInput,
    _validate_provider_url,
)


def test_local_only_forces_external_ai_off():
    settings = AssistantAISettings(
        privacy_mode="local_only",
        allow_external_ai=True,
    )
    assert settings.allow_external_ai is False


def test_raw_rows_and_sample_values_cannot_be_enabled():
    settings = AssistantAISettings(
        external_data_policy=ExternalDataPolicy(
            include_sample_values=True,
            include_row_data=True,
        )
    )
    assert settings.external_data_policy.include_sample_values is False
    assert settings.external_data_policy.include_row_data is False


def test_external_provider_requires_https():
    profile = ProviderProfileInput(
        name="External",
        provider_type="openai_compatible",
        location="external",
        base_url="http://example.com/v1",
        model="model",
    )

    try:
        _validate_provider_url(profile)
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("HTTP external provider should be rejected")
