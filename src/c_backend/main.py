import secrets
from typing import Annotated, Literal

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from c_backend.config import get_settings
from c_backend.db import get_db_session
from c_backend.meta_adapter import extract_text_messages
from c_backend.repositories.messages import (
    SaveMessageResult,
    save_message,
)
from c_backend.schemas.meta_whatsapp import (
    MetaWebhookAck,
    MetaWhatsAppWebhook,
)
from c_backend.security import verify_meta_signature


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

    if not settings.whatsapp_verify_token:
        raise HTTPException(
            status_code=503,
            detail="Webhook verification is not configured",
        )

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


async def require_valid_meta_signature(
    request: Request,
    signature: Annotated[
        str | None,
        Header(alias="X-Hub-Signature-256"),
    ] = None,
) -> None:
    settings = get_settings()

    if not settings.whatsapp_app_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook signature verification is not configured",
        )

    body = await request.body()

    if not verify_meta_signature(
        body=body,
        signature=signature,
        app_secret=settings.whatsapp_app_secret,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )


@app.post(
    "/webhooks/whatsapp",
    response_model=MetaWebhookAck,
)
async def receive_whatsapp_message(
    request: Request,
    payload: MetaWhatsAppWebhook,
    _signature: None = Depends(require_valid_meta_signature),
    session: AsyncSession = Depends(get_db_session),
) -> MetaWebhookAck:
    settings = get_settings()
    raw_payload = await request.json()

    messages = extract_text_messages(payload)

    stored = 0
    duplicates = 0
    ignored = 0
    queued = 0

    for message in messages:
        if message.sender_id not in settings.whatsapp_allowed_senders:
            ignored += 1
            continue

        result = await save_message(
            session=session,
            message=message,
            raw_payload=raw_payload,
        )

        if result == SaveMessageResult.STORED:
            stored += 1

            queued += 1

        elif result == SaveMessageResult.DUPLICATE:
            duplicates += 1

    return MetaWebhookAck(
        status="accepted",
        messages=len(messages),
        stored=stored,
        duplicates=duplicates,
        ignored=ignored,
        queued=queued,
    )
