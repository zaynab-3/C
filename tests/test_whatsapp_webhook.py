import hashlib
import hmac
import json
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

import c_backend.main as main_module
from c_backend.db import get_db_session
from c_backend.repositories.messages import SaveMessageResult


client = TestClient(main_module.app)

TEST_VERIFY_TOKEN = "test-verify-token"
TEST_APP_SECRET = "test-app-secret"


class FakeSettings:
    whatsapp_verify_token = TEST_VERIFY_TOKEN
    whatsapp_app_secret = TEST_APP_SECRET


async def fake_db_session():
    yield object()


main_module.app.dependency_overrides[get_db_session] = fake_db_session


VALID_PAYLOAD = {
    "message_id": "wamid.test.001",
    "sender": "96170123456",
    "type": "text",
    "text": "Hello C",
    "timestamp": "2026-09-05T12:00:00+03:00",
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

    save_mock = AsyncMock(return_value=SaveMessageResult.STORED)
    delay_mock = Mock()

    monkeypatch.setattr(main_module, "save_message", save_mock)
    monkeypatch.setattr(
        main_module.process_message,
        "delay",
        delay_mock,
    )

    response = signed_post(VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "stored"

    delay_mock.assert_called_once_with(
        "whatsapp",
        "wamid.test.001",
    )


def test_duplicate_webhook_is_not_queued(monkeypatch):
    use_test_settings(monkeypatch)

    save_mock = AsyncMock(
        return_value=SaveMessageResult.DUPLICATE
    )
    delay_mock = Mock()

    monkeypatch.setattr(main_module, "save_message", save_mock)
    monkeypatch.setattr(
        main_module.process_message,
        "delay",
        delay_mock,
    )

    response = signed_post(VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"

    delay_mock.assert_not_called()


def test_invalid_webhook_returns_422(monkeypatch):
    use_test_settings(monkeypatch)

    invalid_payload = {
        **VALID_PAYLOAD,
        "sender": "not-a-phone-number",
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
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 401


def test_post_rejects_invalid_signature(monkeypatch):
    use_test_settings(monkeypatch)

    response = client.post(
        "/webhooks/whatsapp",
        json=VALID_PAYLOAD,
        headers={
            "X-Hub-Signature-256": "sha256=wrong",
        },
    )

    assert response.status_code == 401
