from datetime import datetime, timedelta

import pytest
from sqlalchemy import select


def test_login_uses_existing_password_hash_and_exposes_public_user(client, seed):
    response = client.post("/api/v1/auth/login", json={
        "username": "tecnico", "password": "senha-segura-123",
    })
    assert response.status_code == 200
    body = response.json()
    assert len(body["access_token"]) >= 32
    assert body["token_type"].lower() == "bearer"
    assert body["user"]["id"] == seed.users["tecnico"]
    assert body["user"]["username"] == "tecnico"
    assert body["user"]["is_admin"] is False
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert "session" not in response.cookies


@pytest.mark.parametrize("username,password", [
    ("tecnico", "senha-incorreta"),
    ("desconhecido", "senha-segura-123"),
    ("inativo", "senha-segura-123"),
])
def test_invalid_login_is_unauthorized(client, username, password):
    response = client.post("/api/v1/auth/login", json={
        "username": username, "password": password,
    })
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert "access_token" not in response.json()


@pytest.mark.parametrize("path", [
    "/api/v1/auth/me", "/api/v1/dashboard", "/api/v1/machines",
    "/api/v1/tickets", "/api/v1/rooms", "/api/v1/online", "/api/v1/users",
])
def test_protected_api_returns_json_401_without_web_redirect(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert "location" not in response.headers


def test_me_resolves_bearer_token(client, headers, seed):
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == seed.users["tecnico"]
    assert response.json()["username"] == "tecnico"
    assert "password_hash" not in response.json()


def test_token_stored_as_digest_and_logout_revokes_only_current_session(client, login, database):
    from app.models import MobileSession

    headers = login()
    other_headers = login()
    raw_token = headers["Authorization"].split(" ", 1)[1]
    with database.session() as session:
        saved_sessions = session.scalars(select(MobileSession)).all()
        assert len(saved_sessions) == 2
        assert all(raw_token not in str(vars(saved)) for saved in saved_sessions)

    assert client.post("/api/v1/auth/logout", headers=headers).status_code in (200, 204)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other_headers).status_code == 200


def test_expired_session_rejected(client, headers, database):
    from app.models import MobileSession

    with database.session() as session:
        saved = session.scalar(select(MobileSession))
        saved.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_disabled_user_loses_existing_mobile_access(client, headers, database, seed):
    from app.models import User

    with database.session() as session:
        session.get(User, seed.users["tecnico"]).is_active = False
        session.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_forged_token_rejected(client):
    assert client.get("/api/v1/auth/me", headers={
        "Authorization": "Bearer forged-token",
    }).status_code == 401
