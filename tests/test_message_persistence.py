from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from c_backend.models import Message, OutboxEvent
from c_backend.repositories.messages import SaveMessageResult, save_message
from c_backend.schemas.whatsapp import NormalizedMessage


def normalized(kind):
    return NormalizedMessage(
        channel="whatsapp", external_id="wamid.test", sender_id="test-sender",
        content_type=kind, content="Hello C" if kind == "text" else None,
        received_at=datetime.now(timezone.utc),
        **({"media_id": "media-123", "media_mime_type": "audio/ogg",
            "media_sha256": "test-hash", "media_is_voice": True} if kind == "audio" else {}),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["text", "audio"])
async def test_message_and_outbox_share_one_commit(kind):
    added = []
    stages = []

    async def flush():
        assert len(added) == 1
        assert isinstance(added[0], Message)
        stages.append("flush")

    async def commit():
        assert len(added) == 2
        assert isinstance(added[1], OutboxEvent)
        stages.append("commit")

    session = SimpleNamespace(
        add=added.append, flush=AsyncMock(side_effect=flush),
        commit=AsyncMock(side_effect=commit), rollback=AsyncMock(),
    )
    message = normalized(kind)
    result = await save_message(session, message, {"type": kind})
    assert result == SaveMessageResult.STORED
    assert stages == ["flush", "commit"]
    record, event = added
    assert record.content == message.content
    assert record.content_type == kind
    for field in ("media_id", "media_mime_type", "media_sha256", "media_filename", "media_is_voice"):
        assert getattr(record, field) == getattr(message, field)
    assert record.raw_payload == {"type": kind}
    assert event.event_type == "process_message"
    assert event.event_key == "process_message:whatsapp:wamid.test"
    assert event.payload == {"channel": "whatsapp", "external_id": "wamid.test"}
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    assert not any("url" in column.name for column in Message.__table__.columns)


@pytest.mark.anyio
async def test_duplicate_audio_message_rolls_back_without_outbox():
    violation = Mock(spec=UniqueViolation)
    violation.diag = SimpleNamespace(constraint_name="uq_messages_channel_external_id")
    session = SimpleNamespace(
        add=Mock(), flush=AsyncMock(side_effect=IntegrityError("insert", {}, violation)),
        commit=AsyncMock(), rollback=AsyncMock(),
    )
    assert await save_message(session, normalized("audio"), {}) == SaveMessageResult.DUPLICATE
    assert session.add.call_count == 1
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.anyio
async def test_audio_commit_failure_rolls_back_both_records():
    session = SimpleNamespace(
        add=Mock(), flush=AsyncMock(),
        commit=AsyncMock(side_effect=RuntimeError("commit failed")), rollback=AsyncMock(),
    )
    with pytest.raises(RuntimeError, match="commit failed"):
        await save_message(session, normalized("audio"), {})
    assert session.add.call_count == 2
    session.rollback.assert_awaited_once()
