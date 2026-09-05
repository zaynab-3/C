from types import SimpleNamespace

import httpx
import pytest

from c_backend import whatsapp_media as media


URL = "https://lookaside.fbsbx.com/test-audio"


@pytest.fixture
def install_transport(monkeypatch):
    monkeypatch.setattr(media, "get_settings", lambda: SimpleNamespace(
        whatsapp_access_token="dummy-media-token",
    ))
    real_client = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(media.httpx, "AsyncClient", lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler), **kwargs,
        ))
    return install


@pytest.mark.anyio
async def test_resolves_fresh_url_and_authenticates_both_requests(install_transport):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer dummy-media-token"
        if request.url.host == "graph.facebook.com":
            assert request.url.path == f"/{media.GRAPH_API_VERSION}/123"
            return httpx.Response(200, json={"url": URL})
        assert str(request.url) == URL
        return httpx.Response(200, content=b"voice note")

    install_transport(handler)
    assert await media.download_whatsapp_audio("123") == b"voice note"
    assert await media.download_whatsapp_audio("123") == b"voice note"
    assert len(requests) == 4  # Each invocation resolves a fresh URL.


@pytest.mark.anyio
@pytest.mark.parametrize("size", [0, 14 * 1024 * 1024, 14 * 1024 * 1024 + 1])
async def test_audio_size_limit(install_transport, size):
    assert media.MAX_DOWNLOADED_AUDIO_BYTES == 14 * 1024 * 1024

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            remaining = size
            while remaining:
                chunk = min(65536, remaining)
                yield b"a" * chunk
                remaining -= chunk

    def handler(request):
        if request.url.host == "graph.facebook.com":
            return httpx.Response(200, json={"url": URL})
        return httpx.Response(200, stream=Stream())  # No Content-Length.

    install_transport(handler)
    if size == media.MAX_DOWNLOADED_AUDIO_BYTES:
        assert len(await media.download_whatsapp_audio("123")) == size
    else:
        with pytest.raises(media.WhatsAppMediaError):
            await media.download_whatsapp_audio("123")


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["metadata", "download", "timeout", "invalid_json"])
async def test_media_errors_are_sanitized(install_transport, stage):
    def handler(request):
        is_metadata = request.url.host == "graph.facebook.com"
        if stage == "timeout":
            raise httpx.ReadTimeout("dummy-media-token " + URL, request=request)
        if stage == "invalid_json":
            return httpx.Response(200, content=b"not json")
        if (stage == "metadata" and is_metadata) or (stage == "download" and not is_metadata):
            return httpx.Response(403, text="dummy-media-token " + URL)
        return httpx.Response(200, json={"url": URL})

    install_transport(handler)
    with pytest.raises(media.WhatsAppMediaError) as caught:
        await media.download_whatsapp_audio("123")
    assert "dummy-media-token" not in str(caught.value)
    assert URL not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.anyio
@pytest.mark.parametrize("url", [None, "", "http://lookaside.fbsbx.com/audio", "https://example.com/audio", "https://fbsbx.com.example.com/audio", "https://user:pass@lookaside.fbsbx.com/audio"])
async def test_missing_or_untrusted_url_is_rejected(install_transport, url):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"url": url})

    install_transport(handler)
    with pytest.raises(media.WhatsAppMediaError):
        await media.download_whatsapp_audio("123")
    assert len(requests) == 1


@pytest.mark.anyio
async def test_missing_media_id_is_rejected_before_settings(monkeypatch):
    def no_settings():
        raise AssertionError("Settings should not be loaded")
    monkeypatch.setattr(media, "get_settings", no_settings)
    with pytest.raises(media.WhatsAppMediaError):
        await media.download_whatsapp_audio(" ")


@pytest.mark.anyio
async def test_missing_access_token(monkeypatch):
    monkeypatch.setattr(media, "get_settings", lambda: SimpleNamespace(whatsapp_access_token=None))
    with pytest.raises(media.WhatsAppMediaError, match="not configured"):
        await media.download_whatsapp_audio("123")
