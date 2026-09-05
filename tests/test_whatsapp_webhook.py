from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

import c_backend.main as main_module
from c_backend.db import get_db_session
from c_backend.repositories.messages import SaveMessageResult


client = TestClient(main_module.app)


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


def test_new_webhook_is_stored_and_queued(monkeypatch):
    save_mock = AsyncMock(return_value=SaveMessageResult.STORED)
    delay_mock = Mock()

    monkeypatch.setattr(main_module, "save_message", save_mock)
    monkeypatch.setattr(
        main_module.process_message,
        "delay",
        delay_mock,
    )

    response = client.post(
        "/webhooks/whatsapp",
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "stored"

    delay_mock.assert_called_once_with(
        "whatsapp",
        "wamid.test.001",
    )


def test_duplicate_webhook_is_not_queued(monkeypatch):
    save_mock = AsyncMock(return_value=SaveMessageResult.DUPLICATE)
    delay_mock = Mock()

    monkeypatch.setattr(main_module, "save_message", save_mock)
    monkeypatch.setattr(
        main_module.process_message,
        "delay",
        delay_mock,
    )

    response = client.post(
        "/webhooks/whatsapp",
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"

    delay_mock.assert_not_called()


def test_invalid_webhook_returns_422():
    invalid_payload = {
        **VALID_PAYLOAD,
        "sender": "not-a-phone-number",
    }

    response = client.post(
        "/webhooks/whatsapp",
        json=invalid_payload,
    )

    assert response.status_code == 422


def test_meta_webhook_verification_success(monkeypatch):
    class FakeSettings:
        whatsapp_verify_token = "test-verify-token"

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: FakeSettings(),
    )

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "654321",
        },
    )

    assert response.status_code == 200
    assert response.text == "654321"


def test_meta_webhook_verification_rejects_wrong_token(monkeypatch):
    class FakeSettings:
        whatsapp_verify_token = "test-verify-token"

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: FakeSettings(),
    )

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "654321",
        },
    )

    assert response.status_code == 403
