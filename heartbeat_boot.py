# heartbeat_boot.py
# Heartbeat HEADLESS (sem janela) para rodar como SYSTEM já no BOOT, antes do
# login. Faz a máquina aparecer "online" no painel da TI mesmo na tela de login,
# e informa se há usuário logado ou não ("login feito: sim/não").
#
# Não tem GUI: é só descoberta do servidor + envio periódico de "status_online".
# As constantes do protocolo PRECISAM bater com app/chamados_socket.py.

import os
import sys
import json
import time
import socket
import ipaddress
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil

# ===== Configs (mesmas envs do cliente/servidor) =====
PORTA = int(os.getenv("CHAMADOS_PORT", "5050"))
DISCOVERY_PORT = int(os.getenv("CHAMADOS_DISCOVERY_PORT", str(PORTA)))
FORCED_SERVER = os.getenv("CHAMADOS_SERVER", "").strip()
CONNECT_TIMEOUT = float(os.getenv("CHAMADOS_TIMEOUT", "0.5"))
SCAN_WORKERS = int(os.getenv("CHAMADOS_SCAN_WORKERS", "128"))
DEFAULT_PREFIX = int(os.getenv("CHAMADOS_PREFIX", "24"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "15"))

# ===== Protocolo de descoberta (igual a chamados_socket.py / Professor_auto.py) =====
SERVICE_NAME = "manutencao_chamados"
DISCOVERY_MAGIC = b"MANUT_DISCOVER?"
DISCOVERY_REPLY_PREFIX = b"MANUT_HERE "


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# Cache próprio (não disputa arquivo com a GUI).
CACHE_FILE = os.path.join(_base_dir(), "chamados_server_cache_boot.json")


# ---------------- Login: tem usuário logado? ----------------
def usuario_logado():
    """Retorna o nome do usuário interativo logado, ou None se ninguém (tela de login).

    Rodando como SYSTEM, psutil.users() lista as sessões interativas.
    """
    try:
        for u in psutil.users():
            nome = (u.name or "").strip()
            if nome:
                return nome
    except Exception:
        pass
    return None


def coletar_diagnostico(login_user):
    diag = {
        "origem": "boot",
        "login_ativo": bool(login_user),
        "usuario_logado": login_user,
    }
    try:
        diag["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        diag["mem_percent"] = mem.percent
        system_drive = os.getenv("SystemDrive", "C:") + "\\"
        diag["disco_percent"] = psutil.disk_usage(system_drive).percent
        diag["tempo_atividade_s"] = int(time.time() - psutil.boot_time())
    except Exception as e:
        diag["erro"] = str(e)
    return diag


# ---------------- TCP / UDP ----------------
def _tcp_send_json(ip, porta, payload, timeout):
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, porta))
            s.sendall(data)
        return True
    except Exception:
        return False


def _tcp_ping(ip, porta, timeout):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, porta))
            s.sendall(json.dumps({"ping": 1}).encode("utf-8"))
            try:
                s.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            data = s.recv(512)
        if not data:
            return False
        try:
            return json.loads(data.decode("utf-8", errors="replace")).get("service") == SERVICE_NAME
        except Exception:
            return False
    except Exception:
        return False


def _get_private_ipv4s():
    ips = []
    try:
        for _, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    try:
                        obj = ipaddress.ip_address(a.address)
                        if obj.is_private and not obj.is_loopback:
                            ips.append(a.address)
                    except Exception:
                        pass
    except Exception:
        pass
    seen, out = set(), []
    for ip in ips:
        if ip not in seen:
            seen.add(ip); out.append(ip)
    return out


def _udp_discover(porta, timeout=1.5):
    targets = ["255.255.255.255"]
    for ip in _get_private_ipv4s():
        try:
            net = ipaddress.ip_network(f"{ip}/{DEFAULT_PREFIX}", strict=False)
            targets.append(str(net.broadcast_address))
        except Exception:
            pass
    targets = list(dict.fromkeys(targets))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        for tgt in targets:
            try:
                sock.sendto(DISCOVERY_MAGIC, (tgt, porta))
            except Exception:
                pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
            except Exception:
                break
            if data.startswith(DISCOVERY_REPLY_PREFIX):
                try:
                    if json.loads(data[len(DISCOVERY_REPLY_PREFIX):].decode("utf-8")).get("service") == SERVICE_NAME:
                        return addr[0]
                except Exception:
                    return addr[0]
        return ""
    finally:
        sock.close()


def _load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return (json.load(f).get("ip") or "").strip()
    except Exception:
        return ""


def _save_cache(ip):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ip": ip, "saved_at": datetime.now().isoformat()}, f)
    except Exception:
        pass


def discover_server():
    if FORCED_SERVER and _tcp_ping(FORCED_SERVER, PORTA, CONNECT_TIMEOUT):
        _save_cache(FORCED_SERVER)
        return FORCED_SERVER

    udp_ip = _udp_discover(DISCOVERY_PORT, timeout=max(1.0, CONNECT_TIMEOUT * 3))
    if udp_ip and _tcp_ping(udp_ip, PORTA, CONNECT_TIMEOUT):
        _save_cache(udp_ip)
        return udp_ip

    cached = _load_cache()
    if cached and _tcp_ping(cached, PORTA, CONNECT_TIMEOUT):
        return cached

    for ip_str in _get_private_ipv4s():
        net = ipaddress.ip_network(f"{ip_str}/{DEFAULT_PREFIX}", strict=False)
        hosts = [str(h) for h in net.hosts()]
        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
            futures = {ex.submit(_tcp_ping, h, PORTA, CONNECT_TIMEOUT): h for h in hosts}
            for fut in as_completed(futures):
                if fut.result():
                    found = futures[fut]
                    _save_cache(found)
                    return found
    return ""


def main():
    nome_pc = socket.gethostname()
    server_ip = ""

    while True:
        login_user = usuario_logado()
        payload = {
            "nome": nome_pc,
            "usuario": login_user,  # None => "sem login" no painel
            "hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "problema": "status_online",  # nunca vira chamado
            "diagnostico": coletar_diagnostico(login_user),
        }

        if not server_ip or not _tcp_send_json(server_ip, PORTA, payload, CONNECT_TIMEOUT):
            server_ip = discover_server()
            if server_ip:
                _tcp_send_json(server_ip, PORTA, payload, CONNECT_TIMEOUT)

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()
