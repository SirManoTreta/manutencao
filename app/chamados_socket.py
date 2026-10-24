"""Servidor TCP de chamados (integra o Professor.py direto no site).

O Professor.py envia um JSON via socket TCP para a porta 5050 (por padrão),
com campos como: nome (hostname), usuario, problema e diagnostico.

Aqui nós:
- Atualizamos/registramos um heartbeat (status_online) por computador.
- Criamos um Ticket quando o problema NÃO for status_online.

Esse servidor roda em thread, iniciado no startup do FastAPI.
"""

from __future__ import annotations

import json
import os
import socket
import socketserver
import threading
from datetime import datetime

from .database import SessionLocal
from .models import Machine, Ticket, MachineHeartbeat
from .realtime import broadcast_from_thread
from .push import enqueue_push, build_ticket_push_payload
from .fcm import enqueue_ticket_push


DEFAULT_HOST = os.getenv("CHAMADOS_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("CHAMADOS_PORT", "5050"))
# Porta da descoberta por broadcast UDP. Por padrão usa a mesma do TCP, mas é
# configurável: em algumas máquinas um serviço do Windows (svchost) já ocupa a
# UDP 5050, então dá para mover a descoberta sem mexer no TCP.
DEFAULT_DISCOVERY_PORT = int(os.getenv("CHAMADOS_DISCOVERY_PORT", str(DEFAULT_PORT)))

# Identificador do serviço usado tanto no ACK do "ping" TCP quanto na
# descoberta por broadcast UDP. O cliente (Professor_auto.py) confere essa
# string para ter CERTEZA de que achou o servidor certo (e não outro
# processo qualquer ocupando a porta 5050).
SERVICE_NAME = "manutencao_chamados"

# Descoberta por broadcast UDP: o cliente manda DISCOVERY_MAGIC para o
# broadcast da rede e o servidor responde com DISCOVERY_REPLY_PREFIX + JSON.
DISCOVERY_MAGIC = b"MANUT_DISCOVER?"
DISCOVERY_REPLY_PREFIX = b"MANUT_HERE "


def _safe_json_dumps(obj) -> str | None:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return None


def _read_all(request, max_bytes: int = 256 * 1024) -> bytes:
    """Lê tudo até EOF (o client fecha o socket após enviar)."""
    data = b""
    while True:
        chunk = request.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) >= max_bytes:
            break
    return data


class _TicketTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        raw = _read_all(self.request)
        if not raw:
            return

        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            return

        # "ping" de descoberta/health-check: responde um ACK identificando o
        # serviço para o cliente confirmar que é o servidor certo.
        if payload.get("ping"):
            try:
                ack = json.dumps({"service": SERVICE_NAME, "ok": True}).encode("utf-8")
                self.request.sendall(ack)
            except Exception:
                pass
            return

        pc_name = str(payload.get("nome", "")).strip()
        if not pc_name:
            return

        usuario = payload.get("usuario")
        usuario = str(usuario).strip() if usuario is not None else None
        if usuario == "":
            usuario = None

        problema = str(payload.get("problema", "")).strip()
        diagnostico = payload.get("diagnostico") or {}

        now = datetime.utcnow()

        db = SessionLocal()
        ticket_created = False
        created_ticket_id = None
        created_problem = None
        try:
            machine = db.query(Machine).filter(Machine.machine_name == pc_name).first()
            machine_id = machine.id if machine else None

            # Heartbeat (sempre atualiza)
            hb = db.query(MachineHeartbeat).filter(MachineHeartbeat.pc_name == pc_name).first()
            if not hb:
                hb = MachineHeartbeat(pc_name=pc_name)
                db.add(hb)

            hb.machine_id = machine_id
            hb.last_seen = now
            hb.last_user = usuario
            hb.diagnostics_json = _safe_json_dumps(diagnostico)

            # Ticket (só quando for um problema real)
            if problema and problema not in (
                "status_online",
                "Solicitação iniciada - aguardando seleção",
            ):
                t = Ticket(
                    machine_id=machine_id,
                    pc_name=pc_name,
                    reported_user=usuario,
                    problem=problema,
                    diagnostics_json=_safe_json_dumps(diagnostico),
                    status="OPEN",
                    created_at=now,
                )
                db.add(t)
                db.flush()  # gera t.id antes do commit
                created_ticket_id = t.id
                created_problem = problema
                ticket_created = True

            db.commit()
        finally:
            db.close()

        # Notifica a UI em tempo real (sem recarregar a página)
        if ticket_created:
            payload = {"type": "ticket_created", "pc_name": pc_name, "problem": created_problem, "ticket_id": created_ticket_id}
            broadcast_from_thread(payload)
            # Push do sistema (Service Worker) — só vai disparar se o cliente tiver subscription ativa
            enqueue_push(build_ticket_push_payload(pc_name=pc_name, problem=created_problem or "Novo chamado", ticket_id=created_ticket_id))
            # FCM nativo coexiste com WebSocket e Web Push; só após persistir o chamado.
            enqueue_ticket_push(created_ticket_id)


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


_lock = threading.Lock()
_server: _ThreadingTCPServer | None = None
_thread: threading.Thread | None = None

# Descoberta UDP
_udp_thread: threading.Thread | None = None
_udp_stop = threading.Event()


def _udp_discovery_loop(host: str, port: int, stop_event: threading.Event) -> None:
    """Responde a pacotes de descoberta por broadcast UDP.

    O cliente envia DISCOVERY_MAGIC para o broadcast da rede; aqui respondemos
    diretamente ao remetente com um JSON identificando o serviço e a porta TCP.
    O cliente descobre o IP do servidor a partir do endereço de origem do pacote.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as e:
        print(f"[CHAMADOS] Descoberta UDP indisponível ({e}). Cliente usará varredura como fallback.")
        sock.close()
        return

    sock.settimeout(0.5)
    reply = DISCOVERY_REPLY_PREFIX + json.dumps(
        {"service": SERVICE_NAME, "tcp_port": DEFAULT_PORT}
    ).encode("utf-8")

    print(f"[CHAMADOS] Descoberta UDP escutando em {host}:{port}")
    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            break
        if DISCOVERY_MAGIC in data:
            try:
                sock.sendto(reply, addr)
            except Exception:
                pass
    sock.close()


def start_chamados_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Inicia o servidor TCP + descoberta UDP em background (idempotente)."""
    global _server, _thread, _udp_thread
    with _lock:
        if _server is not None:
            return
        _server = _ThreadingTCPServer((host, port), _TicketTCPHandler)
        _thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _thread.start()
        print(f"[CHAMADOS] Servidor TCP escutando em {host}:{port}")

        # Sobe a descoberta UDP (porta configurável; por padrão a mesma do TCP).
        _udp_stop.clear()
        _udp_thread = threading.Thread(
            target=_udp_discovery_loop,
            args=(host, DEFAULT_DISCOVERY_PORT, _udp_stop),
            daemon=True,
        )
        _udp_thread.start()


def stop_chamados_server() -> None:
    """Para o servidor TCP + descoberta UDP (idempotente)."""
    global _server, _thread, _udp_thread
    with _lock:
        if _server is None:
            return
        try:
            _server.shutdown()
            _server.server_close()
        finally:
            _server = None
            _thread = None

        _udp_stop.set()
        _udp_thread = None
        print("[CHAMADOS] Servidor TCP finalizado")
