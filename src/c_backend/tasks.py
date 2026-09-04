import asyncio

from sqlalchemy import select

from c_backend.celery_app import celery_app
from c_backend.db import AsyncSessionLocal, engine
from c_backend.models import Message


async def _process_message(
    channel: str,
    external_id: str,
) -> str:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(
                Message.channel == channel,
                Message.external_id == external_id,
            )
        )

        message = result.scalar_one_or_none()

        if message is None:
            raise ValueError(
                f"Message not found: {channel}/{external_id}"
            )

        print(
            f"C worker processing: "
            f"{message.channel} / "
            f"{message.external_id} / "
            f"{message.content}"
        )

        message_id = str(message.id)

    await engine.dispose()

    return f"processed message {message_id}"


@celery_app.task(name="c.process_message")
def process_message(
    channel: str,
    external_id: str,
) -> str:
    return asyncio.run(
        _process_message(
            channel=channel,
            external_id=external_id,
        )
    )
