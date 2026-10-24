import pytest


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/v1/users", None),
    ("POST", "/api/v1/users", {"username": "intruso", "password": "senha-segura-123", "is_admin": True}),
    ("PUT", "/api/v1/users/1", {"is_admin": True}),
    ("DELETE", "/api/v1/users/1", None),
])
def test_non_admin_cannot_manage_users(client, headers, method, path, payload):
    response = client.request(method, path, headers=headers, json=payload)
    assert response.status_code == 403


def test_admin_can_create_update_and_disable_user(client, login, database):
    from app.models import User
    from app.security import verify_password

    headers = login("admin")
    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 4
    assert "password_hash" not in response.text

    response = client.post("/api/v1/users", headers=headers, json={
        "username": "novo.tecnico", "password": "nova-senha-123", "is_admin": False,
    })
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert "password" not in response.json()
    assert "password_hash" not in response.json()
    with database.session() as session:
        user = session.get(User, user_id)
        assert user.password_hash != "nova-senha-123"
        assert verify_password("nova-senha-123", user.password_hash)

    response = client.put(f"/api/v1/users/{user_id}", headers=headers, json={
        "username": "tecnico.editado", "is_admin": True,
    })
    assert response.status_code == 200
    assert response.json()["is_admin"] is True
    assert response.json()["username"] == "tecnico.editado"
    assert client.delete(f"/api/v1/users/{user_id}", headers=headers).status_code == 204
    with database.session() as session:
        assert session.get(User, user_id).is_active is False
    assert client.post("/api/v1/auth/login", json={
        "username": "tecnico.editado", "password": "nova-senha-123",
    }).status_code == 401


def test_admin_cannot_disable_own_account(client, login, seed):
    headers = login("admin")
    response = client.delete(f"/api/v1/users/{seed.users['admin']}", headers=headers)
    assert response.status_code == 409
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_duplicate_username_returns_conflict(client, login):
    response = client.post("/api/v1/users", headers=login("admin"), json={
        "username": "tecnico", "password": "nova-senha-123", "is_admin": False,
    })
    assert response.status_code == 409


def test_password_change_invalidates_mobile_session(client, login, seed):
    old_headers = login("tecnico")
    response = client.put(f"/api/v1/users/{seed.users['tecnico']}", headers=login("admin"), json={
        "username": "tecnico", "password": "senha-alterada-123",
    })
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "username": "tecnico", "password": "senha-alterada-123",
    }).status_code == 200
