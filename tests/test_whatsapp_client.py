import json

import httpx
import pytest

import c_backend.whatsapp_client as whatsapp_client
from c_backend.whatsapp_client import (
    WhatsAppSendError,
    send_whatsapp_template,
)


class FakeSettings:
    whatsapp_access_token = "test-access-token"
    whatsapp_phone_number_id = "123456789"


def use_test_settings(monkeypatch):
    monkeypatch.setattr(
        whatsapp_client,
        "get_settings",
        lambda: FakeSettings(),
    )


@pytest.mark.anyio
async def test_send_whatsapp_template_success(monkeypatch):
    use_test_settings(monkeypatch)

    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://graph.facebook.com/"
            "v26.0/123456789/messages"
        )

        assert request.headers["Authorization"] == (
            "Bearer test-access-token"
        )

        payload = json.loads(request.content)

        assert payload == {
            "messaging_product": "whatsapp",
            "to": "96170123456",
            "type": "template",
            "template": {
                "name": "hello_world",
                "language": {
                    "code": "en_US",
                },
            },
        }

        return httpx.Response(
            200,
            json={
                "messages": [
                    {
                        "id": "wamid.test.success",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    monkeypatch.setattr(
        whatsapp_client.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(
            transport=transport,
            **kwargs,
        ),
    )

    message_id = await send_whatsapp_template(
        to="96170123456",
        template_name="hello_world",
    )

    assert message_id == "wamid.test.success"


@pytest.mark.anyio
async def test_send_requires_access_token(monkeypatch):
    class MissingTokenSettings:
        whatsapp_access_token = None
        whatsapp_phone_number_id = "123456789"

    monkeypatch.setattr(
        whatsapp_client,
        "get_settings",
        lambda: MissingTokenSettings(),
    )

    with pytest.raises(
        WhatsAppSendError,
        match="WHATSAPP_ACCESS_TOKEN",
    ):
        await send_whatsapp_template(
            to="96170123456",
            template_name="hello_world",
        )


@pytest.mark.anyio
async def test_send_requires_phone_number_id(monkeypatch):
    class MissingPhoneSettings:
        whatsapp_access_token = "test-access-token"
        whatsapp_phone_number_id = None

    monkeypatch.setattr(
        whatsapp_client,
        "get_settings",
        lambda: MissingPhoneSettings(),
    )

    with pytest.raises(
        WhatsAppSendError,
        match="WHATSAPP_PHONE_NUMBER_ID",
    ):
        await send_whatsapp_template(
            to="96170123456",
            template_name="hello_world",
        )


@pytest.mark.anyio
async def test_meta_error_becomes_whatsapp_send_error(
    monkeypatch,
):
    use_test_settings(monkeypatch)

    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            request=request,
            json={
                "error": {
                    "message": "Bad request",
                }
            },
        )

    transport = httpx.MockTransport(handler)

    monkeypatch.setattr(
        whatsapp_client.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(
            transport=transport,
            **kwargs,
        ),
    )

    with pytest.raises(
        WhatsAppSendError,
        match="Meta WhatsApp API returned 400",
    ):
        await send_whatsapp_template(
            to="96170123456",
            template_name="hello_world",
        )
