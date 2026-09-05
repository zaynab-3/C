from datetime import datetime, timezone

from c_backend.schemas.meta_whatsapp import MetaWhatsAppWebhook
from c_backend.schemas.whatsapp import NormalizedMessage


def extract_text_messages(
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
                if message.type != "text":
                    continue

                if message.text is None:
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
                        content_type="text",
                        content=message.text.body,
                        received_at=received_at,
                    )
                )

    return messages
