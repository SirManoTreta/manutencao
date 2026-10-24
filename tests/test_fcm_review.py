"""Payload budget regressions: JSON escaping also consumes transport bytes."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("character", ['"', "\\", "\x01"], ids=["quotes", "backslashes", "control"])
def test_escaped_problem_stays_within_json_payload_budget(
    client, headers, seed, database, monkeypatch, character,
):
    from app import fcm
    from app.models import Ticket
    from firebase_admin import messaging

    assert client.post("/api/v1/push/register", headers=headers, json={
        "fcm_token": "phone-escaped-json-review", "platform": "ios",
    }).status_code == 200
    with database.session() as session:
        session.get(Ticket, seed.tickets[0]).problem = character * 4000
        session.commit()
    sender = Mock(return_value=SimpleNamespace(responses=[
        SimpleNamespace(success=True, exception=None),
    ]))
    monkeypatch.setattr(messaging, "send_each_for_multicast", sender)
    monkeypatch.setattr(fcm, "_get_firebase_app", lambda: "firebase-app-mock")

    fcm._send_ticket_notification(seed.tickets[0])
    message = sender.call_args.args[0]
    encoded = messaging._MessagingService.encode_message(messaging.Message(
        token=message.tokens[0], data=message.data, notification=message.notification,
        android=message.android, apns=message.apns,
    ))
    assert len(json.dumps(encoded, ensure_ascii=False).encode("utf-8")) <= 4096
    assert message.data["ticket_id"] == str(seed.tickets[0])
    assert message.data["type"] == "new_ticket"
