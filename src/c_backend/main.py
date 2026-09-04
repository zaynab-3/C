from typing import Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
