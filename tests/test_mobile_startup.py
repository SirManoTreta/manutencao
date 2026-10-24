"""Exercita o lifespan e o TCP reais, em subprocesso e portas efêmeras locais."""
import os
from pathlib import Path
import subprocess
import sys


def test_full_startup_professor_tcp_to_web_mobile_and_shared_database(tmp_path):
    environment = os.environ.copy()
    environment.update({
        "MANUTENCAO_DATA_DIR": str(tmp_path / "startup-data"),
        "CHAMADOS_HOST": "127.0.0.1", "CHAMADOS_PORT": "0",
        "CHAMADOS_DISCOVERY_PORT": "0", "FCM_ENABLED": "false",
    })
    script = r'''
import json
import socket
from fastapi.testclient import TestClient
from app import main, chamados_socket

with TestClient(main.app) as client:
    assert client.post('/setup', data={'username': 'startup-admin', 'password': 'test-password'}, follow_redirects=False).status_code == 303
    assert client.get('/dashboard').status_code == 200
    login = client.post('/api/v1/auth/login', json={'username': 'startup-admin', 'password': 'test-password'})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    machine = client.post('/api/v1/machines', headers=headers, json={
        'machine_name': 'PC-INTEGRACAO', 'room_name': '7º Ano A',
        'username': 'professor', 'ip': '192.0.2.10', 'profile': 'B',
    })
    assert machine.status_code == 201, machine.text
    with client.websocket_connect('/ws/tickets') as web:
        assert web.receive_json()['type'] == 'ready'
        with client.websocket_connect('/ws/v1/tickets', headers=headers) as mobile:
            assert mobile.receive_json()['type'] == 'ready'
            with socket.create_connection(chamados_socket._server.server_address, timeout=5) as professor:
                professor.sendall(json.dumps({'nome': 'PC-INTEGRACAO', 'usuario': 'professor',
                    'problema': 'Projetor sem imagem', 'diagnostico': {'rede': 'ok'}}).encode())
                professor.shutdown(socket.SHUT_WR)
                assert professor.recv(1024) == b''
            web_event = web.receive_json()
            mobile_event = mobile.receive_json()
            assert web_event == mobile_event
            assert mobile_event['type'] == 'ticket_created'
            ticket_id = mobile_event['ticket_id']
            assert client.post(f'/api/v1/tickets/{ticket_id}/take', headers=headers).status_code == 200
            assert web.receive_json()['type'] == 'ticket_taken'
            assert mobile.receive_json()['type'] == 'ticket_taken'
            legacy = client.get('/api/tickets?status=IN_PROGRESS').json()['tickets']
            assert len(legacy) == 1 and legacy[0]['id'] == ticket_id
            assert client.get('/api/v1/online', headers=headers).json()[0]['login_active'] is True
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/v1/auth/me', headers=headers).status_code == 401
main.engine.dispose()
print('STARTUP_TCP_WEB_MOBILE_OK')
'''
    result = subprocess.run(
        [sys.executable, "-c", script], env=environment,
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STARTUP_TCP_WEB_MOBILE_OK" in result.stdout
