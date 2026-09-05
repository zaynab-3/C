import secrets
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from c_backend.config import get_settings
from c_backend.db import get_db_session
from c_backend.repositories.messages import (
    SaveMessageResult,
    save_message,
)
from c_backend.schemas.whatsapp import (
    MockWhatsAppTextEvent,
    NormalizedMessage,
    WhatsAppWebhookResponse,
)
from c_backend.tasks import process_message


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


app = FastAPI(
    title="C Backend",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="c-backend",
    )


@app.get(
    "/webhooks/whatsapp",
    response_class=PlainTextResponse,
)
async def verify_whatsapp_webhook(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    settings = get_settings()

    valid_mode = mode == "subscribe"
    valid_token = secrets.compare_digest(
        verify_token,
        settings.whatsapp_verify_token,
    )

    if not valid_mode or not valid_token:
        raise HTTPException(
            status_code=403,
            detail="Webhook verification failed",
        )

    return PlainTextResponse(
        content=challenge,
        status_code=200,
    )


@app.post(
    "/webhooks/whatsapp",
    response_model=WhatsAppWebhookResponse,
)
async def receive_whatsapp_message(
    event: MockWhatsAppTextEvent,
    session: AsyncSession = Depends(get_db_session),
) -> WhatsAppWebhookResponse:
    message = NormalizedMessage(
        external_id=event.message_id,
        channel="whatsapp",
        sender_id=event.sender,
        content_type=event.type,
        content=event.text,
        received_at=event.timestamp,
    )

    result = await save_message(
        session=session,
        message=message,
        raw_payload=event.model_dump(mode="json"),
    )

    if result == SaveMessageResult.STORED:
        process_message.delay(
            message.channel,
            message.external_id,
        )

    return WhatsAppWebhookResponse(
        status=result.value,
        message=message,
    )
