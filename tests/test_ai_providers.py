from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from c_backend.ai.base import (
    AIProviderConfigurationError,
    AIProviderError,
    AIResponse,
    AITranscription,
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
    assert call["config"].automatic_function_calling is not None
    assert call["config"].automatic_function_calling.disable is True


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


@pytest.mark.anyio
@pytest.mark.parametrize("mime_type", ["audio/ogg; codecs=opus", " AUDIO/OGG ; codecs=opus"])
async def test_gemini_transcribes_bytes_with_normalized_mime_type(monkeypatch, mime_type):
    generate = AsyncMock(return_value=SimpleNamespace(text="  Spoken words  "))
    monkeypatch.setattr(gemini_module.genai, "Client", Mock(return_value=SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )))
    provider = gemini_module.GeminiProvider(api_key="dummy-key", model="configured-model")
    result = await provider.transcribe_audio(b"audio", mime_type=mime_type)
    assert result == AITranscription("Spoken words", "gemini", "configured-model")
    call = generate.await_args.kwargs
    assert call["model"] == "configured-model"
    assert len(call["contents"]) == 1
    part = call["contents"][0]
    assert part.inline_data.data == b"audio"
    assert part.inline_data.mime_type == "audio/ogg"
    assert call["config"].automatic_function_calling.disable is True
    assert not call["config"].tools
    assert "Do not answer the speaker" in call["config"].system_instruction
    assert "Return only the recognized spoken content" in call["config"].system_instruction


@pytest.mark.anyio
@pytest.mark.parametrize("mime_type", ["image/png; x=audio/ogg", "audio/; codecs=opus", ""])
async def test_gemini_rejects_invalid_normalized_audio_mime(monkeypatch, mime_type):
    generate = AsyncMock()
    monkeypatch.setattr(gemini_module.genai, "Client", Mock(return_value=SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )))
    provider = gemini_module.GeminiProvider(api_key="dummy-key", model="test-model")
    with pytest.raises(AIProviderError, match="audio MIME type"):
        await provider.transcribe_audio(b"audio", mime_type=mime_type)
    generate.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("returned_text", [None, "", "  "])
async def test_gemini_rejects_empty_transcription(monkeypatch, returned_text):
    generate = AsyncMock(return_value=SimpleNamespace(text=returned_text))
    monkeypatch.setattr(gemini_module.genai, "Client", Mock(return_value=SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )))
    provider = gemini_module.GeminiProvider(api_key="dummy-key", model="test-model")
    with pytest.raises(AIProviderError, match="no transcript"):
        await provider.transcribe_audio(b"audio", mime_type="audio/ogg")


@pytest.mark.anyio
async def test_gemini_transcription_error_is_sanitized(monkeypatch):
    generate = AsyncMock(side_effect=RuntimeError("dummy-sensitive-request"))
    monkeypatch.setattr(gemini_module.genai, "Client", Mock(return_value=SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )))
    provider = gemini_module.GeminiProvider(api_key="dummy-key", model="test-model")
    with pytest.raises(AIProviderError) as caught:
        await provider.transcribe_audio(b"audio", mime_type="audio/ogg")
    assert "dummy-sensitive-request" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.anyio
async def test_openai_keeps_text_support_but_rejects_transcription(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(openai_module, "AsyncOpenAI", constructor)
    provider = openai_module.OpenAIProvider(api_key="dummy-key", model="test-model")
    with pytest.raises(AIProviderError, match="not supported by openai"):
        await provider.transcribe_audio(b"audio", mime_type="audio/ogg")
    constructor.return_value.responses.create.assert_not_called()
