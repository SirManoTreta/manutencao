"""Native push lifecycle through the public API; no Firebase delivery required."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select


@pytest.mark.parametrize("path,payload", [
    ("/api/v1/push/register", {"fcm_token": "sem-login", "platform": "android"}),
    ("/api/v1/push/unregister", {"fcm_token": "sem-login"}),
])
def test_push_endpoints_require_bearer(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 401
    assert "location" not in response.headers


def test_register_uses_authenticated_user_and_records_metadata(client, headers, seed, database):
    from app.models import FCMDevice

    response = client.post("/api/v1/push/register", headers=headers, json={
        "fcm_token": "token-galaxy-escolar", "platform": "android", "device_name": "Galaxy da TI",
    })
    assert response.status_code == 200
    assert response.json() == {"registered": True}
    assert "token-galaxy-escolar" not in response.text
    with database.session() as session:
        device = session.scalar(select(FCMDevice))
        assert device.user_id == seed.users["tecnico"]
        assert device.platform == "android"
        assert device.device_name == "Galaxy da TI"
        assert device.is_active is True
        assert device.created_at is not None
        assert device.updated_at >= device.created_at


@pytest.mark.parametrize("path,payload", [
    ("/api/v1/push/register", {"fcm_token": "forjado", "user_id": 1}),
    ("/api/v1/push/unregister", {"fcm_token": "forjado", "user_id": 1}),
])
def test_client_cannot_select_other_device_owner(client, headers, database, path, payload):
    from app.models import FCMDevice

    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == 422
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 0


@pytest.mark.parametrize("payload", [
    {"fcm_token": ""}, {"fcm_token": "   "}, {"fcm_token": "x" * 4097},
    {"fcm_token": "token", "platform": "windows"},
    {"fcm_token": "token", "device_name": "x" * 121},
])
def test_native_registration_validates_payload(client, headers, payload):
    assert client.post("/api/v1/push/register", headers=headers, json=payload).status_code == 422


def test_repeated_registration_updates_metadata_without_duplicate(client, headers, database):
    from app.models import FCMDevice

    payload = {"fcm_token": "token-unico", "platform": "android", "device_name": "Primeiro nome"}
    assert client.post("/api/v1/push/register", headers=headers, json=payload).status_code == 200
    old_date = datetime.utcnow() - timedelta(days=10)
    with database.session() as session:
        device = session.scalar(select(FCMDevice))
        device.created_at = old_date
        device.updated_at = old_date
        device_id = device.id
        session.commit()

    assert client.post("/api/v1/push/register", headers=headers, json={
        **payload, "platform": "ios", "device_name": "Novo nome",
    }).status_code == 200
    with database.session() as session:
        devices = session.scalars(select(FCMDevice)).all()
        assert len(devices) == 1
        assert devices[0].id == device_id
        assert devices[0].platform == "ios"
        assert devices[0].device_name == "Novo nome"
        assert devices[0].created_at == old_date
        assert devices[0].updated_at > old_date

    # Legacy/minimal registration must not erase an existing useful device name.
    assert client.post("/api/v1/push/register", headers=headers, json={"fcm_token": "token-unico"}).status_code == 200
    with database.session() as session:
        assert session.scalar(select(FCMDevice)).device_name == "Novo nome"


def test_unregister_is_user_scoped_idempotent_and_can_reactivate(client, login, database, seed):
    from app.models import FCMDevice

    owner = login("tecnico")
    other = login("colega")
    payload = {"fcm_token": "token-meu-celular"}
    client.post("/api/v1/push/register", headers=owner, json=payload)
    assert client.post("/api/v1/push/unregister", headers=other, json=payload).status_code == 200
    with database.session() as session:
        assert session.scalar(select(FCMDevice)).is_active is True

    # Same authenticated user may disable a phone from another active session.
    same_user_session = login("tecnico")
    for _ in range(2):
        assert client.post("/api/v1/push/unregister", headers=same_user_session, json=payload).status_code == 200
    with database.session() as session:
        device = session.scalar(select(FCMDevice))
        assert device.user_id == seed.users["tecnico"]
        assert device.is_active is False
        device_id = device.id

    assert client.post("/api/v1/push/register", headers=owner, json=payload).status_code == 200
    with database.session() as session:
        device = session.scalar(select(FCMDevice))
        assert device.id == device_id
        assert device.is_active is True


def test_user_can_register_multiple_phones_and_refresh_one_token(client, headers, database):
    from app.models import FCMDevice

    for token, name in [("phone-one-old", "Celular 1"), ("phone-two", "Celular 2")]:
        assert client.post("/api/v1/push/register", headers=headers, json={
            "fcm_token": token, "device_name": name,
        }).status_code == 200
    assert client.post("/api/v1/push/unregister", headers=headers, json={"fcm_token": "phone-one-old"}).status_code == 200
    assert client.post("/api/v1/push/register", headers=headers, json={
        "fcm_token": "phone-one-refreshed", "device_name": "Celular 1",
    }).status_code == 200
    with database.session() as session:
        devices = {device.token: device for device in session.scalars(select(FCMDevice)).all()}
        assert devices["phone-one-old"].is_active is False
        assert devices["phone-one-refreshed"].is_active is True
        assert devices["phone-two"].is_active is True


def test_phone_transferred_to_next_account_survives_previous_user_unregister(client, login, database, seed):
    from app.models import FCMDevice

    previous = login("tecnico")
    current = login("colega")
    payload = {"fcm_token": "phone-account-switch", "device_name": "Celular compartilhado"}
    assert client.post("/api/v1/push/register", headers=previous, json=payload).status_code == 200
    assert client.post("/api/v1/push/register", headers=current, json=payload).status_code == 200
    assert client.post("/api/v1/push/unregister", headers=previous, json={"fcm_token": payload["fcm_token"]}).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=previous).status_code == 204
    with database.session() as session:
        devices = session.scalars(select(FCMDevice)).all()
        assert len(devices) == 1
        assert devices[0].user_id == seed.users["colega"]
        assert devices[0].is_active is True


def test_old_devices_endpoint_and_new_push_endpoints_share_registration(client, headers, database):
    from app.models import FCMDevice

    assert client.post("/api/v1/devices", headers=headers, json={
        "token": "legacy-and-native-phone", "platform": "android",
    }).status_code == 201
    assert client.post("/api/v1/push/register", headers=headers, json={
        "fcm_token": "legacy-and-native-phone", "device_name": "Nome atualizado",
    }).status_code == 200
    with database.session() as session:
        devices = session.scalars(select(FCMDevice)).all()
        assert len(devices) == 1
        assert devices[0].device_name == "Nome atualizado"
    assert client.request("DELETE", "/api/v1/devices", headers=headers, json={
        "token": "legacy-and-native-phone",
    }).status_code == 204
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(FCMDevice)) == 0


def test_push_status_requires_authentication(client):
    assert client.get("/api/v1/push/status").status_code == 401


def test_push_status_counts_only_current_users_eligible_devices(client, login, database, monkeypatch):
    from app.models import FCMDevice, MobileSession

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS", raising=False)
    monkeypatch.setenv("FCM_ENABLED", "false")
    owner = login("tecnico")
    old_session = login("tecnico")
    other_user = login("colega")
    for headers, token in [
        (owner, "phone-eligible"), (owner, "phone-disabled"),
        (old_session, "phone-expired-session"), (other_user, "other-user-phone"),
    ]:
        assert client.post("/api/v1/push/register", headers=headers, json={"fcm_token": token}).status_code == 200
    client.post("/api/v1/push/unregister", headers=owner, json={"fcm_token": "phone-disabled"})
    with database.session() as session:
        device = session.scalar(select(FCMDevice).where(FCMDevice.token == "phone-expired-session"))
        session.get(MobileSession, device.session_id).expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
    response = client.get("/api/v1/push/status", headers=owner)
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "credentials_configured": False, "active_devices": 1}
    assert "phone-eligible" not in response.text
    assert "token" not in response.text
