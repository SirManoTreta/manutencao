import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select


def test_device_registration_is_idempotent_and_logout_removes_its_devices(client, headers, database):
    from app.models import FCMDevice

    payload = {"token": "fcm-dispositivo-de-teste", "platform": "android"}
    for _ in range(2):
        response = client.post("/api/v1/devices", headers=headers, json=payload)
        assert response.status_code == 201
        assert "fcm-dispositivo-de-teste" not in response.text
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 1
        assert session.scalar(select(FCMDevice)).platform == "android"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 0


def test_device_unregistration_is_scoped_to_current_session(client, login, database):
    from app.models import FCMDevice

    owner = login("tecnico")
    other = login("colega")
    payload = {"token": "fcm-dispositivo-privado"}
    assert client.post("/api/v1/devices", headers=owner, json={**payload, "platform": "ios"}).status_code == 201
    assert client.request("DELETE", "/api/v1/devices", headers=other, json=payload).status_code == 204
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 1
    assert client.request("DELETE", "/api/v1/devices", headers=owner, json=payload).status_code == 204
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 0


@pytest.mark.parametrize("payload", [
    {"token": "", "platform": "android"},
    {"token": "token", "platform": "desktop"},
])
def test_device_input_validated(client, headers, payload):
    assert client.post("/api/v1/devices", headers=headers, json=payload).status_code == 422


@pytest.fixture
def firebase_mock(monkeypatch):
    """Firebase-shaped boundary, with no credentials, SDK or network required."""
    from app import fcm

    class UnregisteredError(Exception):
        pass

    messaging = SimpleNamespace(
        UnregisteredError=UnregisteredError,
        send_each_for_multicast=Mock(return_value=SimpleNamespace(responses=[
            SimpleNamespace(success=True, exception=None),
        ])),
    )
    for name in ("MulticastMessage", "Notification", "AndroidConfig", "AndroidNotification",
                 "APNSConfig", "APNSPayload", "Aps"):
        setattr(messaging, name, lambda **values: SimpleNamespace(**values))
    monkeypatch.setitem(sys.modules, "firebase_admin", SimpleNamespace(messaging=messaging))
    monkeypatch.setattr(fcm, "_get_firebase_app", lambda: "firebase-app-mock")
    return messaging


def test_fcm_delivery_has_deep_link_id_room_and_high_priority(client, headers, seed, firebase_mock):
    from app import fcm

    assert client.post("/api/v1/devices", headers=headers, json={
        "token": "fcm-token-deep-link", "platform": "android",
    }).status_code == 201
    fcm._send_ticket_notification(seed.tickets[0])
    message = firebase_mock.send_each_for_multicast.call_args.args[0]
    assert message.tokens == ["fcm-token-deep-link"]
    assert message.data["ticket_id"] == str(seed.tickets[0])
    assert message.data["type"] == "ticket_created"
    assert "7º Ano A" in message.notification.body
    assert "PC-SALA07" in message.notification.body
    assert "Projetor sem imagem" in message.notification.body
    assert message.android.priority == "high"
    assert message.android.notification.channel_id == "maintenance_tickets"


def test_unregistered_fcm_token_is_pruned(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import FCMDevice

    client.post("/api/v1/devices", headers=headers, json={"token": "expired-fcm-token", "platform": "android"})
    firebase_mock.send_each_for_multicast.return_value = SimpleNamespace(responses=[
        SimpleNamespace(success=False, exception=firebase_mock.UnregisteredError("Unregistered")),
    ])
    fcm._send_ticket_notification(seed.tickets[0])
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 0


def test_disabled_users_do_not_receive_fcm(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import User

    client.post("/api/v1/devices", headers=headers, json={"token": "inactive-fcm-token", "platform": "android"})
    with database.session() as session:
        session.get(User, seed.users["tecnico"]).is_active = False
        session.commit()
    fcm._send_ticket_notification(seed.tickets[0])
    firebase_mock.send_each_for_multicast.assert_not_called()


def test_fcm_failure_does_not_escape_background_boundary(application, monkeypatch):
    from app import fcm

    monkeypatch.setattr(fcm, "_send_ticket_notification", Mock(side_effect=RuntimeError("offline")))
    fcm._send_safely(1)


def test_fcm_disabled_needs_no_firebase_credentials(application, monkeypatch):
    from app import fcm

    monkeypatch.delenv("FIREBASE_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FCM_ENABLED", raising=False)
    assert fcm._get_firebase_app() is None


def test_fcm_expired_sessions_receive_no_notification(client, headers, seed, database, firebase_mock):
    from datetime import datetime, timedelta
    from app import fcm
    from app.models import MobileSession

    client.post("/api/v1/devices", headers=headers, json={"token": "session-expired-fcm", "platform": "android"})
    with database.session() as session:
        session.scalar(select(MobileSession)).expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
    fcm._send_ticket_notification(seed.tickets[0])
    firebase_mock.send_each_for_multicast.assert_not_called()


@pytest.mark.parametrize("problem,expected_new_tickets", [("Projetor sem imagem", 1), ("status_online", 0)])
def test_professor_protocol_keeps_web_push_and_adds_fcm_after_commit(
    client, seed, database, monkeypatch, problem, expected_new_tickets,
):
    from app import chamados_socket
    from app.models import Ticket

    events, web_notifications, fcm_ids = [], [], []
    monkeypatch.setattr(chamados_socket, "broadcast_from_thread", events.append)
    monkeypatch.setattr(chamados_socket, "enqueue_push", web_notifications.append)

    def assert_committed_then_enqueue(ticket_id):
        with database.session() as session:
            assert session.get(Ticket, ticket_id) is not None
        fcm_ids.append(ticket_id)

    monkeypatch.setattr(chamados_socket, "enqueue_ticket_push", assert_committed_then_enqueue)

    class Request:
        data = json.dumps({
            "nome": "PC-SALA07", "usuario": "professor.joao",
            "problema": problem, "diagnostico": {"rede": "ok"},
        }).encode("utf-8")

        def recv(self, _size):
            result, self.data = self.data, b""
            return result

    chamados_socket._TicketTCPHandler(Request(), ("127.0.0.1", 1), None)
    assert len(events) == expected_new_tickets
    assert len(web_notifications) == expected_new_tickets
    assert len(fcm_ids) == expected_new_tickets
    if expected_new_tickets:
        assert events[0]["ticket_id"] == fcm_ids[0]
        assert events[0]["type"] == "ticket_created"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Ticket)) == 3 + expected_new_tickets
