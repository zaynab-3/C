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


@pytest.mark.anyio
async def test_outbox_dispatcher_publishes_event(
    monkeypatch,
):
    event = SimpleNamespace(
        event_type="process_message",
        payload={
            "channel": "whatsapp",
            "external_id": "wamid.dispatch.test",
        },
        status="pending",
        attempts=0,
        available_at=datetime.now(timezone.utc),
        last_error=None,
        published_at=None,
    )

    fake_session = FakeOutboxSession([event])

    monkeypatch.setattr(
        tasks_module,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    delay_mock = Mock()

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

    delay_mock.assert_called_once_with(
        "whatsapp",
        "wamid.dispatch.test",
    )

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

    event = SimpleNamespace(
        event_type="process_message",
        payload={
            "channel": "whatsapp",
            "external_id": "wamid.dispatch.fail",
        },
        status="pending",
        attempts=0,
        available_at=original_available_at,
        last_error=None,
        published_at=None,
    )

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
