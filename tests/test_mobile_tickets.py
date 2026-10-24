from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier, Lock

from fastapi.testclient import TestClient
from sqlalchemy import event


def test_tickets_list_filter_and_detail(client, headers, seed):
    response = client.get("/api/v1/tickets?status=ALL", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 3
    response = client.get("/api/v1/tickets?status=OPEN", headers=headers)
    assert [ticket["id"] for ticket in response.json()] == [seed.tickets[0]]
    response = client.get(f"/api/v1/tickets/{seed.tickets[0]}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["problem"] == "Projetor sem imagem"
    assert body["reported_user"] == "professor.joao"
    assert body["diagnostics_json"] == '{"rede": "ok"}'
    assert body["machine"]["room_name"] == "7º Ano A"
    assert datetime.fromisoformat(body["created_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0


def test_take_and_close_ticket_record_actor_and_diagnosis(client, headers, seed):
    ticket_id = seed.tickets[0]
    response = client.post(f"/api/v1/tickets/{ticket_id}/take", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"
    assert response.json()["assigned_by"] == "tecnico"
    assert response.json()["assigned_at"]
    assert client.post(f"/api/v1/tickets/{ticket_id}/take", headers=headers).status_code == 409
    response = client.post(f"/api/v1/tickets/{ticket_id}/close", headers=headers, json={
        "diagnosis": "Cabo HDMI substituído",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CLOSED"
    assert body["closed_by"] == "tecnico"
    assert body["closed_at"]
    assert body["diagnosis"] == "Cabo HDMI substituído"
    # Technical diagnostics sent by Professor_auto remain available.
    assert body["diagnostics_json"] == '{"rede": "ok"}'
    assert client.post(f"/api/v1/tickets/{ticket_id}/close", headers=headers, json={}).status_code == 409


def test_open_ticket_cannot_be_closed_before_take(client, headers, seed):
    response = client.post(f"/api/v1/tickets/{seed.tickets[0]}/close", headers=headers, json={})
    assert response.status_code == 409


def test_two_simultaneous_requests_have_exactly_one_winner(application, client, login, database, seed):
    """Synchronize two real SQLite connections immediately before the UPDATE.

    Sequential repeated calls cannot catch an ORM read/check/write race. This
    barrier forces both HTTP workers to reach their write before either proceeds.
    """
    first_headers = login("tecnico")
    second_headers = login("colega")
    before_update = Barrier(2, timeout=10)
    lock = Lock()
    connections = set()

    def synchronize_updates(connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("UPDATE TICKETS SET"):
            with lock:
                connections.add(id(connection.connection.driver_connection))
            before_update.wait()

    event.listen(database.engine, "before_cursor_execute", synchronize_updates)

    def take(headers):
        independent_client = TestClient(application, follow_redirects=False)
        try:
            response = independent_client.post(
                f"/api/v1/tickets/{seed.tickets[0]}/take", headers=headers,
            )
            return response.status_code, response.json(), headers
        finally:
            independent_client.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(take, first_headers)
            second = executor.submit(take, second_headers)
            results = [first.result(timeout=20), second.result(timeout=20)]
    finally:
        event.remove(database.engine, "before_cursor_execute", synchronize_updates)

    assert len(connections) == 2, "Concurrency test must use two DB connections"
    assert sorted(result[0] for result in results) == [200, 409]
    winner = next(result for result in results if result[0] == 200)
    stored = client.get(f"/api/v1/tickets/{seed.tickets[0]}", headers=first_headers).json()
    assert stored["status"] == "IN_PROGRESS"
    assert stored["assigned_by"] == winner[1]["assigned_by"]
