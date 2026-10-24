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
