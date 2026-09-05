from typing import Any

import httpx

from c_backend.config import get_settings


GRAPH_API_VERSION = "v26.0"


class WhatsAppSendError(RuntimeError):
    pass


async def send_whatsapp_template(
    to: str,
    template_name: str,
    language_code: str = "en_US",
) -> str:
    settings = get_settings()

    if not settings.whatsapp_access_token:
        raise WhatsAppSendError(
            "WHATSAPP_ACCESS_TOKEN is not configured"
        )

    if not settings.whatsapp_phone_number_id:
        raise WhatsAppSendError(
            "WHATSAPP_PHONE_NUMBER_ID is not configured"
        )

    url = (
        f"https://graph.facebook.com/"
        f"{GRAPH_API_VERSION}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code,
            },
        },
    }

    headers = {
        "Authorization": (
            f"Bearer {settings.whatsapp_access_token}"
        ),
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise WhatsAppSendError(
            f"Meta WhatsApp API returned "
            f"{response.status_code}: {response.text}"
        ) from exc

    data = response.json()
    messages = data.get("messages", [])

    if not messages or not messages[0].get("id"):
        raise WhatsAppSendError(
            "Meta accepted the request but returned no message ID"
        )

    return str(messages[0]["id"])
