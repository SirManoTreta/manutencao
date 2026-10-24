"""WebSocket realtime helpers.

Objetivo: permitir que a página /tickets atualize sem recarregar.

O servidor TCP (Professor.py) roda em thread. Quando ele cria um Ticket,
ele chama `broadcast_from_thread(...)` para notificar todos os clientes
conectados via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._authorizers: dict[WebSocket, Callable[[], Awaitable[bool]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, authorize: Callable[[], Awaitable[bool]] | None = None) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
            if authorize:
                self._authorizers[ws] = authorize

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
            self._authorizers.pop(ws, None)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            targets = list(self._connections)

        for ws in targets:
            try:
                authorize = self._authorizers.get(ws)
                if authorize and not await authorize():
                    await ws.close(code=1008)
                    await self.disconnect(ws)
                    continue
                await ws.send_text(data)
            except Exception:
                # conexão morreu, remove
                await self.disconnect(ws)


manager = ConnectionManager()

# Loop principal do FastAPI (capturado no startup). Usado para disparar
# broadcasts a partir da thread do servidor TCP.
MAIN_LOOP: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global MAIN_LOOP
    MAIN_LOOP = loop


def broadcast_from_thread(payload: dict[str, Any]) -> None:
    """Dispara um broadcast de dentro de uma thread (servidor TCP)."""
    if MAIN_LOOP is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(manager.broadcast(payload), MAIN_LOOP)
    except Exception:
        # não deixa thread morrer por causa de websocket
        return
