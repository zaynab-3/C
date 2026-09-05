import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import c_backend.tasks as tasks
from c_backend.ai import AIProviderError, AITranscription
from c_backend.whatsapp_media import WhatsAppMediaError
from c_backend.whatsapp_client import WhatsAppSendError
from test_tasks import FakeResult, make_message


@pytest.fixture
def audio_worker(monkeypatch):
    database = make_message(
        content_type="audio", content=None, media_id="media-123",
        media_mime_type="audio/ogg; codecs=opus", transcript=None,
        transcription_provider=None, transcription_model=None, transcribed_at=None,
    )
    commits = []
    events = []
    reads = []

    class Session:
        async def __aenter__(self):
            self.added = []
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            assert statement._for_update_arg is not None
            reads.append(statement.get_execution_options())
            self.message = copy.deepcopy(database)
            return FakeResult(self.message)

        def add(self, event):
            self.added.append(event)

        async def commit(self):
            database.__dict__.update(copy.deepcopy(self.message.__dict__))
            events.extend(self.added)
            self.added = []
            commits.append(copy.deepcopy(database))

    download = AsyncMock(return_value=b"audio bytes")
    transcribe = AsyncMock(return_value=AITranscription(
        "  Spoken request  ", "gemini", "transcription-model",
    ))
    provider = Mock(return_value=SimpleNamespace(transcribe_audio=transcribe))
    graph = AsyncMock(return_value={
        "response_text": "C reply", "provider": "gemini", "model": "reply-model",
    })
    send = AsyncMock(return_value="outbound-123")
    monkeypatch.setattr(tasks, "AsyncSessionLocal", Session)
    monkeypatch.setattr(tasks, "engine", SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr(tasks, "download_whatsapp_audio", download)
    monkeypatch.setattr(tasks, "get_ai_provider", provider)
    monkeypatch.setattr(tasks, "run_text_graph", graph)
    monkeypatch.setattr(tasks, "send_whatsapp_text", send)
    return SimpleNamespace(
        db=database, commits=commits, events=events, reads=reads,
        download=download, transcribe=transcribe, graph=graph, send=send,
        provider=provider, session=Session,
    )


async def process(worker):
    return await tasks._process_message("whatsapp", worker.db.external_id)


@pytest.mark.anyio
async def test_audio_commits_transcript_before_graph_and_outbox(audio_worker):
    w = audio_worker

    async def generate(*args, **kwargs):
        assert len(w.commits) == 1
        assert w.db.transcript == "Spoken request"
        assert w.db.generated_reply is None
        assert w.db.processed_at is None
        assert w.events == []
        return {"response_text": "C reply", "provider": "gemini", "model": "reply-model"}

    w.graph.side_effect = generate
    await process(w)
    w.download.assert_awaited_once_with("media-123")
    w.transcribe.assert_awaited_once_with(b"audio bytes", mime_type="audio/ogg; codecs=opus")
    assert w.graph.await_args.args == ("Spoken request",)
    assert w.db.content is None
    assert w.db.transcription_provider == "gemini"
    assert w.db.transcription_model == "transcription-model"
    assert w.db.transcribed_at is not None
    assert w.db.ai_model == "reply-model"
    assert w.db.ai_generated_at is not None
    assert w.db.processed_at is None
    assert len(w.commits) == 2
    assert len(w.reads) == 2
    assert w.reads[-1]["populate_existing"] is True
    assert len(w.events) == 1
    assert w.events[0].event_key == f"send_whatsapp_reply:{w.db.id}"
    w.send.assert_not_awaited()


@pytest.mark.anyio
async def test_existing_transcript_skips_download_and_transcription(audio_worker):
    w = audio_worker
    w.db.transcript = "Saved transcript"
    w.db.media_id = None  # Reuse does not depend on still-accessible media.
    await process(w)
    w.download.assert_not_awaited()
    w.provider.assert_not_called()
    w.transcribe.assert_not_awaited()
    assert w.graph.await_args.args == ("Saved transcript",)
    assert len(w.commits) == 1


@pytest.mark.anyio
async def test_generation_retry_reuses_durable_transcript(audio_worker):
    w = audio_worker
    w.graph.side_effect = AIProviderError("generation failed")
    with pytest.raises(AIProviderError):
        await process(w)
    assert w.db.transcript == "Spoken request"
    assert w.db.generated_reply is None
    assert w.events == []
    assert len(w.commits) == 1

    w.graph.side_effect = None
    await process(w)
    w.download.assert_awaited_once()
    w.transcribe.assert_awaited_once()
    assert w.graph.await_count == 2
    assert len(w.events) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["media", "transcription", "empty_transcript"])
async def test_audio_failure_never_invokes_graph_or_persists(audio_worker, stage):
    w = audio_worker
    if stage == "media":
        w.download.side_effect = WhatsAppMediaError("download failed")
    elif stage == "transcription":
        w.transcribe.side_effect = AIProviderError("transcription failed")
    else:
        w.transcribe.return_value = AITranscription("  ", "gemini", "test-model")
    with pytest.raises((WhatsAppMediaError, AIProviderError)):
        await process(w)
    w.graph.assert_not_awaited()
    w.send.assert_not_awaited()
    assert w.db.transcript is None
    assert w.db.transcribed_at is None
    assert w.db.generated_reply is None
    assert w.commits == []
    assert w.events == []


@pytest.mark.anyio
async def test_saved_audio_reply_skips_every_generation_stage(audio_worker):
    w = audio_worker
    w.db.generated_reply = "Saved reply"
    await process(w)
    w.download.assert_not_awaited()
    w.provider.assert_not_called()
    w.graph.assert_not_awaited()
    assert w.commits == []


@pytest.mark.anyio
async def test_audio_delivery_retry_only_sends_saved_reply(audio_worker):
    w = audio_worker
    w.db.generated_reply = "Saved reply"
    w.send.side_effect = WhatsAppSendError("delivery failed")
    with pytest.raises(WhatsAppSendError):
        await tasks._send_whatsapp_reply("whatsapp", w.db.external_id)
    assert w.db.processed_at is None
    w.send.side_effect = None
    await tasks._send_whatsapp_reply("whatsapp", w.db.external_id)
    w.download.assert_not_awaited()
    w.transcribe.assert_not_awaited()
    w.graph.assert_not_awaited()
    assert w.db.generated_reply == "Saved reply"
    assert w.db.processed_at is not None
    assert w.send.await_count == 2
    w.send.assert_awaited_with(to=w.db.sender_id, body="Saved reply")


@pytest.mark.anyio
@pytest.mark.parametrize("completed", [False, True])
async def test_rechecks_concurrent_progress_after_transcript_commit(
    audio_worker, monkeypatch, completed,
):
    w = audio_worker
    original_commit = w.session.commit

    async def commit_with_competing_worker(session):
        await original_commit(session)
        w.db.generated_reply = "Other worker reply"
        if completed:
            w.db.processed_at = object()

    monkeypatch.setattr(w.session, "commit", commit_with_competing_worker)
    await process(w)
    w.graph.assert_not_awaited()
    assert w.db.generated_reply == "Other worker reply"
    assert len(w.commits) == 1
    assert len(w.reads) == 2


@pytest.mark.anyio
async def test_failed_transcript_commit_does_not_start_graph(audio_worker, monkeypatch):
    w = audio_worker
    monkeypatch.setattr(w.session, "commit", AsyncMock(side_effect=RuntimeError("DB failed")))
    with pytest.raises(RuntimeError, match="DB failed"):
        await process(w)
    assert w.db.transcript is None
    w.graph.assert_not_awaited()
    assert w.events == []


@pytest.mark.anyio
@pytest.mark.parametrize("field,value", [("media_id", None), ("media_mime_type", None), ("media_mime_type", "image/png")])
async def test_audio_requires_metadata_before_download(audio_worker, field, value):
    w = audio_worker
    setattr(w.db, field, value)
    with pytest.raises(WhatsAppMediaError):
        await process(w)
    w.download.assert_not_awaited()
    w.transcribe.assert_not_awaited()
    w.graph.assert_not_awaited()


def test_retry_boundaries_remain_separate():
    assert tasks.process_message.autoretry_for == (AIProviderError, WhatsAppMediaError)
    assert tasks.send_whatsapp_reply.autoretry_for == (WhatsAppSendError,)
