"""
Web Push (notificações mesmo com o navegador fechado), via Service Worker.

IMPORTANTE:
- Web Push "de verdade" exige HTTPS (secure context) na maioria dos navegadores.
- Em HTTP por IP local, normalmente funciona apenas "tempo real" com a página aberta (WebSocket),
  mas o push do sistema tende a ser bloqueado (especialmente no celular).

Este módulo:
- Gera chaves VAPID automaticamente se não existirem (salvas em /data).
- Armazena subscriptions no SQLite.
- Envia push para todas as subscriptions quando chega um novo chamado.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from pywebpush import webpush, WebPushException  # pip install pywebpush
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption
)

from .database import SessionLocal
from .models import PushSubscription


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

VAPID_PRIVATE_PATH = os.path.join(DATA_DIR, "vapid_private.pem")
VAPID_PUBLIC_PATH = os.path.join(DATA_DIR, "vapid_public.txt")

# "sub" é obrigatório no VAPID. Pode ser um e-mail ou URL.
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:ti@local")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _generate_vapid_keys() -> tuple[str, str]:
    """
    Gera um par de chaves VAPID (ES256).

    Retorna:
        (private_pem_str, public_key_b64url)
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    ).decode("utf-8")

    public_key = private_key.public_key()
    nums = public_key.public_numbers()
    x = nums.x.to_bytes(32, "big")
    y = nums.y.to_bytes(32, "big")
    uncompressed = b"\x04" + x + y
    public_b64 = _b64url_encode(uncompressed)
    return private_pem, public_b64


def ensure_vapid_keys() -> dict[str, str]:
    """
    Garante que as chaves VAPID existam em /data.
    Retorna {"public_key": ..., "private_key_path": ...}
    """
    if os.path.exists(VAPID_PRIVATE_PATH) and os.path.exists(VAPID_PUBLIC_PATH):
        return {
            "public_key": Path(VAPID_PUBLIC_PATH).read_text(encoding="utf-8").strip(),
            "private_key_path": VAPID_PRIVATE_PATH,
        }

    private_pem, public_b64 = _generate_vapid_keys()
    Path(VAPID_PRIVATE_PATH).write_text(private_pem, encoding="utf-8")
    Path(VAPID_PUBLIC_PATH).write_text(public_b64, encoding="utf-8")
    return {"public_key": public_b64, "private_key_path": VAPID_PRIVATE_PATH}


def get_public_key() -> str:
    return ensure_vapid_keys()["public_key"]


def upsert_subscription(db: Session, subscription: dict[str, Any], user_agent: Optional[str] = None) -> None:
    endpoint = (subscription.get("endpoint") or "").strip()
    if not endpoint:
        return

    sub_json = json.dumps(subscription, ensure_ascii=False)
    existing = db.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).scalar_one_or_none()

    now = datetime.utcnow()
    if existing:
        existing.subscription_json = sub_json
        existing.user_agent = user_agent
        existing.updated_at = now
    else:
        db.add(PushSubscription(
            endpoint=endpoint,
            subscription_json=sub_json,
            user_agent=user_agent,
            created_at=now,
            updated_at=now,
        ))


def delete_subscription(db: Session, endpoint: str) -> None:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return
    existing = db.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).scalar_one_or_none()
    if existing:
        db.delete(existing)


def _send_push_to_all(payload: dict[str, Any]) -> None:
    """
    Envia push para todas as subscriptions armazenadas.
    Se alguma subscription estiver inválida (410/404), ela é removida.
    """
    keys = ensure_vapid_keys()
    private_key_path = keys["private_key_path"]

    db = SessionLocal()
    try:
        subs = db.execute(select(PushSubscription)).scalars().all()
        to_delete: list[str] = []

        data = json.dumps(payload, ensure_ascii=False)

        for sub in subs:
            try:
                info = json.loads(sub.subscription_json)
                webpush(
                    subscription_info=info,
                    data=data,
                    vapid_private_key=private_key_path,
                    vapid_claims={"sub": VAPID_SUBJECT},
                )
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                # 404/410 = subscription expirada / inválida
                if status in (404, 410):
                    to_delete.append(sub.endpoint)
            except Exception:
                # qualquer outro erro: não derruba tudo
                pass

        for ep in to_delete:
            delete_subscription(db, ep)

        if to_delete:
            db.commit()
    finally:
        db.close()


def enqueue_push(payload: dict[str, Any]) -> None:
    """
    Dispara o envio de push em background (não bloqueia o recebimento do socket).
    """
    t = threading.Thread(target=_send_push_to_all, args=(payload,), daemon=True)
    t.start()


def build_ticket_push_payload(pc_name: str, problem: str, ticket_id: int | None = None) -> dict[str, Any]:
    title = "Novo chamado"
    body = f"{pc_name}: {problem}" if pc_name else f"{problem}"
    url = "/tickets"
    if ticket_id:
        # se você quiser no futuro abrir diretamente o ticket, dá pra colocar uma rota específica
        url = "/tickets"
    return {
        "type": "ticket_created",
        "title": title,
        "body": body,
        "url": url,
        "ticket_id": ticket_id,
        "pc_name": pc_name,
        "problem": problem,
    }
