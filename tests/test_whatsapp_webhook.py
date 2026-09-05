import copy
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest

from fastapi.testclient import TestClient

import c_backend.main as main_module
from c_backend.db import get_db_session
from c_backend.repositories.messages import SaveMessageResult


client = TestClient(main_module.app)

TEST_VERIFY_TOKEN = "test-verify-token"
TEST_APP_SECRET = "test-app-secret"
AUTHORIZED_SENDER = "96170123456"


class FakeSettings:
    whatsapp_verify_token = TEST_VERIFY_TOKEN
    whatsapp_app_secret = TEST_APP_SECRET
    whatsapp_allowed_senders = {AUTHORIZED_SENDER}


async def fake_db_session():
    yield object()


main_module.app.dependency_overrides[get_db_session] = fake_db_session


VALID_META_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "waba123",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [
                            {
                                "from": AUTHORIZED_SENDER,
                                "id": "wamid.test.001",
                                "timestamp": "1788600000",
                                "type": "text",
                                "text": {
                                    "body": "Hello C"
                                },
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


def use_test_settings(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: FakeSettings(),
    )


def signed_post(payload: dict):
    body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = (
        "sha256="
        + hmac.new(
            TEST_APP_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    return client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )


def test_new_webhook_is_stored_and_queued(monkeypatch):
    use_test_settings(monkeypatch)

    save_mock = AsyncMock(
        return_value=SaveMessageResult.STORED
    )
    monkeypatch.setattr(
        main_module,
        "save_message",
        save_mock,
    )

    response = signed_post(VALID_META_PAYLOAD)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "accepted"
    assert data["messages"] == 1
    assert data["stored"] == 1
    assert data["duplicates"] == 0
    assert data["ignored"] == 0
    assert data["queued"] == 1


def test_duplicate_webhook_is_not_queued(monkeypatch):
    use_test_settings(monkeypatch)

    save_mock = AsyncMock(
        return_value=SaveMessageResult.DUPLICATE
    )
    monkeypatch.setattr(
        main_module,
        "save_message",
        save_mock,
    )

    response = signed_post(VALID_META_PAYLOAD)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "accepted"
    assert data["messages"] == 1
    assert data["stored"] == 0
    assert data["duplicates"] == 1
    assert data["ignored"] == 0
    assert data["queued"] == 0



def test_unauthorized_sender_is_ignored(monkeypatch):
    use_test_settings(monkeypatch)

    save_mock = AsyncMock()
    monkeypatch.setattr(
        main_module,
        "save_message",
        save_mock,
    )

    payload = copy.deepcopy(VALID_META_PAYLOAD)
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = (
        "96179999999"
    )

    response = signed_post(payload)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "accepted"
    assert data["messages"] == 1
    assert data["stored"] == 0
    assert data["duplicates"] == 0
    assert data["ignored"] == 1
    assert data["queued"] == 0

    save_mock.assert_not_called()


def test_invalid_webhook_returns_422(monkeypatch):
    use_test_settings(monkeypatch)

    invalid_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "id": "wamid.test.001",
                                    "timestamp": "1788600000",
                                    "type": "text",
                                    "text": {
                                        "body": "Hello C"
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    response = signed_post(invalid_payload)

    assert response.status_code == 422


def test_meta_webhook_verification_success(monkeypatch):
    use_test_settings(monkeypatch)

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TEST_VERIFY_TOKEN,
            "hub.challenge": "654321",
        },
    )

    assert response.status_code == 200
    assert response.text == "654321"


def test_meta_webhook_verification_rejects_wrong_token(
    monkeypatch,
):
    use_test_settings(monkeypatch)

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "654321",
        },
    )

    assert response.status_code == 403


def test_post_rejects_missing_signature(monkeypatch):
    use_test_settings(monkeypatch)

    response = client.post(
        "/webhooks/whatsapp",
        json=VALID_META_PAYLOAD,
    )

    assert response.status_code == 401


def test_post_rejects_invalid_signature(monkeypatch):
    use_test_settings(monkeypatch)

    response = client.post(
        "/webhooks/whatsapp",
        json=VALID_META_PAYLOAD,
        headers={
            "X-Hub-Signature-256": "sha256=wrong",
        },
    )

    assert response.status_code == 401


def audio_payload():
    payload = copy.deepcopy(VALID_META_PAYLOAD)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message.pop("text")
    message.update(type="audio", audio={
        "id": "media-123", "mime_type": "audio/ogg; codecs=opus",
        "sha256": "test-sha256", "voice": True, "future_field": "ignored",
    })
    return payload


@pytest.mark.parametrize("result", [SaveMessageResult.STORED, SaveMessageResult.DUPLICATE])
def test_audio_webhook_normalizes_and_handles_duplicates(monkeypatch, result):
    use_test_settings(monkeypatch)
    save = AsyncMock(return_value=result)
    monkeypatch.setattr(main_module, "save_message", save)
    response = signed_post(audio_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == 1
    assert data["stored"] == int(result == SaveMessageResult.STORED)
    assert data["queued"] == int(result == SaveMessageResult.STORED)
    assert data["duplicates"] == int(result == SaveMessageResult.DUPLICATE)
    message = save.await_args.kwargs["message"]
    assert message.external_id == "wamid.test.001"
    assert message.sender_id == AUTHORIZED_SENDER
    assert message.received_at.timestamp() == 1788600000
    assert message.content_type == "audio"
    assert message.content is None
    assert message.media_id == "media-123"
    assert message.media_mime_type == "audio/ogg; codecs=opus"
    assert message.media_sha256 == "test-sha256"
    assert message.media_is_voice is True
    assert message.media_filename is None


def test_audio_sender_authorization_remains_required(monkeypatch):
    use_test_settings(monkeypatch)
    save = AsyncMock()
    monkeypatch.setattr(main_module, "save_message", save)
    payload = audio_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = "unauthorized-test-sender"
    response = signed_post(payload)
    assert response.status_code == 200
    assert response.json()["ignored"] == 1
    save.assert_not_awaited()


@pytest.mark.parametrize("message_type", ["image", "document", "video", "sticker"])
def test_unsupported_inbound_types_remain_ignored(monkeypatch, message_type):
    use_test_settings(monkeypatch)
    save = AsyncMock()
    monkeypatch.setattr(main_module, "save_message", save)
    payload = copy.deepcopy(VALID_META_PAYLOAD)
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = message_type
    response = signed_post(payload)
    assert response.status_code == 200
    assert response.json()["messages"] == 0
    save.assert_not_awaited()


def test_audio_voice_flag_is_optional(monkeypatch):
    use_test_settings(monkeypatch)
    save = AsyncMock(return_value=SaveMessageResult.STORED)
    monkeypatch.setattr(main_module, "save_message", save)
    payload = audio_payload()
    del payload["entry"][0]["changes"][0]["value"]["messages"][0]["audio"]["voice"]
    assert signed_post(payload).status_code == 200
    assert save.await_args.kwargs["message"].media_is_voice is None
