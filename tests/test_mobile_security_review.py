"""Independent regression checks for account changes, device ownership and legacy data."""

import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect


@pytest.mark.parametrize("authorization", ["Basic invalid", "Bearer", "Bearer " + "x" * 257])
def test_invalid_bearer_transport_is_rejected(client, authorization):
    response = client.get("/api/v1/auth/me", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_existing_admin_session_loses_admin_access_after_demotion(client, login, database, seed):
    from app.models import User

    headers = login("admin")
    assert client.get("/api/v1/users", headers=headers).status_code == 200
    with database.session() as session:
        session.get(User, seed.users["admin"]).is_admin = False
        session.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == 403


def test_web_password_change_invalidates_mobile_http_and_active_websocket(client, headers, seed):
    from app.realtime import manager

    with client.websocket_connect("/ws/v1/tickets", headers=headers) as websocket:
        assert websocket.receive_json() == {"type": "ready"}
        assert client.post("/login", data={
            "username": "admin", "password": "senha-segura-123",
        }).status_code == 303
        assert client.post(f"/users/{seed.users['tecnico']}/edit", data={
            "username": "tecnico", "password": "nova-senha-pelo-site",
            "is_active": "on",
        }).status_code == 303
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        # A revoked listener must be checked before a new ticket payload is sent,
        # even when it has not sent its next keepalive yet.
        websocket.portal.call(manager.broadcast, {"type": "ticket_created", "ticket_id": 999})
        with pytest.raises(WebSocketDisconnect) as exception:
            websocket.receive_json()
        assert exception.value.code == 1008


def test_logout_does_not_remove_device_reassigned_by_next_login(client, login, database, seed):
    from app.models import FCMDevice

    first = login("tecnico")
    next_account = login("colega")
    device = {"token": "same-phone-after-account-switch", "platform": "android"}
    assert client.post("/api/v1/devices", headers=first, json=device).status_code == 201
    assert client.post("/api/v1/devices", headers=next_account, json=device).status_code == 201
    assert client.post("/api/v1/auth/logout", headers=first).status_code == 204
    with database.session() as session:
        registrations = session.scalars(select(FCMDevice)).all()
        assert len(registrations) == 1
        assert registrations[0].user_id == seed.users["colega"]
    assert client.get("/api/v1/auth/me", headers=next_account).status_code == 200


def test_legacy_database_migration_preserves_tickets_and_is_idempotent(tmp_path):
    # This subprocess never imports the production database path. It resembles
    # the deployed pre-mobile schema and then imports the current entry point.
    legacy_directory = tmp_path / "legacy"
    legacy_directory.mkdir()
    with sqlite3.connect(legacy_directory / "app.db") as connection:
        connection.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN NOT NULL,
                is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL
            );
            CREATE TABLE tickets (
                id INTEGER PRIMARY KEY, machine_id INTEGER,
                pc_name VARCHAR(120) NOT NULL, reported_user VARCHAR(120),
                problem TEXT NOT NULL, diagnostics_json TEXT,
                status VARCHAR(16) NOT NULL, created_at DATETIME NOT NULL,
                assigned_at DATETIME, assigned_by VARCHAR(80),
                closed_at DATETIME, closed_by VARCHAR(80)
            );
            INSERT INTO tickets (id, pc_name, problem, diagnostics_json, status, created_at)
            VALUES (1, 'PC-LEGACY', 'Sem imagem', '{"rede":"ok"}', 'OPEN', '2026-01-01 12:00:00');
        """)
    environment = os.environ.copy()
    environment["MANUTENCAO_DATA_DIR"] = str(legacy_directory)
    result = subprocess.run(
        [sys.executable, "-c", "import app.main; app.main._migrate_sqlite(); app.main._migrate_sqlite()"],
        env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(legacy_directory / "app.db") as connection:
        row = connection.execute("SELECT pc_name, diagnostics_json, status, resolution_note FROM tickets").fetchone()
        assert row == ("PC-LEGACY", '{"rede":"ok"}', "OPEN", None)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"mobile_sessions", "fcm_devices"} <= tables
