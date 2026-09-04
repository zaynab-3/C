from enum import StrEnum
from typing import Any

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from c_backend.models import Message
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
        received_at=message.received_at,
        raw_payload=raw_payload,
    )

    session.add(record)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        if (
            isinstance(exc.orig, UniqueViolation)
            and exc.orig.diag.constraint_name
            == "uq_messages_channel_external_id"
        ):
            return SaveMessageResult.DUPLICATE

        raise

    return SaveMessageResult.STORED
