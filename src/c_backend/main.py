from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from c_backend.schemas.whatsapp import (
    MockWhatsAppTextEvent,
    NormalizedMessage,
)


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
    response_model=NormalizedMessage,
)
async def receive_whatsapp_message(
    event: MockWhatsAppTextEvent,
) -> NormalizedMessage:
    return NormalizedMessage(
        external_id=event.message_id,
        channel="whatsapp",
        sender_id=event.sender,
        content_type=event.type,
        content=event.text,
        received_at=event.timestamp,
    )
