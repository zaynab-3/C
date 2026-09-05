import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from c_backend.celery_app import celery_app
from c_backend.db import AsyncSessionLocal, engine
from c_backend.models import Message, OutboxEvent
from c_backend.whatsapp_client import send_whatsapp_text


async def _process_message(
    channel: str,
    external_id: str,
) -> str:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Message)
                .where(
                    Message.channel == channel,
                    Message.external_id == external_id,
                )
                .with_for_update()
            )

            message = result.scalar_one_or_none()

            if message is None:
                raise ValueError(
                    f"Message not found: {channel}/{external_id}"
                )

            message_id = str(message.id)

            if message.processed_at is not None:
                print(
                    f"C worker skipped already processed message: "
                    f"{channel} / {external_id}"
                )
                return f"already processed message {message_id}"

            print(
                f"C worker processing: "
                f"{message.channel} / "
                f"{message.external_id} / "
                f"{message.content}"
            )

            outbound_id = None

            if channel == "whatsapp":
                outbound_id = await send_whatsapp_text(
                    to=message.sender_id,
                    body="C received your message automatically.",
                )

                print(
                    f"C automatic WhatsApp reply sent: "
                    f"{outbound_id}"
                )

            message.processed_at = datetime.now(timezone.utc)
            message.outbound_external_id = outbound_id

            await session.commit()

            return f"processed message {message_id}"

    finally:
        await engine.dispose()


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


async def _dispatch_outbox_batch(
    limit: int = 25,
) -> str:
    published = 0
    failed = 0

    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            result = await session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "pending",
                    OutboxEvent.available_at <= now,
                )
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )

            events = list(result.scalars())

            for event in events:
                event.attempts += 1

                try:
                    if event.event_type != "process_message":
                        raise ValueError(
                            f"Unsupported outbox event: "
                            f"{event.event_type}"
                        )

                    channel = event.payload.get("channel")
                    external_id = event.payload.get(
                        "external_id"
                    )

                    if not isinstance(channel, str):
                        raise ValueError(
                            "Outbox event has invalid channel"
                        )

                    if not isinstance(external_id, str):
                        raise ValueError(
                            "Outbox event has invalid external_id"
                        )

                    process_message.delay(
                        channel,
                        external_id,
                    )

                except Exception as exc:
                    failed += 1

                    event.last_error = str(exc)[:2000]

                    delay_seconds = min(
                        60,
                        2 ** min(event.attempts, 5),
                    )

                    event.available_at = (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=delay_seconds)
                    )

                else:
                    published += 1

                    event.status = "published"
                    event.published_at = (
                        datetime.now(timezone.utc)
                    )
                    event.last_error = None

            await session.commit()

        return (
            f"published={published} "
            f"failed={failed}"
        )

    finally:
        await engine.dispose()


@celery_app.task(name="c.dispatch_outbox")
def dispatch_outbox() -> str:
    return asyncio.run(
        _dispatch_outbox_batch()
    )
