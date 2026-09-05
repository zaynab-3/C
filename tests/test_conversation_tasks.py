from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import c_backend.tasks as tasks
from c_backend.ai import AIResponse, AITranscription
from c_backend.conversation import ConversationEntry
from c_backend.orchestration import text as text_module
from c_backend.whatsapp_client import WhatsAppSendError
from test_conversation_repository import conversation_db
from test_tasks import FakeResult, FakeSession, make_message


@pytest.mark.anyio
@pytest.mark.parametrize("previous_kind", ["text", "audio"])
@pytest.mark.parametrize("current_kind", ["text", "audio"])
async def test_worker_supplies_db_history_across_modalities(
    monkeypatch, conversation_db, previous_kind, current_kind,
):
    db = conversation_db
    previous_text = "My conversation test word is cedar."
    current_text = "What was the test word I just told you?"
    db.add(1, content="Outside configured history limit")
    db.add(
        2, content_type=previous_kind,
        content=previous_text if previous_kind == "text" else None,
        transcript=previous_text if previous_kind == "audio" else None,
        generated_reply="I will use cedar for this conversation.",
    )
    current_row = db.add(
        3, content_type=current_kind,
        content=current_text if current_kind == "text" else None,
        transcript=None, generated_reply=None, processed_at=None,
    )
    current = make_message(
        **vars(current_row), media_id="test-media", media_mime_type="audio/ogg",
        transcription_provider=None, transcription_model=None, transcribed_at=None,
        external_id="test-current-id",
    )
    session = FakeSession(current)

    async def execute(statement):
        if statement._for_update_arg is not None:
            return FakeResult(current)
        if current_kind == "audio":
            assert session.commit.await_count == 1
            assert current.transcript == current_text
        return await db.session.execute(statement)

    session.execute = AsyncMock(side_effect=execute)
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "engine", SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(conversation_history_limit=1))
    download = AsyncMock(return_value=b"test audio")
    transcription = AsyncMock(return_value=AITranscription(current_text, "gemini", "test-model"))
    monkeypatch.setattr(tasks, "download_whatsapp_audio", download)
    monkeypatch.setattr(tasks, "get_ai_provider", lambda: SimpleNamespace(transcribe_audio=transcription))
    generate = AsyncMock(return_value=AIResponse("cedar", "gemini", "test-model"))
    monkeypatch.setattr(text_module, "get_ai_provider", lambda: SimpleNamespace(generate_text=generate))
    graph = AsyncMock(wraps=tasks.run_text_graph)
    monkeypatch.setattr(tasks, "run_text_graph", graph)

    await tasks._process_message("whatsapp", current.external_id)

    graph.assert_awaited_once()
    assert graph.await_args.args == (current_text,)
    assert graph.await_args.kwargs["history"] == [
        ConversationEntry("user", previous_text),
        ConversationEntry("assistant", "I will use cedar for this conversation."),
    ]
    prompt = generate.await_args.args[0]
    assert "cedar" in prompt and current_text in prompt
    assert "Outside configured history limit" not in prompt
    assert current.external_id not in prompt
    assert current.sender_id not in prompt
    assert current.media_id not in prompt
    if current_kind == "audio":
        download.assert_awaited_once()
        transcription.assert_awaited_once()
        assert session.commit.await_count == 2
    else:
        download.assert_not_awaited()
        transcription.assert_not_awaited()
        session.commit.assert_awaited_once()
    assert current.generated_reply == "cedar"
    assert len(session.added) == 1
    assert session.added[0].event_type == "send_whatsapp_reply"
    assert current.processed_at is None


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["text", "audio"])
async def test_saved_reply_skips_history_loading_and_graph(monkeypatch, kind):
    current = make_message(content_type=kind, generated_reply="Saved output")
    session = FakeSession(current)
    history = AsyncMock(side_effect=AssertionError("Must not reload history"))
    graph = AsyncMock(side_effect=AssertionError("Must not regenerate"))
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "engine", SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr(tasks, "load_recent_conversation", history)
    monkeypatch.setattr(tasks, "run_text_graph", graph)
    await tasks._process_message("whatsapp", current.external_id)
    history.assert_not_awaited()
    graph.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_delivery_retry_never_loads_context_or_regenerates(monkeypatch):
    current = make_message(generated_reply="Saved output")
    session = FakeSession(current)
    history = AsyncMock(side_effect=AssertionError("Must not reload history"))
    graph = AsyncMock(side_effect=AssertionError("Must not regenerate"))
    send = AsyncMock(side_effect=[WhatsAppSendError("temporary failure"), "test-outbound"])
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "engine", SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr(tasks, "load_recent_conversation", history)
    monkeypatch.setattr(tasks, "run_text_graph", graph)
    monkeypatch.setattr(tasks, "send_whatsapp_text", send)
    with pytest.raises(WhatsAppSendError):
        await tasks._send_whatsapp_reply("whatsapp", current.external_id)
    await tasks._send_whatsapp_reply("whatsapp", current.external_id)
    history.assert_not_awaited()
    graph.assert_not_awaited()
    assert send.await_count == 2
    assert all(call.kwargs["body"] == "Saved output" for call in send.await_args_list)
