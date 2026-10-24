import json
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
    """Build real SDK messages, mock all delivery: no credential or network."""
    from app import fcm
    from firebase_admin import messaging

    monkeypatch.setattr(messaging, "send_each_for_multicast", Mock(
        return_value=SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)]),
    ))
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
    assert message.data["type"] == "new_ticket"
    assert "7º Ano A" in message.notification.body
    assert "PC-SALA07" in message.notification.body
    assert "Projetor sem imagem" in message.notification.body
    assert message.android.priority == "high"
    assert message.android.notification.channel_id == "maintenance_tickets"


def test_unregistered_fcm_token_is_deactivated(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import FCMDevice

    client.post("/api/v1/devices", headers=headers, json={"token": "expired-fcm-token", "platform": "android"})
    firebase_mock.send_each_for_multicast.return_value = SimpleNamespace(responses=[
        SimpleNamespace(success=False, exception=firebase_mock.UnregisteredError("Unregistered")),
    ])
    fcm._send_ticket_notification(seed.tickets[0])
    with database.session() as session:
        assert session.scalar(select(FCMDevice)).is_active is False


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


def test_inactive_device_does_not_receive_push(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import FCMDevice

    client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "device-opted-out"})
    client.post("/api/v1/push/unregister", headers=headers, json={"fcm_token": "device-opted-out"})
    fcm._send_ticket_notification(seed.tickets[0])
    firebase_mock.send_each_for_multicast.assert_not_called()
    with database.session() as session:
        assert session.scalar(select(FCMDevice)).is_active is False


def test_every_active_phone_receives_one_copy_of_new_ticket(client, headers, seed, firebase_mock):
    from app import fcm

    for token in ("active-phone-one", "active-phone-two", "disabled-phone"):
        client.post("/api/v1/push/register", headers=headers, json={"fcm_token": token})
    client.post("/api/v1/push/unregister", headers=headers, json={"fcm_token": "disabled-phone"})
    firebase_mock.send_each_for_multicast.return_value = SimpleNamespace(responses=[
        SimpleNamespace(success=True, exception=None), SimpleNamespace(success=True, exception=None),
    ])
    fcm._send_ticket_notification(seed.tickets[0])
    firebase_mock.send_each_for_multicast.assert_called_once()
    message = firebase_mock.send_each_for_multicast.call_args.args[0]
    assert sorted(message.tokens) == ["active-phone-one", "active-phone-two"]


def test_late_rejection_cannot_deactivate_a_renewed_registration(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import FCMDevice

    client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "phone-renewed-in-flight"})

    def renew_before_old_response(_message, **_kwargs):
        response = client.post("/api/v1/push/register", headers=headers, json={
            "fcm_token": "phone-renewed-in-flight", "device_name": "Registro renovado",
        })
        assert response.status_code == 200
        return SimpleNamespace(responses=[
            SimpleNamespace(success=False, exception=firebase_mock.UnregisteredError("old registration expired")),
        ])

    firebase_mock.send_each_for_multicast.side_effect = renew_before_old_response
    fcm._send_ticket_notification(seed.tickets[0])
    with database.session() as session:
        device = session.scalar(select(FCMDevice))
        assert device.is_active is True
        assert device.device_name == "Registro renovado"


def test_notification_for_unregistered_pc_uses_safe_room_fallback(client, headers, database, firebase_mock):
    from app import fcm
    from app.models import Ticket

    client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "phone-with-unknown-pc"})
    with database.session() as session:
        ticket = Ticket(pc_name="PC-NAO-CADASTRADO", problem="Sem imagem", status="OPEN")
        session.add(ticket)
        session.commit()
        ticket_id = ticket.id
    fcm._send_ticket_notification(ticket_id)
    message = firebase_mock.send_each_for_multicast.call_args.args[0]
    assert message.data["type"] == "new_ticket"
    assert message.data["ticket_id"] == str(ticket_id)
    assert all(isinstance(value, str) for value in message.data.values())
    assert "PC-NAO-CADASTRADO" in message.notification.body
    assert "Não cadastrada" in message.notification.body


@pytest.mark.parametrize("error_kind,expected_active", [
    ("invalid_token", False), ("generic_invalid_argument", True),
    ("invalid_message", True), ("temporary", True),
])
def test_only_confirmed_token_rejection_deactivates_device(
    client, headers, seed, database, firebase_mock, error_kind, expected_active, caplog,
):
    from app import fcm
    from app.models import FCMDevice
    from firebase_admin import exceptions

    client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "phone-token-rejection"})
    private_token = "private-fcm-value-must-not-appear-in-logs"
    if error_kind == "temporary":
        error = exceptions.UnavailableError(private_token)
    elif error_kind == "generic_invalid_argument":
        error = exceptions.InvalidArgumentError(private_token)
    else:
        details = [{
            "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "INVALID_ARGUMENT",
        }]
        if error_kind == "invalid_message":
            details.append({
                "@type": "type.googleapis.com/google.rpc.BadRequest",
                "fieldViolations": [{"field": "message.data", "description": "Invalid payload"}],
            })
        error = exceptions.InvalidArgumentError(private_token, http_response=SimpleNamespace(
            json=lambda: {"error": {"details": details}},
        ))
    firebase_mock.send_each_for_multicast.return_value = SimpleNamespace(responses=[
        SimpleNamespace(success=False, exception=error),
    ])
    fcm._send_ticket_notification(seed.tickets[0])
    with database.session() as session:
        assert session.scalar(select(FCMDevice)).is_active is expected_active
    assert private_token not in caplog.text


def test_global_invalid_message_error_keeps_registered_device(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import FCMDevice
    from firebase_admin import exceptions

    client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "valid-phone-token"})
    firebase_mock.send_each_for_multicast.side_effect = exceptions.InvalidArgumentError("Invalid message payload")
    fcm._send_safely(seed.tickets[0])
    with database.session() as session:
        assert session.scalar(select(FCMDevice)).is_active is True


def test_multibyte_problem_fits_fcm_payload_without_corrupting_utf8(client, headers, seed, database, firebase_mock):
    from app import fcm
    from app.models import Machine, Ticket
    from firebase_admin import messaging

    client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "phone-utf8"})
    with database.session() as session:
        ticket = session.get(Ticket, seed.tickets[0])
        ticket.problem = "Problema de projeção: " + "🔴漢" * 2000
        ticket.pc_name = "電" * 120
        session.get(Machine, seed.machines[0]).room_name = "室" * 120
        session.commit()
    fcm._send_ticket_notification(seed.tickets[0])
    message = firebase_mock.send_each_for_multicast.call_args.args[0]
    encoded = messaging._MessagingService.encode_message(messaging.Message(
        token=message.tokens[0], data=message.data, notification=message.notification,
        android=message.android, apns=message.apns,
    ))
    assert len(json.dumps(encoded, ensure_ascii=False).encode("utf-8")) <= 4096
    assert "�" not in message.notification.body
    assert message.data["ticket_id"] == str(seed.tickets[0])


def test_missing_credentials_skips_sdk_initialization(application, monkeypatch):
    import builtins
    from app import fcm

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS", raising=False)
    monkeypatch.delenv("FCM_ENABLED", raising=False)
    original_import = builtins.__import__

    def forbid_firebase_import(name, *args, **kwargs):
        if name == "firebase_admin" or name.startswith("firebase_admin."):
            raise AssertionError("Firebase SDK must stay lazy without configuration")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbid_firebase_import)
    assert fcm._get_firebase_app() is None
    assert fcm.configuration_status() == {"enabled": False, "credentials_configured": False}


def test_bad_credentials_log_only_safe_error_class(application, monkeypatch, caplog):
    from app import fcm
    import firebase_admin
    from firebase_admin import credentials

    private_value = "C:/secrets/conta-privada-push.json-token-nao-logar"
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", private_value)
    monkeypatch.delenv("FCM_ENABLED", raising=False)
    monkeypatch.setattr(firebase_admin, "get_app", Mock(side_effect=ValueError("not initialized")))
    monkeypatch.setattr(credentials, "Certificate", Mock(side_effect=ValueError(private_value)))
    fcm._send_safely(1)
    assert "FCM" in caplog.text
    assert "ValueError" in caplog.text
    assert private_value not in caplog.text


def test_google_credentials_take_precedence_over_legacy_alias(application, monkeypatch):
    from app import fcm
    import firebase_admin
    from firebase_admin import credentials

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "C:/fake/preferred-account.json")
    monkeypatch.setenv("FIREBASE_CREDENTIALS", "C:/fake/legacy-account.json")
    monkeypatch.delenv("FCM_ENABLED", raising=False)
    monkeypatch.setattr(firebase_admin, "get_app", Mock(side_effect=ValueError("not initialized")))
    certificate = Mock(return_value="fake-certificate")
    initializer = Mock(return_value="fake-app")
    monkeypatch.setattr(credentials, "Certificate", certificate)
    monkeypatch.setattr(firebase_admin, "initialize_app", initializer)
    assert fcm._get_firebase_app() == "fake-app"
    certificate.assert_called_once_with("C:/fake/preferred-account.json")
    assert initializer.call_args.kwargs["name"] == "maintenance-mobile"


@pytest.mark.parametrize("failure_stage", ["firebase_initialization", "thread_start"])
def test_fcm_failure_preserves_committed_ticket_websocket_and_web_push(
    client, database, monkeypatch, caplog, failure_stage,
):
    from app import chamados_socket, fcm
    from app.models import Ticket

    steps = []
    secret = "credential-or-token-value-never-log-this"

    def committed_broadcast(event):
        with database.session() as session:
            assert session.get(Ticket, event["ticket_id"]) is not None
        steps.append("websocket")

    monkeypatch.setattr(chamados_socket, "broadcast_from_thread", committed_broadcast)
    monkeypatch.setattr(chamados_socket, "enqueue_push", lambda _payload: steps.append("web_push"))
    if failure_stage == "firebase_initialization":
        def fail_initialization():
            steps.append("fcm")
            raise ValueError(secret)
        monkeypatch.setattr(fcm, "_get_firebase_app", fail_initialization)
        monkeypatch.setattr(chamados_socket, "enqueue_ticket_push", fcm._send_safely)
    else:
        def fail_thread_start(_self):
            steps.append("fcm")
            raise RuntimeError(secret)
        monkeypatch.setattr(fcm.threading.Thread, "start", fail_thread_start)

    class Request:
        data = json.dumps({"nome": "PC-SALA07", "usuario": "professor.joao", "problema": "Sem imagem"}).encode()

        def recv(self, _size):
            chunk, self.data = self.data, b""
            return chunk

    chamados_socket._TicketTCPHandler(Request(), ("127.0.0.1", 1), None)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Ticket)) == 4
    assert steps == ["websocket", "web_push", "fcm"]
    assert secret not in caplog.text


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
