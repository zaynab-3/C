import copy
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

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
