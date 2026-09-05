from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, MetaData, Table, create_engine
from sqlalchemy.dialects import postgresql

from c_backend.config import Settings
from c_backend.conversation import ConversationEntry
from c_backend.models import Message
from c_backend.repositories.conversation import load_recent_conversation


BASE_TIME = datetime(2026, 9, 5, tzinfo=timezone.utc)


@pytest.fixture
def conversation_db():
    # Run the actual selection SQL against a local, in-memory table containing
    # only relevant columns. No PostgreSQL service, drivers or credentials used.
    fields = (
        "id", "channel", "sender_id", "received_at", "created_at",
        "content_type", "content", "transcript", "generated_reply", "processed_at",
    )
    table = Table("messages", MetaData(), *[
        Column(name, Message.__table__.columns[name].type) for name in fields
    ])
    engine = create_engine("sqlite:///:memory:")
    table.create(engine)
    with engine.connect() as connection:
        def add(number, **overrides):
            values = {
                "id": UUID(int=number), "channel": "whatsapp", "sender_id": "sender-a",
                "received_at": BASE_TIME + timedelta(seconds=number),
                "created_at": BASE_TIME + timedelta(seconds=number),
                "content_type": "text", "content": f"user-{number}",
                "transcript": None, "generated_reply": f"assistant-{number}",
                "processed_at": BASE_TIME + timedelta(seconds=number),
            }
            values.update(overrides)
            connection.execute(table.insert().values(**values))
            return SimpleNamespace(**values)

        yield SimpleNamespace(
            add=add, session=SimpleNamespace(execute=AsyncMock(side_effect=connection.execute)),
        )
    engine.dispose()


@pytest.mark.anyio
async def test_same_conversation_only_and_current_and_future_excluded(conversation_db):
    db = conversation_db
    db.add(1)
    db.add(2, sender_id="sender-b")
    db.add(3, channel="another-channel")
    current = db.add(4)
    db.add(5)
    history = await load_recent_conversation(db.session, current, limit=10)
    assert history == [
        ConversationEntry("user", "user-1"), ConversationEntry("assistant", "assistant-1"),
    ]


@pytest.mark.anyio
async def test_sql_limit_selects_newest_rows_then_returns_chronological_entries(conversation_db):
    db = conversation_db
    for number in (4, 1, 3, 2):
        db.add(number)
    current = db.add(5)
    history = await load_recent_conversation(db.session, current, limit=2)
    assert history == [
        ConversationEntry("user", "user-3"), ConversationEntry("assistant", "assistant-3"),
        ConversationEntry("user", "user-4"), ConversationEntry("assistant", "assistant-4"),
    ]
    statement = db.session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "LIMIT" in str(compiled)
    assert statement._limit_clause.value == 2
    assert [column.name for column in statement.selected_columns] == [
        "content_type", "content", "transcript", "generated_reply", "processed_at",
    ]  # No identifiers, raw payloads or media metadata loaded into history.


@pytest.mark.anyio
async def test_equal_timestamps_use_created_at_then_id_for_stable_boundary(conversation_db):
    db = conversation_db
    db.add(4, received_at=BASE_TIME, created_at=BASE_TIME)
    db.add(2, received_at=BASE_TIME, created_at=BASE_TIME)
    db.add(7, received_at=BASE_TIME, created_at=BASE_TIME - timedelta(seconds=1))
    current = db.add(3, received_at=BASE_TIME, created_at=BASE_TIME)
    db.add(1, received_at=BASE_TIME, created_at=BASE_TIME + timedelta(seconds=1))
    history = await load_recent_conversation(db.session, current, limit=10)
    assert [entry.content for entry in history] == [
        "user-7", "assistant-7", "user-2", "assistant-2",
    ]


@pytest.mark.anyio
async def test_normalizes_only_text_and_audio_and_available_persisted_replies(conversation_db):
    db = conversation_db
    db.add(1, content="Text content", transcript="wrong text source")
    db.add(2, content_type="audio", content="wrong audio source", transcript="Spoken text")
    db.add(3, content_type="audio", content="not a transcript", transcript=None, generated_reply=None)
    db.add(4, content="Pending user", generated_reply=None)
    db.add(5, content_type="audio", transcript=None, generated_reply="Persisted reply only")
    db.add(6, content_type="image", content="unsupported", generated_reply="unsupported reply")
    db.add(7, content="  ", generated_reply="  ")
    current = db.add(8)
    history = await load_recent_conversation(db.session, current, limit=10)
    assert history == [
        ConversationEntry("user", "Text content"), ConversationEntry("assistant", "assistant-1"),
        ConversationEntry("user", "Spoken text"), ConversationEntry("assistant", "assistant-2"),
        ConversationEntry("user", "Pending user"),
        ConversationEntry("assistant", "Persisted reply only"),
    ]


@pytest.mark.anyio
async def test_only_delivered_assistant_replies_enter_context(conversation_db):
    db = conversation_db
    db.add(
        1,
        content="First user message",
        generated_reply="Generated but not delivered",
        processed_at=None,
    )
    db.add(
        2,
        content="Second user message",
        generated_reply="Delivered assistant reply",
    )
    current = db.add(3)

    history = await load_recent_conversation(db.session, current, limit=10)

    assert history == [
        ConversationEntry("user", "First user message"),
        ConversationEntry("user", "Second user message"),
        ConversationEntry("assistant", "Delivered assistant reply"),
    ]


@pytest.mark.anyio
async def test_disabled_context_does_not_query(conversation_db):
    db = conversation_db
    current = db.add(1)
    assert await load_recent_conversation(db.session, current, limit=0) == []
    db.session.execute.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [-1, 51])
async def test_repository_rejects_unbounded_limits(conversation_db, limit):
    db = conversation_db
    with pytest.raises(ValueError, match="between 0 and 50"):
        await load_recent_conversation(db.session, db.add(1), limit=limit)
    db.session.execute.assert_not_awaited()


@pytest.mark.parametrize("limit", [-1, 51])
def test_settings_reject_out_of_range_context_limits(limit):
    with pytest.raises(ValidationError, match="CONVERSATION_HISTORY_LIMIT"):
        Settings(_env_file=None, CONVERSATION_HISTORY_LIMIT=limit)


def test_settings_default_and_configurable_context_limit(monkeypatch):
    required = {
        "POSTGRES_DB": "test_db",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": 5432,
        "CELERY_BROKER_URL": "redis://127.0.0.1:6379/0",
    }
    monkeypatch.delenv("CONVERSATION_HISTORY_LIMIT", raising=False)
    assert Settings(
        _env_file=None,
        **required,
    ).conversation_history_limit == 10

    monkeypatch.setenv("CONVERSATION_HISTORY_LIMIT", "3")
    assert Settings(
        _env_file=None,
        **required,
    ).conversation_history_limit == 3
