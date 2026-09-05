import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest

import c_backend.tasks as tasks_module
from c_backend.ai import AIProviderError


class FakeResult:
    def __init__(self, message):
        self.message = message

    def scalar_one_or_none(self):
        return self.message


class FakeSession:
    def __init__(self, message):
        self.message = message
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return FakeResult(self.message)


@pytest.mark.anyio
async def test_worker_uses_ai_provider_for_whatsapp_reply(
    monkeypatch,
):
    message_id = uuid.uuid4()

    message = SimpleNamespace(
        id=message_id,
        channel="whatsapp",
        external_id="wamid.worker.test",
        sender_id="96170123456",
        content="Hello C",
        processed_at=None,
        outbound_external_id=None,
    )

    fake_session = FakeSession(message)
    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    generate_mock = AsyncMock(
        return_value=SimpleNamespace(
            text="Hello from C intelligence.",
            provider="gemini",
            model="gemini-test-model",
        )
    )
    provider = SimpleNamespace(generate_text=generate_mock)
    provider_factory = Mock(return_value=provider)
    monkeypatch.setattr(
        tasks_module,
        "get_ai_provider",
        provider_factory,
    )

    send_mock = AsyncMock(
        return_value="wamid.outbound.test"
    )
    monkeypatch.setattr(
        tasks_module,
        "send_whatsapp_text",
        send_mock,
    )

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    result = await tasks_module._process_message(
        channel="whatsapp",
        external_id="wamid.worker.test",
    )

    provider_factory.assert_called_once_with()
    generate_mock.assert_awaited_once_with(
        "Hello C",
        system_prompt=ANY,
    )
    system_prompt = generate_mock.await_args.kwargs[
        "system_prompt"
    ]
    assert "Tool execution is not available" in system_prompt

    send_mock.assert_awaited_once_with(
        to="96170123456",
        body="Hello from C intelligence.",
    )

    assert message.processed_at is not None
    assert (
        message.outbound_external_id
        == "wamid.outbound.test"
    )

    fake_session.commit.assert_awaited_once()
    dispose_mock.assert_awaited_once()

    assert result == f"processed message {message_id}"


@pytest.mark.anyio
async def test_worker_ai_failure_does_not_send_or_mark_processed(
    monkeypatch,
):
    message = SimpleNamespace(
        id=uuid.uuid4(),
        channel="whatsapp",
        external_id="wamid.worker.ai.fail",
        sender_id="96170123456",
        content="Hello C",
        processed_at=None,
        outbound_external_id=None,
    )

    fake_session = FakeSession(message)
    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    generate_mock = AsyncMock(
        side_effect=AIProviderError("temporary AI outage")
    )
    monkeypatch.setattr(
        tasks_module,
        "get_ai_provider",
        Mock(
            return_value=SimpleNamespace(
                generate_text=generate_mock
            )
        ),
    )

    send_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "send_whatsapp_text",
        send_mock,
    )

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    with pytest.raises(
        AIProviderError,
        match="temporary AI outage",
    ):
        await tasks_module._process_message(
            channel="whatsapp",
            external_id="wamid.worker.ai.fail",
        )

    send_mock.assert_not_awaited()
    fake_session.commit.assert_not_awaited()
    assert message.processed_at is None
    assert message.outbound_external_id is None
    dispose_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_skips_already_processed_message(
    monkeypatch,
):
    message_id = uuid.uuid4()

    message = SimpleNamespace(
        id=message_id,
        channel="whatsapp",
        external_id="wamid.worker.duplicate",
        sender_id="96170123456",
        content="Hello again",
        processed_at=object(),
        outbound_external_id="wamid.already.sent",
    )

    fake_session = FakeSession(message)
    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    provider_factory = Mock()
    monkeypatch.setattr(
        tasks_module,
        "get_ai_provider",
        provider_factory,
    )

    send_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "send_whatsapp_text",
        send_mock,
    )

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    result = await tasks_module._process_message(
        channel="whatsapp",
        external_id="wamid.worker.duplicate",
    )

    provider_factory.assert_not_called()
    send_mock.assert_not_awaited()
    fake_session.commit.assert_not_awaited()
    dispose_mock.assert_awaited_once()

    assert result == f"already processed message {message_id}"
