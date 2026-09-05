from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from c_backend.ai.base import (
    AIProviderConfigurationError,
    AIProviderError,
    AIResponse,
)
from c_backend.ai import factory as factory_module
from c_backend.ai import gemini_provider as gemini_module
from c_backend.ai import openai_provider as openai_module


def _settings(provider: str) -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider=provider,
        gemini_api_key="gemini-test-key",
        gemini_model="gemini-test-model",
        openai_api_key="openai-test-key",
        openai_model="openai-test-model",
    )


def test_factory_selects_gemini(monkeypatch):
    sentinel = object()
    constructor = Mock(return_value=sentinel)
    monkeypatch.setattr(
        factory_module,
        "GeminiProvider",
        constructor,
    )

    result = factory_module.get_ai_provider(_settings("gemini"))

    assert result is sentinel
    constructor.assert_called_once_with(
        api_key="gemini-test-key",
        model="gemini-test-model",
    )


def test_factory_selects_openai(monkeypatch):
    sentinel = object()
    constructor = Mock(return_value=sentinel)
    monkeypatch.setattr(
        factory_module,
        "OpenAIProvider",
        constructor,
    )

    result = factory_module.get_ai_provider(_settings("openai"))

    assert result is sentinel
    constructor.assert_called_once_with(
        api_key="openai-test-key",
        model="openai-test-model",
    )


def test_factory_rejects_unknown_provider():
    with pytest.raises(
        AIProviderConfigurationError,
        match="Unsupported AI provider",
    ):
        factory_module.get_ai_provider(_settings("unknown"))


@pytest.mark.anyio
async def test_gemini_provider_generates_text(monkeypatch):
    generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Gemini answer")
    )
    fake_client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=generate_content
            )
        )
    )
    client_constructor = Mock(return_value=fake_client)
    monkeypatch.setattr(
        gemini_module.genai,
        "Client",
        client_constructor,
    )

    provider = gemini_module.GeminiProvider(
        api_key="secret-test-key",
        model="gemini-test-model",
    )
    result = await provider.generate_text(
        "Hello",
        system_prompt="You are C.",
    )

    assert result == AIResponse(
        text="Gemini answer",
        provider="gemini",
        model="gemini-test-model",
    )
    call = generate_content.await_args.kwargs
    assert call["model"] == "gemini-test-model"
    assert call["contents"] == "Hello"
    assert call["config"] is not None


@pytest.mark.anyio
async def test_openai_provider_generates_text(monkeypatch):
    create = AsyncMock(
        return_value=SimpleNamespace(output_text="OpenAI answer")
    )
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=create)
    )
    client_constructor = Mock(return_value=fake_client)
    monkeypatch.setattr(
        openai_module,
        "AsyncOpenAI",
        client_constructor,
    )

    provider = openai_module.OpenAIProvider(
        api_key="secret-test-key",
        model="openai-test-model",
    )
    result = await provider.generate_text(
        "Hello",
        system_prompt="You are C.",
    )

    assert result == AIResponse(
        text="OpenAI answer",
        provider="openai",
        model="openai-test-model",
    )
    create.assert_awaited_once_with(
        model="openai-test-model",
        input="Hello",
        instructions="You are C.",
    )


def test_gemini_provider_requires_key():
    with pytest.raises(
        AIProviderConfigurationError,
        match="GEMINI_API_KEY",
    ):
        gemini_module.GeminiProvider(
            api_key=None,
            model="gemini-test-model",
        )


def test_openai_provider_requires_model():
    with pytest.raises(
        AIProviderConfigurationError,
        match="OPENAI_MODEL",
    ):
        openai_module.OpenAIProvider(
            api_key="openai-test-key",
            model=None,
        )


@pytest.mark.anyio
async def test_provider_rejects_empty_prompt(monkeypatch):
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock())
    )
    monkeypatch.setattr(
        openai_module,
        "AsyncOpenAI",
        Mock(return_value=fake_client),
    )

    provider = openai_module.OpenAIProvider(
        api_key="openai-test-key",
        model="openai-test-model",
    )

    with pytest.raises(AIProviderError, match="Prompt must not be empty"):
        await provider.generate_text("   ")
