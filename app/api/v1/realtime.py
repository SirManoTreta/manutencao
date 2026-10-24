"""Canal nativo: Authorization no handshake, nunca token na URL/logs."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...database import SessionLocal
from ...realtime import manager
from .dependencies import resolve_session

router = APIRouter()


def _is_valid(token: str) -> bool:
    with SessionLocal() as db:
        return resolve_session(db, token) is not None


@router.websocket("/ws/v1/tickets")
async def mobile_tickets(ws: WebSocket):
    scheme, _, token = ws.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not await asyncio.to_thread(_is_valid, token):
        await ws.close(code=1008)
        return

    async def authorized():
        return await asyncio.to_thread(_is_valid, token)

    await manager.connect(ws, authorize=authorized)
    try:
        await ws.send_json({"type": "ready"})
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                pass
            if not await authorized():
                await ws.close(code=1008)
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
