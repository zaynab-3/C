import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import c_backend.tasks as tasks_module


class FakeResult:
    def __init__(self, message):
        self.message = message

    def scalar_one_or_none(self):
        return self.message


class FakeSession:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return FakeResult(self.message)


@pytest.mark.anyio
async def test_worker_automatically_replies_to_whatsapp(
    monkeypatch,
):
    message_id = uuid.uuid4()

    message = SimpleNamespace(
        id=message_id,
        channel="whatsapp",
        external_id="wamid.worker.test",
        sender_id="96170123456",
        content="Hello C",
    )

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: FakeSession(message),
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

    send_mock.assert_awaited_once_with(
        to="96170123456",
        body="C received your message automatically.",
    )

    dispose_mock.assert_awaited_once()

    assert result == f"processed message {message_id}"
