# watchdog.py
# Mantém o "Relatar Problema - TI.exe" sempre aberto: se o professor matar pelo
# Gerenciador de Tarefas, este vigia reabre em poucos segundos.
#
# Distribuído junto na MESMA pasta do exe principal. É iniciado pela Tarefa
# Agendada (no logon); o Agendador, por sua vez, reabre este vigia se ele cair.

import os
import sys
import time
import subprocess

CREATE_NO_WINDOW = 0x08000000  # evita piscar janelas de console
APP_NAME = "Relatar Problema - TI.exe"
CHECK_INTERVAL = 5  # segundos


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_PATH = os.path.join(_base_dir(), APP_NAME)


def _is_running(exe_name: str) -> bool:
    """Checa via tasklist (nativo do Windows, sem dependências)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
        ).stdout or ""
        return exe_name.lower() in out.lower()
    except Exception:
        return False


def _launch() -> None:
    try:
        subprocess.Popen([APP_PATH], cwd=_base_dir())
    except Exception:
        pass


def main() -> None:
    # Pequena espera inicial (deixa o desktop terminar de carregar no logon).
    time.sleep(3)
    while True:
        try:
            if os.path.exists(APP_PATH) and not _is_running(APP_NAME):
                _launch()
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
