"""API integration fixtures: every import and request uses disposable SQLite data.

Do not import app modules at collection time: app.main initializes the database and
session key on import. The environment must be isolated before that happens.
"""

import importlib
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def application():
    isolated_directory = tempfile.TemporaryDirectory(prefix="manutencao-import-tests-")
    previous_directory = os.environ.get("MANUTENCAO_DATA_DIR")
    os.environ["MANUTENCAO_DATA_DIR"] = isolated_directory.name
    database = importlib.import_module("app.database")
    # Fail before app.main can run its schema migration against a real database.
    assert Path(database.DATA_DIR).resolve() == Path(isolated_directory.name).resolve()
    main = importlib.import_module("app.main")
    yield main.app
    database.engine.dispose()
    if previous_directory is None:
        os.environ.pop("MANUTENCAO_DATA_DIR", None)
    else:
        os.environ["MANUTENCAO_DATA_DIR"] = previous_directory
    isolated_directory.cleanup()


@pytest.fixture
def database(application, tmp_path, monkeypatch):
    from app.database import Base, get_db

    # A file, rather than StaticPool/:memory:, gives concurrent requests separate
    # connections and exercises SQLite's real conditional UPDATE semantics.
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'integration.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_database():
        with factory() as session:
            yield session

    application.dependency_overrides[get_db] = override_database
    # Web middleware, WebSockets and push workers instantiate their own sessions.
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("app.") and hasattr(module, "SessionLocal"):
            monkeypatch.setattr(module, "SessionLocal", factory)

    yield SimpleNamespace(engine=engine, session=factory)
    application.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture(scope="session")
def password_hashes(application):
    from app.security import hash_password

    return {
        name: hash_password("senha-segura-123")
        for name in ("admin", "tecnico", "colega", "inativo")
    }


@pytest.fixture
def seed(database, password_hashes):
    from app.models import Machine, MachineHeartbeat, MachinePeripheral, Ticket, User

    now = datetime.utcnow()
    with database.session() as session:
        users = {}
        for name, password_hash in password_hashes.items():
            user = User(
                username=name,
                password_hash=password_hash,
                is_admin=name == "admin",
                is_active=name != "inativo",
            )
            session.add(user)
            session.flush()
            users[name] = user.id

        machines = [
            Machine(
                machine_name="PC-SALA07", room_name="7º Ano A", ip="192.0.2.7",
                username="professor.joao", profile="B", room_status="URGENT",
                hoptodesk_id="123456", hoptodesk_password="segredo-remoto",
                inspected=False, checkup_done=False, ram_gb=16,
            ),
            Machine(
                machine_name="PC-SALA02", room_name="2º Ano A", ip="192.0.2.2",
                username="professora.ana", profile="A", room_status="ATTENTION",
                inspected=True, last_inspection_date=now.date(),
                checkup_done=True, last_checkup_date=now.date(),
            ),
            Machine(
                machine_name="PC-SECRETARIA", room_name="Secretaria", ip="192.0.2.9",
                username="secretaria", profile="C", room_status="OK",
                inspected=False, checkup_done=True, last_checkup_date=now.date(),
            ),
        ]
        session.add_all(machines)
        session.flush()
        machines[0].peripherals.append(MachinePeripheral(
            peripheral_code="MOUSE", present=True, tested_working=True, quantity=0,
        ))
        tickets = [
            Ticket(machine_id=machines[0].id, pc_name=machines[0].machine_name,
                   reported_user="professor.joao", problem="Projetor sem imagem",
                   diagnostics_json='{"rede": "ok"}', status="OPEN"),
            Ticket(machine_id=machines[1].id, pc_name=machines[1].machine_name,
                   problem="Sem internet", status="IN_PROGRESS",
                   assigned_by="tecnico", assigned_at=now),
            Ticket(machine_id=machines[2].id, pc_name=machines[2].machine_name,
                   problem="Mouse falhando", status="CLOSED",
                   assigned_by="tecnico", assigned_at=now,
                   closed_by="tecnico", closed_at=now),
        ]
        session.add_all(tickets)
        session.add_all([
            MachineHeartbeat(pc_name=machines[0].machine_name, machine_id=machines[0].id,
                             last_seen=now, last_user="professor.joao"),
            MachineHeartbeat(pc_name=machines[1].machine_name, machine_id=machines[1].id,
                             last_seen=now - timedelta(hours=1), last_user=None),
        ])
        session.commit()
        return SimpleNamespace(
            users=users,
            machines=[machine.id for machine in machines],
            tickets=[ticket.id for ticket in tickets],
        )


@pytest.fixture
def client(application, database, seed):
    # Deliberately no `with TestClient(...)`: lifespan would start the TCP/UDP
    # listener and periodic worker, neither of which belongs in HTTP API tests.
    client = TestClient(application, follow_redirects=False)
    yield client
    client.close()


@pytest.fixture
def login(client):
    def authenticate(username="tecnico"):
        response = client.post("/api/v1/auth/login", json={
            "username": username, "password": "senha-segura-123",
        })
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return authenticate


@pytest.fixture
def headers(login):
    return login()
