"""Resolve a fresh Meta media URL and download bounded audio into memory."""

from urllib.parse import quote

import httpx

from c_backend.config import get_settings
from c_backend.whatsapp_client import GRAPH_API_VERSION


# Leave room for base64 encoding and request overhead below 20 MB inline.
MAX_DOWNLOADED_AUDIO_BYTES = 14 * 1024 * 1024


class WhatsAppMediaError(RuntimeError):
    """Media retrieval failed; safe to surface without request details."""


async def download_whatsapp_audio(media_id: str) -> bytes:
    if not media_id or not media_id.strip():
        raise WhatsAppMediaError("Audio media ID is required")

    settings = get_settings()
    if not settings.whatsapp_access_token:
        raise WhatsAppMediaError("WhatsApp media access is not configured")

    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    metadata_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{quote(media_id.strip(), safe='')}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            metadata_response = await client.get(metadata_url, headers=headers)
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            url = metadata.get("url") if isinstance(metadata, dict) else None
            if not isinstance(url, str) or not url.strip():
                raise WhatsAppMediaError("Meta returned no media URL")

            download_url = httpx.URL(url)
            # Send the bearer token only to Meta's HTTPS media hosts.
            trusted_host = any(
                download_url.host == domain
                or download_url.host.endswith("." + domain)
                for domain in ("facebook.com", "fbcdn.net", "fbsbx.com")
            )
            if (
                download_url.scheme != "https"
                or not trusted_host
                or download_url.userinfo
                or download_url.port not in (None, 443)
            ):
                raise WhatsAppMediaError("Meta returned an invalid media URL")

            async with client.stream("GET", download_url, headers=headers) as response:
                response.raise_for_status()
                # Stream and count actual bytes: Content-Length may be absent or wrong.
                audio = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(audio) + len(chunk) > MAX_DOWNLOADED_AUDIO_BYTES:
                        raise WhatsAppMediaError("Audio exceeds the 14 MiB limit")
                    audio.extend(chunk)
                if not audio:
                    raise WhatsAppMediaError("Meta returned empty audio")
                return bytes(audio)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        # Do not include response bodies, temporary URLs or underlying exceptions.
        raise WhatsAppMediaError("Meta media retrieval failed") from None
