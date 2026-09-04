import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from c_backend.db import AsyncSessionLocal, engine
from c_backend.models import Message
from c_backend.repositories.messages import save_message
from c_backend.schemas.whatsapp import NormalizedMessage


async def main() -> None:
    external_id = f"wamid.python-test.{uuid.uuid4()}"

    message = NormalizedMessage(
        external_id=external_id,
        channel="whatsapp",
        sender_id="96170123456",
        content_type="text",
        content="Hello from Python",
        received_at=datetime.now(timezone.utc),
    )

    raw_payload = {
        "message_id": external_id,
        "sender": "96170123456",
        "type": "text",
        "text": "Hello from Python",
    }

    async with AsyncSessionLocal() as session:
        first_result = await save_message(
            session=session,
            message=message,
            raw_payload=raw_payload,
        )

        second_result = await save_message(
            session=session,
            message=message,
            raw_payload=raw_payload,
        )

        count_result = await session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.channel == "whatsapp",
                Message.external_id == external_id,
            )
        )

        count = count_result.scalar_one()

        print(f"First save: {first_result}")
        print(f"Second save: {second_result}")
        print(f"Rows stored: {count}")

        await session.execute(
            delete(Message).where(
                Message.channel == "whatsapp",
                Message.external_id == external_id,
            )
        )
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=asyncio.SelectorEventLoop,
    )
