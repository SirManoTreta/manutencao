from datetime import timedelta

import pytest


def test_dashboard_reuses_real_inventory_and_ticket_counts(client, headers, seed):
    response = client.get("/api/v1/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_machines"] == 3
    assert body["rooms_count"] == 3
    assert body["online_count"] == 1
    assert body["in_progress_tickets"] == 1
    assert body["closed_tickets"] == 1
    assert body["pending_inspections"] == 2
    assert body["pending_checkups"] == 1
    assert body["urgent_rooms"] == 1
    assert body["attention_rooms"] == 1
    assert len(body["recent_tickets"]) == 3
    assert len(body["recent_machines"]) == 3
    assert sum(row["count"] for row in body["profile_rows"]) == 3
    assert sum(row["count"] for row in body["status_rows"]) == 3
    assert sum(row["count"] for row in body["segment_rows"]) == 3
    assert "segredo-remoto" not in response.text


def test_machine_list_detail_and_filters_do_not_leak_remote_password(client, headers, seed):
    response = client.get("/api/v1/machines", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 3
    assert "hoptodesk_password" not in response.text
    assert "segredo-remoto" not in response.text
    detail = client.get(f"/api/v1/machines/{seed.machines[0]}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["machine_name"] == "PC-SALA07"
    assert detail.json()["hoptodesk_id"] == "123456"
    mouse = next(p for p in detail.json()["peripherals"] if p["peripheral_code"] == "MOUSE")
    assert mouse["present"] is True
    assert mouse["tested_working"] is True
    assert "hoptodesk_password" not in detail.text

    filtered = client.get("/api/v1/machines", headers=headers, params={
        "q": "SALA07", "profile": "B", "segment": "FUND2",
        "room_status": "URGENT", "inspected": "false", "checkup_done": "false",
    })
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [seed.machines[0]]
    pending = client.get("/api/v1/machines", headers=headers, params={"checkup_done": "false"})
    assert [item["id"] for item in pending.json()] == [seed.machines[0]]
    assert client.get("/api/v1/machines?q=nao-existe", headers=headers).json() == []


def test_machine_create_partial_update_and_delete_use_existing_audit_rules(client, headers, database):
    from app.models import Machine, MachineAudit
    from sqlalchemy import select

    response = client.post("/api/v1/machines", headers=headers, json={
        "machine_name": "PC-NOVO", "room_name": "3º Ano A", "ip": "192.0.2.30",
        "username": "professor.novo", "profile": "A", "room_status": "OK",
        "ram_gb": 8, "mac_address": "aabbccddeeff",
        "peripherals": [
            {"peripheral_code": "MOUSE", "present": True, "tested_working": True},
            {"peripheral_code": "CABO_RCA", "present": True,
             "tested_working": True, "quantity": 2},
        ],
    })
    assert response.status_code == 201, response.text
    created = response.json()
    machine_id = created["id"]
    assert created["created_by"] == "tecnico"
    assert created["mac_address"] == "AA:BB:CC:DD:EE:FF"
    rca = next(p for p in created["peripherals"] if p["peripheral_code"] == "CABO_RCA")
    assert rca["quantity"] == 2

    changed = client.put(f"/api/v1/machines/{machine_id}", headers=headers, json={"ram_gb": 32})
    assert changed.status_code == 200
    assert changed.json()["ram_gb"] == 32
    assert changed.json()["machine_name"] == "PC-NOVO"
    assert changed.json()["updated_by"] == "tecnico"
    mouse = next(p for p in changed.json()["peripherals"] if p["peripheral_code"] == "MOUSE")
    assert mouse["present"] is True  # Partial update must not reset peripherals.

    changed = client.put(f"/api/v1/machines/{machine_id}", headers=headers, json={"profile": "C"})
    assert changed.status_code == 200
    codes = {p["peripheral_code"] for p in changed.json()["peripherals"]}
    assert "WEBCAM" in codes
    assert "CABO_RCA" not in codes
    assert "PROJETOR" not in codes

    assert client.delete(f"/api/v1/machines/{machine_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/machines/{machine_id}", headers=headers).status_code == 404
    with database.session() as session:
        assert session.get(Machine, machine_id) is None
        actions = session.scalars(select(MachineAudit.action).where(MachineAudit.machine_id == machine_id)).all()
        assert actions == ["CREATE", "UPDATE", "UPDATE", "DELETE"]


@pytest.mark.parametrize("payload", [
    {"profile": "INVALID"}, {"room_status": "INVALID"}, {"ram_gb": -1},
    {"machine_name": ""}, {"hoptodesk_password": "nao-expor"},
])
def test_machine_inputs_are_validated(client, headers, seed, payload):
    response = client.put(f"/api/v1/machines/{seed.machines[0]}", headers=headers, json=payload)
    assert response.status_code == 422


def test_partial_mobile_update_preserves_legacy_remote_secret(client, headers, database, seed):
    from app.models import Machine

    response = client.put(f"/api/v1/machines/{seed.machines[0]}", headers=headers, json={"ram_gb": 32})
    assert response.status_code == 200
    assert "hoptodesk_password" not in response.text
    with database.session() as session:
        assert session.get(Machine, seed.machines[0]).hoptodesk_password == "segredo-remoto"


def test_auto_reset_expiration_is_shared_with_mobile(client, headers, database, seed):
    from app.models import Machine
    from app.main import _today_br

    old_date = _today_br() - timedelta(days=3)
    with database.session() as session:
        machine = session.get(Machine, seed.machines[1])
        machine.inspected = True
        machine.checkup_done = True
        machine.last_inspection_date = old_date
        machine.last_checkup_date = old_date
        session.commit()
    response = client.get("/api/v1/machines", headers=headers)
    assert response.status_code == 200
    machine = next(m for m in response.json() if m["id"] == seed.machines[1])
    assert machine["inspected"] is False
    assert machine["checkup_done"] is False
    assert machine["last_inspection_date"] == old_date.isoformat()


def test_rooms_list_machines_and_status_update(client, headers, seed):
    response = client.get("/api/v1/rooms", headers=headers)
    assert response.status_code == 200
    rooms = {room["room_name"]: room for room in response.json()}
    assert rooms["7º Ano A"]["room_status"] == "URGENT"
    response = client.get("/api/v1/rooms/machines", headers=headers, params={"room_name": "7º Ano A"})
    assert response.status_code == 200
    assert [m["id"] for m in response.json()] == [seed.machines[0]]
    response = client.patch("/api/v1/rooms/status", headers=headers, json={
        "room_name": "7º Ano A", "room_status": "OK",
    })
    assert response.status_code == 200
    machine = client.get(f"/api/v1/machines/{seed.machines[0]}", headers=headers).json()
    assert machine["room_status"] == "OK"
    assert machine["updated_by"] == "tecnico"
    assert client.patch("/api/v1/rooms/status", headers=headers, json={
        "room_name": "7º Ano A", "room_status": "INVALID",
    }).status_code == 422


def test_online_exposes_heartbeat_and_login_screen(client, headers, seed):
    response = client.get("/api/v1/online", headers=headers)
    assert response.status_code == 200
    rows = {row["pc_name"]: row for row in response.json()}
    online = rows["PC-SALA07"]
    assert online["is_online"] is True
    assert online["login_active"] is True
    assert online["last_user"] == "professor.joao"
    assert online["machine"]["id"] == seed.machines[0]
    assert online["age_seconds"] >= 0
    offline = rows["PC-SALA02"]
    assert offline["is_online"] is False
    assert offline["login_active"] is False
    assert offline["last_user"] is None


@pytest.mark.parametrize("resource", ["machines", "tickets"])
def test_missing_resources_return_404_json(client, headers, resource):
    response = client.get(f"/api/v1/{resource}/999999", headers=headers)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
