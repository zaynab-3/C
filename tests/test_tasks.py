import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest

import c_backend.tasks as tasks_module
from c_backend.ai import AIProviderError
from c_backend.whatsapp_client import WhatsAppSendError


class FakeResult:
    def __init__(self, message):
        self.message = message

    def scalar_one_or_none(self):
        return self.message


class FakeSession:
    def __init__(self, message):
        self.message = message
        self.commit = AsyncMock()
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return FakeResult(self.message)

    def add(self, value):
        self.added.append(value)


def make_message(**overrides):
    values = {
        "id": uuid.uuid4(),
        "channel": "whatsapp",
        "external_id": "wamid.worker.test",
        "sender_id": "96170123456",
        "content": "Hello C",
        "generated_reply": None,
        "ai_provider": None,
        "ai_model": None,
        "ai_generated_at": None,
        "processed_at": None,
        "outbound_external_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_worker_persists_ai_reply_and_queues_delivery(
    monkeypatch,
):
    message = make_message()
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
    provider_factory = Mock(
        return_value=SimpleNamespace(
            generate_text=generate_mock
        )
    )
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
        external_id="wamid.worker.test",
    )

    provider_factory.assert_called_once_with()
    generate_mock.assert_awaited_once_with(
        "Hello C",
        system_prompt=ANY,
    )
    send_mock.assert_not_awaited()

    assert message.generated_reply == "Hello from C intelligence."
    assert message.ai_provider == "gemini"
    assert message.ai_model == "gemini-test-model"
    assert message.ai_generated_at is not None
    assert message.processed_at is None
    assert message.outbound_external_id is None

    assert len(fake_session.added) == 1
    event = fake_session.added[0]
    assert event.event_type == "send_whatsapp_reply"
    assert event.event_key == f"send_whatsapp_reply:{message.id}"
    assert event.payload == {
        "channel": "whatsapp",
        "external_id": "wamid.worker.test",
    }

    fake_session.commit.assert_awaited_once()
    dispose_mock.assert_awaited_once()
    assert result == f"prepared message {message.id}"


@pytest.mark.anyio
async def test_worker_reuses_persisted_reply_without_ai(
    monkeypatch,
):
    message = make_message(
        generated_reply="Already generated.",
        ai_provider="gemini",
        ai_model="gemini-test-model",
        ai_generated_at=object(),
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

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    result = await tasks_module._process_message(
        channel="whatsapp",
        external_id=message.external_id,
    )

    provider_factory.assert_not_called()
    assert fake_session.added == []
    fake_session.commit.assert_not_awaited()
    dispose_mock.assert_awaited_once()
    assert (
        result
        == f"reply already prepared for message {message.id}"
    )


@pytest.mark.anyio
async def test_worker_ai_failure_does_not_persist_or_queue(
    monkeypatch,
):
    message = make_message(
        external_id="wamid.worker.ai.fail"
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
            external_id=message.external_id,
        )

    fake_session.commit.assert_not_awaited()
    assert fake_session.added == []
    assert message.generated_reply is None
    assert message.processed_at is None
    dispose_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_sender_uses_saved_reply_and_marks_delivered(
    monkeypatch,
):
    message = make_message(
        generated_reply="Persisted C reply.",
        ai_provider="gemini",
        ai_model="gemini-test-model",
        ai_generated_at=object(),
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

    result = await tasks_module._send_whatsapp_reply(
        channel="whatsapp",
        external_id=message.external_id,
    )

    provider_factory.assert_not_called()
    send_mock.assert_awaited_once_with(
        to="96170123456",
        body="Persisted C reply.",
    )
    assert message.processed_at is not None
    assert message.outbound_external_id == "wamid.outbound.test"
    fake_session.commit.assert_awaited_once()
    dispose_mock.assert_awaited_once()
    assert result == f"delivered message {message.id}"


@pytest.mark.anyio
async def test_sender_failure_keeps_saved_reply_for_retry(
    monkeypatch,
):
    message = make_message(
        generated_reply="Persisted C reply.",
        ai_provider="gemini",
        ai_model="gemini-test-model",
        ai_generated_at=object(),
    )
    fake_session = FakeSession(message)

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    send_mock = AsyncMock(
        side_effect=WhatsAppSendError(
            "temporary Meta failure"
        )
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

    with pytest.raises(
        WhatsAppSendError,
        match="temporary Meta failure",
    ):
        await tasks_module._send_whatsapp_reply(
            channel="whatsapp",
            external_id=message.external_id,
        )

    send_mock.assert_awaited_once_with(
        to="96170123456",
        body="Persisted C reply.",
    )
    assert message.generated_reply == "Persisted C reply."
    assert message.processed_at is None
    assert message.outbound_external_id is None
    fake_session.commit.assert_not_awaited()
    dispose_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_sender_skips_already_processed_message(
    monkeypatch,
):
    message = make_message(
        external_id="wamid.worker.duplicate",
        generated_reply="Already sent.",
        processed_at=object(),
        outbound_external_id="wamid.already.sent",
    )
    fake_session = FakeSession(message)

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
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

    result = await tasks_module._send_whatsapp_reply(
        channel="whatsapp",
        external_id=message.external_id,
    )

    send_mock.assert_not_awaited()
    fake_session.commit.assert_not_awaited()
    dispose_mock.assert_awaited_once()
    assert (
        result
        == f"already delivered message {message.id}"
    )
