import pytest
from starlette.websockets import WebSocketDisconnect


def test_web_keeps_html_cookie_login_and_existing_json_shapes(client, headers, seed):
    response = client.get("/machines")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    response = client.get("/login")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'action="/login"' in response.text

    response = client.post("/login", data={"username": "tecnico", "password": "senha-segura-123"})
    assert response.status_code == 303
    assert "session" in client.cookies
    for path in ("/dashboard", "/machines", "/rooms", "/tickets"):
        page = client.get(path)
        assert page.status_code == 200, path
        assert page.headers["content-type"].startswith("text/html")

    assert isinstance(client.get("/api/tickets").json()["tickets"], list)
    assert isinstance(client.get("/api/online").json()["online"], list)
    # Mobile bearer remains required even with an authenticated browser cookie.
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post(f"/api/v1/tickets/{seed.tickets[0]}/take", headers=headers).status_code == 200
    web_tickets = client.get("/api/tickets?status=IN_PROGRESS").json()["tickets"]
    ticket = next(item for item in web_tickets if item["id"] == seed.tickets[0])
    assert ticket["assigned_by"] == "tecnico"
    assert client.get("/logout").status_code == 302
    assert client.get("/machines").status_code == 302
    # Browser logout does not revoke a separate native-device session.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


@pytest.mark.parametrize("path", ["/ws/v1/tickets", "/ws/v1/tickets?token=forged-token", "/ws/tickets"])
def test_websockets_reject_missing_authentication(client, path):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(path):
            pass
    assert exc.value.code == 1008


def test_mobile_websocket_accepts_bearer_and_rejects_revoked_session(client, headers):
    with client.websocket_connect("/ws/v1/tickets", headers=headers) as websocket:
        assert websocket.receive_json() == {"type": "ready"}
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        websocket.send_text("ping")
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_json()
        assert exc.value.code == 1008


def test_existing_websocket_accepts_web_session(client):
    client.post("/login", data={"username": "tecnico", "password": "senha-segura-123"})
    with client.websocket_connect("/ws/tickets") as websocket:
        assert websocket.receive_json() == {"type": "ready"}


def test_ticket_event_reaches_both_existing_web_and_mobile_channels(client, headers):
    from app.realtime import manager

    client.post("/login", data={"username": "tecnico", "password": "senha-segura-123"})
    with client.websocket_connect("/ws/tickets") as web:
        assert web.receive_json() == {"type": "ready"}
        with client.websocket_connect("/ws/v1/tickets", headers=headers) as mobile:
            assert mobile.receive_json() == {"type": "ready"}
            event = {"type": "ticket_created", "ticket_id": 77, "pc_name": "PC-SALA07"}
            mobile.portal.call(manager.broadcast, event)
            assert web.receive_json() == event
            assert mobile.receive_json() == event


def test_revoked_mobile_session_receives_no_further_ticket_payload(client, headers):
    from app.realtime import manager

    with client.websocket_connect("/ws/v1/tickets", headers=headers) as websocket:
        assert websocket.receive_json() == {"type": "ready"}
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        websocket.portal.call(manager.broadcast, {"type": "ticket_created", "ticket_id": 77})
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_json()
        assert exc.value.code == 1008
