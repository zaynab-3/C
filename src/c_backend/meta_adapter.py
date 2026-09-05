from datetime import datetime, timezone

from c_backend.schemas.meta_whatsapp import MetaWhatsAppWebhook
from c_backend.schemas.whatsapp import NormalizedMessage


def extract_inbound_messages(
    payload: MetaWhatsAppWebhook,
) -> list[NormalizedMessage]:
    messages: list[NormalizedMessage] = []

    for entry in payload.entry:
        for change in entry.changes:
            if change.field != "messages":
                continue

            if not change.value.messages:
                continue

            for message in change.value.messages:
                if message.type == "text" and message.text is not None:
                    content = {"content_type": "text", "content": message.text.body}
                elif message.type == "audio" and message.audio is not None:
                    content = {
                        "content_type": "audio",
                        "content": None,
                        "media_id": message.audio.id,
                        "media_mime_type": message.audio.mime_type,
                        "media_sha256": message.audio.sha256,
                        "media_is_voice": message.audio.voice,
                    }
                else:
                    continue

                received_at = datetime.fromtimestamp(
                    int(message.timestamp),
                    tz=timezone.utc,
                )

                messages.append(
                    NormalizedMessage(
                        external_id=message.id,
                        channel="whatsapp",
                        sender_id=message.sender,
                        **content,
                        received_at=received_at,
                    )
                )

    return messages
