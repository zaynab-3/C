from unittest.mock import AsyncMock, Mock

import pytest

from c_backend.ai import AIProvider, AIProviderError, AIResponse
from c_backend.orchestration import text as text_module


@pytest.mark.anyio
@pytest.mark.parametrize("provider_name", ["gemini", "openai"])
async def test_graph_calls_provider_and_returns_text_metadata(
    monkeypatch, provider_name,
):
    provider = Mock(spec=AIProvider)
    provider.generate_text = AsyncMock(
        return_value=AIResponse("C reply", provider_name, "test-model")
    )
    factory = Mock(return_value=provider)
    monkeypatch.setattr(text_module, "get_ai_provider", factory)

    result = await text_module.run_text_graph(
        "Hello", system_prompt="Reply concisely."
    )

    factory.assert_called_once_with()
    provider.generate_text.assert_awaited_once_with(
        "Hello", system_prompt="Reply concisely."
    )
    assert result == {
        "response_text": "C reply",
        "provider": provider_name,
        "model": "test-model",
    }


@pytest.mark.anyio
async def test_graph_propagates_provider_error_without_retry(monkeypatch):
    error = AIProviderError("temporary AI outage")
    provider = Mock(spec=AIProvider)
    provider.generate_text = AsyncMock(side_effect=error)
    monkeypatch.setattr(text_module, "get_ai_provider", lambda: provider)

    with pytest.raises(AIProviderError) as caught:
        await text_module.run_text_graph("Hello", system_prompt="You are C.")

    assert caught.value is error
    provider.generate_text.assert_awaited_once()


@pytest.mark.anyio
async def test_graph_invocations_do_not_share_state(monkeypatch):
    provider = Mock(spec=AIProvider)
    provider.generate_text = AsyncMock(side_effect=[
        AIResponse("First reply", "gemini", "first-model"),
        AIResponse("Second reply", "openai", "second-model"),
    ])
    factory = Mock(return_value=provider)
    monkeypatch.setattr(text_module, "get_ai_provider", factory)

    first = await text_module.run_text_graph("First", system_prompt="Prompt 1")
    second = await text_module.run_text_graph("Second", system_prompt="Prompt 2")

    assert first == {
        "response_text": "First reply", "provider": "gemini", "model": "first-model",
    }
    assert second == {
        "response_text": "Second reply", "provider": "openai", "model": "second-model",
    }
    assert factory.call_count == 2
    provider.generate_text.assert_awaited_with("Second", system_prompt="Prompt 2")
