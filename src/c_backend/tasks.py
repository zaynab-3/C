import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from c_backend.ai import AIProviderError, get_ai_provider
from c_backend.celery_app import celery_app
from c_backend.db import AsyncSessionLocal, engine
from c_backend.models import Message, OutboxEvent
from c_backend.whatsapp_client import (
    WhatsAppSendError,
    send_whatsapp_text,
)


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

            if channel != "whatsapp":
                message.processed_at = datetime.now(timezone.utc)
                await session.commit()
                return f"processed message {message_id}"

            if not message.content or not message.content.strip():
                raise ValueError(
                    "WhatsApp text message has no content"
                )

            if message.generated_reply:
                print(
                    f"C worker reused persisted AI reply: "
                    f"{channel} / {external_id}"
                )
                return f"reply already prepared for message {message_id}"

            print(
                f"C worker generating reply: "
                f"{message.channel} / "
                f"{message.external_id} / "
                f"{message.content}"
            )

            provider = get_ai_provider()
            ai_response = await provider.generate_text(
                message.content,
                system_prompt=(
                    "You are C, a reliable WhatsApp-first assistant. "
                    "Reply directly and concisely to the user's message. "
                    "Do not claim that you performed external actions. "
                    "Tool execution is not available at this stage."
                ),
            )

            message.generated_reply = ai_response.text
            message.ai_provider = ai_response.provider
            message.ai_model = ai_response.model
            message.ai_generated_at = datetime.now(timezone.utc)

            session.add(
                OutboxEvent(
                    event_key=f"send_whatsapp_reply:{message.id}",
                    event_type="send_whatsapp_reply",
                    payload={
                        "channel": channel,
                        "external_id": external_id,
                    },
                )
            )

            await session.commit()

            print(
                f"C persisted AI reply via "
                f"{ai_response.provider}/{ai_response.model}: "
                f"{channel} / {external_id}"
            )

            return f"prepared message {message_id}"

    finally:
        await engine.dispose()


@celery_app.task(
    name="c.process_message",
    autoretry_for=(AIProviderError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
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


async def _send_whatsapp_reply(
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
                    f"C sender skipped already delivered message: "
                    f"{channel} / {external_id}"
                )
                return f"already delivered message {message_id}"

            if channel != "whatsapp":
                raise ValueError(
                    f"Unsupported outbound channel: {channel}"
                )

            if not message.generated_reply:
                raise ValueError(
                    "Persisted WhatsApp reply is missing"
                )

            outbound_id = await send_whatsapp_text(
                to=message.sender_id,
                body=message.generated_reply,
            )

            message.processed_at = datetime.now(timezone.utc)
            message.outbound_external_id = outbound_id

            await session.commit()

            print(
                f"C persisted WhatsApp delivery: "
                f"{outbound_id}"
            )

            return f"delivered message {message_id}"

    finally:
        await engine.dispose()


@celery_app.task(
    name="c.send_whatsapp_reply",
    autoretry_for=(WhatsAppSendError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def send_whatsapp_reply(
    channel: str,
    external_id: str,
) -> str:
    return asyncio.run(
        _send_whatsapp_reply(
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

                    if event.event_type == "process_message":
                        process_message.delay(
                            channel,
                            external_id,
                        )
                    elif event.event_type == "send_whatsapp_reply":
                        send_whatsapp_reply.delay(
                            channel,
                            external_id,
                        )
                    else:
                        raise ValueError(
                            f"Unsupported outbox event: "
                            f"{event.event_type}"
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
