from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import c_backend.tasks as tasks_module


class FakeOutboxResult:
    def __init__(self, events):
        self.events = events

    def scalars(self):
        return self.events


class FakeOutboxSession:
    def __init__(self, events):
        self.events = events
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return FakeOutboxResult(self.events)


def make_event(event_type, external_id):
    return SimpleNamespace(
        event_type=event_type,
        payload={
            "channel": "whatsapp",
            "external_id": external_id,
        },
        status="pending",
        attempts=0,
        available_at=datetime.now(timezone.utc),
        last_error=None,
        published_at=None,
    )


@pytest.mark.anyio
async def test_outbox_dispatcher_publishes_process_event(
    monkeypatch,
):
    event = make_event(
        "process_message",
        "wamid.dispatch.test",
    )
    fake_session = FakeOutboxSession([event])

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    process_delay = Mock()
    send_delay = Mock()
    monkeypatch.setattr(
        tasks_module.process_message,
        "delay",
        process_delay,
    )
    monkeypatch.setattr(
        tasks_module.send_whatsapp_reply,
        "delay",
        send_delay,
    )

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    result = await tasks_module._dispatch_outbox_batch()

    process_delay.assert_called_once_with(
        "whatsapp",
        "wamid.dispatch.test",
    )
    send_delay.assert_not_called()

    assert event.status == "published"
    assert event.attempts == 1
    assert event.published_at is not None
    assert event.last_error is None
    fake_session.commit.assert_awaited_once()
    dispose_mock.assert_awaited_once()
    assert result == "published=1 failed=0"


@pytest.mark.anyio
async def test_outbox_dispatcher_publishes_send_event(
    monkeypatch,
):
    event = make_event(
        "send_whatsapp_reply",
        "wamid.dispatch.send",
    )
    fake_session = FakeOutboxSession([event])

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    process_delay = Mock()
    send_delay = Mock()
    monkeypatch.setattr(
        tasks_module.process_message,
        "delay",
        process_delay,
    )
    monkeypatch.setattr(
        tasks_module.send_whatsapp_reply,
        "delay",
        send_delay,
    )

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    result = await tasks_module._dispatch_outbox_batch()

    send_delay.assert_called_once_with(
        "whatsapp",
        "wamid.dispatch.send",
    )
    process_delay.assert_not_called()

    assert event.status == "published"
    assert event.attempts == 1
    assert event.published_at is not None
    assert event.last_error is None
    fake_session.commit.assert_awaited_once()
    dispose_mock.assert_awaited_once()
    assert result == "published=1 failed=0"


@pytest.mark.anyio
async def test_outbox_dispatcher_retries_failed_publish(
    monkeypatch,
):
    original_available_at = datetime.now(timezone.utc)
    event = make_event(
        "process_message",
        "wamid.dispatch.fail",
    )
    event.available_at = original_available_at

    fake_session = FakeOutboxSession([event])

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    delay_mock = Mock(
        side_effect=RuntimeError("Redis unavailable")
    )
    monkeypatch.setattr(
        tasks_module.process_message,
        "delay",
        delay_mock,
    )

    dispose_mock = AsyncMock()
    monkeypatch.setattr(
        tasks_module,
        "engine",
        SimpleNamespace(dispose=dispose_mock),
    )

    result = await tasks_module._dispatch_outbox_batch()

    assert event.status == "pending"
    assert event.attempts == 1
    assert "Redis unavailable" in event.last_error
    assert event.available_at > original_available_at
    assert event.published_at is None
    fake_session.commit.assert_awaited_once()
    dispose_mock.assert_awaited_once()
    assert result == "published=0 failed=1"
