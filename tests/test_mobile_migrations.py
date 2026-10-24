"""Exercise production-style additive migration against the pre-mobile schema."""

import os
from pathlib import Path
import subprocess
import sys


def test_legacy_database_migration_preserves_data_and_is_idempotent(tmp_path):
    project = Path(__file__).resolve().parents[1]
    # Freeze the original schema as SQL: tests still work after new commits and
    # in a source export without a Git checkout or historic Python model files.
    legacy_schema = (Path(__file__).parent / "fixtures" / "legacy_schema.sql").read_text(encoding="utf-8")
    legacy_directory = tmp_path / "legacy-data"
    legacy_directory.mkdir()
    environment = dict(os.environ, MANUTENCAO_DATA_DIR=str(legacy_directory))
    script = r'''
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime

data = Path(os.environ["MANUTENCAO_DATA_DIR"])
database_path = data / "app.db"
from app.security import hash_password
password_hash = hash_password("senha-legada-123")
with sqlite3.connect(database_path) as connection:
    connection.executescript(sys.stdin.read())
    now = datetime.now().isoformat()
    connection.execute("INSERT INTO users (id,username,password_hash,is_admin,is_active,created_at) VALUES (1,?,?,?,?,?)",
                       ("tecnico-legado", password_hash, True, True, now))
    connection.execute("INSERT INTO machines (id,machine_name,room_name,room_status,ip,username,profile,inspected,checkup_done,hoptodesk_password,created_at,updated_at) VALUES (1,?,?,?,?,?,?,?,?,?,?,?)",
                       ("PC-LEGADO", "7º Ano A", "OK", "192.0.2.77", "professor", "B", False, False, "segredo-legado", now, now))
    connection.execute("INSERT INTO tickets (machine_id,pc_name,problem,status,created_at) VALUES (1,?,?,?,?)",
                       ("PC-LEGADO", "Sem rede", "OPEN", now))
    assert "resolution_note" not in {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
    connection.commit()

import app.main as main
from app.database import DB_PATH, engine
assert Path(DB_PATH).resolve() == database_path.resolve()
main._migrate_sqlite()
main._migrate_sqlite()
with sqlite3.connect(database_path) as connection:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"mobile_sessions", "fcm_devices"} <= tables
    assert "resolution_note" in {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
    assert connection.execute("SELECT username,password_hash FROM users").fetchall() == [("tecnico-legado", password_hash)]
    assert connection.execute("SELECT machine_name,hoptodesk_password FROM machines").fetchall() == [("PC-LEGADO", "segredo-legado")]
    assert connection.execute("SELECT pc_name,problem,status FROM tickets").fetchall() == [("PC-LEGADO", "Sem rede", "OPEN")]
engine.dispose()
print("legacy migration ok")
'''
    result = subprocess.run(
        [sys.executable, "-c", script], input=legacy_schema,
        cwd=project, env=environment, text=True, encoding="utf-8",
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "legacy migration ok" in result.stdout


def test_existing_fcm_token_survives_additive_device_metadata_migration(tmp_path):
    """An installed first mobile version already has devices, not an empty DB."""
    import sqlite3

    project = Path(__file__).resolve().parents[1]
    directory = tmp_path / "old-mobile-data"
    directory.mkdir()
    database_path = directory / "app.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN NOT NULL,
                is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL
            );
            CREATE TABLE mobile_sessions (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                token_hash VARCHAR(64) NOT NULL UNIQUE, password_fingerprint VARCHAR(64) NOT NULL,
                created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL
            );
            CREATE TABLE fcm_devices (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                session_id INTEGER NOT NULL REFERENCES mobile_sessions(id),
                token_hash VARCHAR(64) NOT NULL UNIQUE, token TEXT NOT NULL,
                platform VARCHAR(16) NOT NULL, updated_at DATETIME NOT NULL
            );
            INSERT INTO users VALUES (1,'tecnico-legado','fake-hash',0,1,'2026-01-01 00:00:00');
            INSERT INTO mobile_sessions VALUES (1,1,'session-hash','fingerprint','2026-01-01 00:00:00','2099-01-01 00:00:00');
            INSERT INTO fcm_devices VALUES (1,1,1,'fcm-hash','existing-phone-token','android','2026-02-01 10:30:00');
        ''')
    environment = dict(os.environ, MANUTENCAO_DATA_DIR=str(directory))
    result = subprocess.run(
        [sys.executable, "-c", "import app.main; app.main._migrate_sqlite(); app.main._migrate_sqlite()"],
        cwd=project, env=environment, text=True, encoding="utf-8", capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(fcm_devices)")}
        assert {"device_name", "created_at", "is_active"} <= columns
        devices = connection.execute(
            "SELECT id,user_id,session_id,token_hash,token,platform,updated_at,device_name,created_at,is_active FROM fcm_devices"
        ).fetchall()
        assert len(devices) == 1
        device = devices[0]
        assert device[:7] == (1, 1, 1, "fcm-hash", "existing-phone-token", "android", "2026-02-01 10:30:00")
        assert device[7] is None
        assert device[8] is not None
        assert device[9] == 1
