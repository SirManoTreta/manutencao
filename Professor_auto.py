# Professor_auto.py
# Cliente de chamados (professor) com:
# - Descoberta automática do servidor (porta 5050) na rede local
# - UI em Tkinter com rolagem + mais opções
# - Heartbeat "status_online" (bem mais leve)
# - Atalho de emergência (Ctrl+Shift+E)
#
# Dependências:
#   pip install psutil keyboard
#
# Observação:
#   Este script envia JSON via TCP, compatível com o servidor embutido no seu site de manutenção.

import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import socket
import json
import time
import getpass
import psutil
import threading
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

import keyboard  # Requer: pip install keyboard


def _base_dir() -> str:
    """Pasta-base para arquivos ao lado do programa.

    Quando empacotado com PyInstaller (--onefile), `__file__` aponta para uma
    pasta temporária; aí usamos a pasta do .exe. Em script normal, a pasta do .py.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ===== Configs =====
PORTA = int(os.getenv("CHAMADOS_PORT", "5050"))

# Se você quiser forçar um IP/host fixo sem scan, defina:
#   set CHAMADOS_SERVER=10.0.0.60
# ou em Linux/mac:
#   export CHAMADOS_SERVER=10.0.0.60
FORCED_SERVER = os.getenv("CHAMADOS_SERVER", "").strip()

# Cache local do último servidor que funcionou
CACHE_FILE = os.path.join(_base_dir(), "chamados_server_cache.json")

# Heartbeat: manda "status_online" a cada N segundos (não precisa ser 3s)
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "15"))

# Timeout curto pra descoberta / envio
CONNECT_TIMEOUT = float(os.getenv("CHAMADOS_TIMEOUT", "0.35"))

# Quantos workers no scan (equilíbrio entre rapidez e não “martelar” demais a rede)
SCAN_WORKERS = int(os.getenv("CHAMADOS_SCAN_WORKERS", "128"))

# Se a sua rede não for /24, você pode forçar o prefixo aqui (ex: 23).
DEFAULT_PREFIX = int(os.getenv("CHAMADOS_PREFIX", "24"))

# ===== Protocolo de descoberta (precisa bater com app/chamados_socket.py) =====
SERVICE_NAME = "manutencao_chamados"
DISCOVERY_MAGIC = b"MANUT_DISCOVER?"
DISCOVERY_REPLY_PREFIX = b"MANUT_HERE "
# Porta do broadcast UDP. Deve ser a mesma do servidor (CHAMADOS_DISCOVERY_PORT).
DISCOVERY_PORT = int(os.getenv("CHAMADOS_DISCOVERY_PORT", str(PORTA)))


# ===== Diagnóstico =====
def coletar_diagnostico():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()

        # Disco no Windows: melhor usar a unidade do sistema
        system_drive = os.getenv("SystemDrive", "C:") + "\\"
        disco = psutil.disk_usage(system_drive)

        return {
            "cpu_percent": cpu,
            "mem_percent": mem.percent,
            "mem_total_gb": round(mem.total / (1024**3), 2),
            "disco_percent": disco.percent,
            "disco_total_gb": round(disco.total / (1024**3), 2),
            "tempo_atividade_s": int(time.time() - psutil.boot_time()),
        }
    except Exception as e:
        return {"erro": str(e)}


# ===== TCP util =====
def _tcp_send_json(ip: str, porta: int, payload: dict, timeout: float) -> bool:
    """Envia um JSON em uma conexão TCP curta. Retorna True se conectou e enviou."""
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, porta))
            s.sendall(data)
        return True
    except Exception:
        return False


def _tcp_ping(ip: str, porta: int, timeout: float) -> bool:
    """Confirma que há o servidor CERTO em ip:porta.

    Diferente de só testar a porta aberta, aqui lemos o ACK e validamos o
    nome do serviço — assim não confundimos com outro processo na porta 5050.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, porta))
            s.sendall(json.dumps({"ping": 1}).encode("utf-8"))
            # Sinaliza fim de envio para o servidor (que lê até EOF) responder.
            try:
                s.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            data = s.recv(512)
        if not data:
            return False
        try:
            info = json.loads(data.decode("utf-8", errors="replace"))
            return info.get("service") == SERVICE_NAME
        except Exception:
            return False
    except Exception:
        return False


def _udp_discover(porta: int, timeout: float = 1.0) -> str:
    """Descoberta instantânea por broadcast UDP. Retorna IP do servidor ou ''.

    Manda DISCOVERY_MAGIC para o broadcast geral e para o broadcast de cada
    interface privada; o servidor responde com DISCOVERY_REPLY_PREFIX + JSON.
    """
    targets = ["255.255.255.255"]
    for ip in _get_private_ipv4s():
        try:
            net = ipaddress.ip_network(f"{ip}/{DEFAULT_PREFIX}", strict=False)
            targets.append(str(net.broadcast_address))
        except Exception:
            pass
    targets = list(dict.fromkeys(targets))  # remove duplicadas mantendo ordem

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
            except socket.timeout:
                break
            except Exception:
                break
            if data.startswith(DISCOVERY_REPLY_PREFIX):
                try:
                    info = json.loads(data[len(DISCOVERY_REPLY_PREFIX):].decode("utf-8"))
                    if info.get("service") == SERVICE_NAME:
                        return addr[0]
                except Exception:
                    # veio o prefixo certo, mas JSON estranho: ainda assim é nosso servidor
                    return addr[0]
        return ""
    finally:
        sock.close()


# ===== Descoberta do servidor =====
def _get_private_ipv4s():
    """Coleta IPv4s privados das interfaces ativas (10.x, 172.16-31.x, 192.168.x)."""
    ips = []
    try:
        for _, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    ip = a.address
                    try:
                        ip_obj = ipaddress.ip_address(ip)
                        if ip_obj.is_private and not ip_obj.is_loopback:
                            ips.append(ip)
                    except Exception:
                        pass
    except Exception:
        pass

    # fallback simples
    if not ips:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_private and not ip_obj.is_loopback:
                ips.append(ip)
        except Exception:
            pass

    # remove duplicadas mantendo ordem
    seen = set()
    out = []
    for ip in ips:
        if ip not in seen:
            out.append(ip)
            seen.add(ip)
    return out


def _load_cached_server():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        ip = obj.get("ip", "").strip()
        if ip:
            return ip
    except Exception:
        pass
    return ""


def _save_cached_server(ip: str):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ip": ip, "saved_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def discover_server(porta: int, timeout: float, prefix: int = 24) -> str:
    """
    Tenta encontrar automaticamente o servidor na porta indicada.
    Ordem (do mais rápido/confiável ao fallback):
      1) CHAMADOS_SERVER (se definido)
      2) Broadcast UDP (instantâneo, cobre a sub-rede inteira)
      3) cache local (último IP que funcionou)
      4) scan nas redes /24 das interfaces privadas
    Retorna IP (string) ou "".
    """
    # 1) Forçado
    if FORCED_SERVER:
        if _tcp_ping(FORCED_SERVER, porta, timeout):
            _save_cached_server(FORCED_SERVER)
            return FORCED_SERVER

    # 2) Broadcast UDP — encontra o servidor sem varrer a rede
    udp_ip = _udp_discover(DISCOVERY_PORT, timeout=max(1.0, timeout * 3))
    if udp_ip and _tcp_ping(udp_ip, porta, timeout):
        _save_cached_server(udp_ip)
        return udp_ip

    # 3) Cache
    cached = _load_cached_server()
    if cached and _tcp_ping(cached, porta, timeout):
        return cached

    # 4) Scan por /24 das interfaces
    local_ips = _get_private_ipv4s()
    if not local_ips:
        return ""

    # Cria lista de hosts por rede (exclui o próprio IP pra não perder tempo)
    def make_hosts(ip_str: str):
        net = ipaddress.ip_network(f"{ip_str}/{prefix}", strict=False)
        hosts = [str(h) for h in net.hosts()]
        # dá prioridade ao gateway comum (.1) e a IPs típicos de servidor (.50-.70), mas sem travar nisso
        preferred = []
        for cand in (str(net.network_address + 1),):
            if cand in hosts:
                preferred.append(cand)
        for last_octet in range(50, 71):
            cand = str(ipaddress.ip_address(int(net.network_address) + last_octet))
            if cand in hosts:
                preferred.append(cand)

        # ordem final: preferidos primeiro + o resto
        rest = [h for h in hosts if h not in preferred]
        return preferred + rest

    for ip_str in local_ips:
        hosts = make_hosts(ip_str)

        # worker
        def check(host: str) -> str:
            ok = _tcp_ping(host, porta, timeout)
            return host if ok else ""

        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
            futures = {ex.submit(check, h): h for h in hosts}
            for fut in as_completed(futures):
                found = fut.result()
                if found:
                    _save_cached_server(found)
                    return found

    return ""


# ===== App (UI) =====
class ScrollableFrame(tk.Frame):
    """Frame rolável para caber várias opções."""
    def __init__(self, parent):
        super().__init__(parent)

        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # rolagem com roda do mouse
        def _on_mousewheel(event):
            # Windows: event.delta vem em múltiplos de 120
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)


class ProfessorApp:
    def __init__(self):
        self.nome_pc = socket.gethostname()
        self.usuario = getpass.getuser()
        self.server_ip = ""

        self.root = tk.Tk()
        self.root.title("Relatar Problema - Professor (Auto)")

        # Top info
        tk.Label(self.root, text=f"Computador: {self.nome_pc}").pack()
        tk.Label(self.root, text=f"Usuário: {self.usuario}").pack(pady=(0, 6))

        self.lbl_server = tk.Label(self.root, text="Servidor: procurando automaticamente…")
        self.lbl_server.pack(pady=(0, 10))

        # Entrada “Outro”
        self.other_frame = tk.Frame(self.root)
        self.other_frame.pack(fill="x", padx=10)

        tk.Label(self.other_frame, text="Se for 'Outro', descreva aqui:").pack(anchor="w")
        self.other_text = tk.Entry(self.other_frame)
        self.other_text.pack(fill="x")

        # Área rolável com botões
        tk.Label(self.root, text="Selecione o problema técnico:").pack(pady=8)

        self.scroll = ScrollableFrame(self.root)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self.buttons = []
        self._build_buttons()

        # rodapé
        self.lbl_status = tk.Label(self.root, text="Inicializando…")
        self.lbl_status.pack(pady=(0, 8))

        # desabilita até achar servidor
        self._set_buttons_state("disabled")

        # Começa descoberta em thread
        threading.Thread(target=self._startup_flow, daemon=True).start()

        # Fechar é restrito à TI: o X / Alt+F4 apenas minimizam.
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Hotkey de saída (somente TI): Ctrl+Shift+Q. Disponível desde o início.
        self._start_exit_hotkey()

    def _build_buttons(self):
        # Você pode editar essa lista à vontade.
        # Sugestão: manter textos simples e diretos (ajuda muito na triagem).
        opcoes = [
            # Rede/Internet
            "Sem internet",
            "Wi‑Fi não conecta",
            "Internet lenta",
            "Sites não abrem",
            "Sem acesso ao login/senha",
            # Computador
            "Computador não liga",
            "Computador travando / congelando",
            "Computador muito lento",
            "Reiniciando sozinho",
            "Tela azul / erro no Windows",
            "Teclado ou mouse não funciona",
            "USB não reconhece (pendrive etc.)",
            # Áudio/Vídeo
            "Sem áudio",
            "Microfone não funciona",
            "Webcam não funciona",
            "Monitor não liga",
            "Monitor sem imagem (mas PC ligado)",
            "Imagem tremendo / resolução errada",
            # Projetor / TV / Lousa
            "Projetor sem imagem",
            "HDMI/DisplayPort sem sinal",
            "Som do projetor/TV não sai",
            "Lousa digital não responde",
            # Impressão (se existir na sala)
            "Impressora não imprime",
            "Impressora atolou papel",
            # Geral
            "Solicitar visita da TI (verificar presencialmente)",
            "Outro problema geral (descrever no campo acima)",
        ]

        # seções simples (pra ficar menos caos visual)
        def add_section(title: str):
            tk.Label(self.scroll.inner, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))

        def add_button(text: str):
            btn = tk.Button(self.scroll.inner, text=text, width=40, command=lambda t=text: self._on_select(t))
            btn.pack(pady=2, anchor="w")
            self.buttons.append(btn)

        # Seções
        add_section("Rede / Acesso")
        for t in opcoes[0:5]:
            add_button(t)

        add_section("Computador")
        for t in opcoes[5:12]:
            add_button(t)

        add_section("Áudio / Vídeo")
        for t in opcoes[12:18]:
            add_button(t)

        add_section("Projetor / TV / Lousa")
        for t in opcoes[18:22]:
            add_button(t)

        add_section("Impressão")
        for t in opcoes[22:24]:
            add_button(t)

        add_section("Geral")
        for t in opcoes[24:]:
            add_button(t)

    def _set_buttons_state(self, state: str):
        for b in self.buttons:
            try:
                b.configure(state=state)
            except Exception:
                pass

    def _startup_flow(self):
        # Descobre servidor
        self._ui_status("Procurando servidor de chamados na rede…")
        ip = discover_server(PORTA, CONNECT_TIMEOUT, prefix=DEFAULT_PREFIX)
        if not ip:
            self.server_ip = ""
            self._ui_server("Servidor: NÃO encontrado ❌")
            self._ui_status("Não encontrei o servidor. Chame a TI. (Dica: defina CHAMADOS_SERVER para forçar.)")
            return

        self.server_ip = ip
        self._ui_server(f"Servidor: {ip}:{PORTA} ✅")
        self._ui_status("Conectado. Você já pode selecionar uma opção.")
        self._set_buttons_state("normal")

        # Envia “início”
        self._send("status_online")
        self._send("Solicitação iniciada - aguardando seleção")

        # Heartbeat
        self._start_heartbeat()

        # Emergência hotkey
        self._start_emergency_hotkey()

    def _ui_server(self, text: str):
        self.root.after(0, lambda: self.lbl_server.configure(text=text))

    def _ui_status(self, text: str):
        self.root.after(0, lambda: self.lbl_status.configure(text=text))

    def _send(self, problema: str, diagnostico=None, silent: bool = True) -> bool:
        if not self.server_ip:
            return False

        if diagnostico is None:
            diagnostico = coletar_diagnostico()

        payload = {
            "nome": self.nome_pc,
            "usuario": self.usuario,
            "hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "problema": problema,
            "diagnostico": diagnostico,
        }

        ok = _tcp_send_json(self.server_ip, PORTA, payload, CONNECT_TIMEOUT)
        if not ok and not silent:
            messagebox.showerror("Erro", "Não foi possível contatar o servidor de TI.")
        return ok

    def _start_heartbeat(self):
        def loop():
            while True:
                if self.server_ip:
                    ok = self._send("status_online", diagnostico=coletar_diagnostico(), silent=True)
                    if not ok:
                        # Perdeu o servidor (mudou de IP, caiu, trocou de rede): redescobre.
                        self._ui_status("Conexão perdida. Reconectando ao servidor…")
                        self._rediscover()
                else:
                    # Ainda sem servidor: continua tentando achar.
                    self._rediscover()
                time.sleep(HEARTBEAT_INTERVAL)

        threading.Thread(target=loop, daemon=True).start()

    def _rediscover(self):
        """Procura o servidor de novo e reabilita os botões se achar."""
        ip = discover_server(PORTA, CONNECT_TIMEOUT, prefix=DEFAULT_PREFIX)
        if ip:
            self.server_ip = ip
            self._ui_server(f"Servidor: {ip}:{PORTA} ✅")
            self._ui_status("Reconectado. Você já pode selecionar uma opção.")
            self._set_buttons_state("normal")
        else:
            self.server_ip = ""
            self._ui_server("Servidor: NÃO encontrado ❌")
            self._ui_status("Procurando servidor na rede…")
            self._set_buttons_state("disabled")

    def _start_emergency_hotkey(self):
        def escutar():
            try:
                keyboard.add_hotkey(
                    "ctrl+shift+e",
                    lambda: self._send("EMERGÊNCIA - tela travada ou sem imagem", diagnostico=coletar_diagnostico(), silent=True)
                )
                # Mantém a thread viva
                keyboard.wait()
            except Exception:
                # Se o keyboard falhar por permissão/política, só ignora
                pass

        threading.Thread(target=escutar, daemon=True).start()

    def _on_select(self, problema: str):
        if "Outro problema geral" in problema:
            desc = self.other_text.get().strip()
            if desc:
                problema = f"Outro: {desc}"
            else:
                problema = "Outro (sem descrição)"

        ok = self._send(problema, silent=False)
        if ok:
            messagebox.showinfo("Enviado", "Problema enviado ao setor de TI.")
        else:
            # tenta redescobrir e reenviar (às vezes o IP mudou)
            self._ui_status("Perdi o servidor. Tentando reencontrar…")
            self._set_buttons_state("disabled")
            threading.Thread(target=self._recover_and_resend, args=(problema,), daemon=True).start()

    def _recover_and_resend(self, problema: str):
        ip = discover_server(PORTA, CONNECT_TIMEOUT, prefix=DEFAULT_PREFIX)
        if not ip:
            self.server_ip = ""
            self._ui_server("Servidor: NÃO encontrado ❌")
            self._ui_status("Servidor não encontrado. Chame a TI.")
            return

        self.server_ip = ip
        self._ui_server(f"Servidor: {ip}:{PORTA} ✅")
        self._set_buttons_state("normal")
        ok = self._send(problema, silent=False)
        if ok:
            self._ui_status("Reenviado com sucesso.")
        else:
            self._ui_status("Falha ao reenviar. Chame a TI.")

    def _on_close(self):
        # O professor NÃO pode fechar: o programa precisa ficar aberto para a TI
        # acompanhar as máquinas conectadas. O X e o Alt+F4 apenas minimizam.
        try:
            messagebox.showinfo(
                "TI - Monitoramento",
                "Este programa precisa ficar aberto para a TI acompanhar este "
                "computador.\n\nEle será apenas minimizado.\n"
                "(O fechamento é restrito à TI.)",
            )
        except Exception:
            pass
        try:
            self.root.iconify()
        except Exception:
            pass

    def _real_exit(self):
        """Fechamento de verdade (restrito à TI, via hotkey Ctrl+Shift+Q)."""
        try:
            self.root.destroy()
        except Exception:
            pass
        # Encerra o processo de imediato, mesmo com os hooks do keyboard ativos.
        os._exit(0)

    def _start_exit_hotkey(self):
        # 1) Hotkey GLOBAL via 'keyboard' (funciona mesmo sem foco; pode exigir admin).
        def escutar():
            try:
                keyboard.add_hotkey(
                    "ctrl+shift+q",
                    lambda: self.root.after(0, self._real_exit),
                )
                keyboard.wait()
            except Exception:
                # Sem permissão/política: cai no fallback do Tkinter abaixo.
                pass

        threading.Thread(target=escutar, daemon=True).start()

        # 2) Fallback dentro do Tkinter (funciona com a janela em foco, sem admin).
        try:
            self.root.bind_all("<Control-Shift-Q>", lambda e: self._real_exit())
            self.root.bind_all("<Control-Shift-q>", lambda e: self._real_exit())
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ProfessorApp().run()
