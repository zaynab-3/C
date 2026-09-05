from enum import StrEnum
from typing import Any

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from c_backend.models import Message, OutboxEvent
from c_backend.schemas.whatsapp import NormalizedMessage


class SaveMessageResult(StrEnum):
    STORED = "stored"
    DUPLICATE = "duplicate"


async def save_message(
    session: AsyncSession,
    message: NormalizedMessage,
    raw_payload: dict[str, Any],
) -> SaveMessageResult:
    record = Message(
        channel=message.channel,
        external_id=message.external_id,
        sender_id=message.sender_id,
        content_type=message.content_type,
        content=message.content,
        media_id=message.media_id,
        media_mime_type=message.media_mime_type,
        media_sha256=message.media_sha256,
        media_filename=message.media_filename,
        media_is_voice=message.media_is_voice,
        received_at=message.received_at,
        raw_payload=raw_payload,
    )

    session.add(record)

    try:
        # Force the message INSERT first, but DO NOT commit yet.
        # This lets us detect duplicate WhatsApp message IDs before
        # creating the matching outbox event.
        await session.flush()

    except IntegrityError as exc:
        await session.rollback()

        if (
            isinstance(exc.orig, UniqueViolation)
            and exc.orig.diag.constraint_name
            == "uq_messages_channel_external_id"
        ):
            return SaveMessageResult.DUPLICATE

        raise

    outbox_event = OutboxEvent(
        event_key=(
            f"process_message:"
            f"{message.channel}:"
            f"{message.external_id}"
        ),
        event_type="process_message",
        payload={
            "channel": message.channel,
            "external_id": message.external_id,
        },
    )

    session.add(outbox_event)

    try:
        # Message + outbox event become durable together.
        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return SaveMessageResult.STORED
