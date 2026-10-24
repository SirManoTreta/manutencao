"""FCM independente do Web Push; falhas externas não interrompem chamados TCP."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from .database import SessionLocal
from .models import FCMDevice, MobileSession, Ticket, User
from .security import password_fingerprint

logger = logging.getLogger(__name__)
_firebase_lock = threading.Lock()


def _get_firebase_app():
    credential_path = os.getenv("FIREBASE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    enabled = os.getenv("FCM_ENABLED", "true" if credential_path else "false").lower() in ("1", "true", "yes")
    if not enabled:
        return None
    # Import tardio: site existente funciona mesmo antes de instalar firebase-admin.
    import firebase_admin
    from firebase_admin import credentials

    with _firebase_lock:
        try:
            return firebase_admin.get_app("maintenance-mobile")
        except ValueError:
            credential = credentials.Certificate(credential_path) if credential_path else credentials.ApplicationDefault()
            options = {"httpTimeout": 10}
            if os.getenv("FIREBASE_PROJECT_ID"):
                options["projectId"] = os.environ["FIREBASE_PROJECT_ID"]
            return firebase_admin.initialize_app(credential, options=options, name="maintenance-mobile")


def _send_ticket_notification(ticket_id: int) -> None:
    app = _get_firebase_app()
    if app is None:
        return
    from firebase_admin import messaging

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            return
        room = ticket.machine.room_name if ticket.machine else "Não cadastrada"
        body = f"Sala: {room}\nPC: {ticket.pc_name}\nProblema: {ticket.problem}"
        # Só usuários ativos com sessão válida continuam recebendo chamados.
        rows = db.execute(
            select(FCMDevice, MobileSession, User)
            .join(MobileSession, FCMDevice.session_id == MobileSession.id)
            .join(User, FCMDevice.user_id == User.id)
            .where(User.is_active.is_(True), MobileSession.expires_at > datetime.utcnow())
        ).all()
        devices = [device for device, session, user in rows if session.password_fingerprint == password_fingerprint(user)]
        stale_tokens = []
        for offset in range(0, len(devices), 500):
            batch = devices[offset:offset + 500]
            message = messaging.MulticastMessage(
                tokens=[device.token for device in batch],
                notification=messaging.Notification(title="Novo chamado — TI", body=body[:1000]),
                data={"type": "ticket_created", "ticket_id": str(ticket.id), "pc_name": ticket.pc_name, "room_name": room},
                android=messaging.AndroidConfig(
                    priority="high", ttl=timedelta(hours=1),
                    notification=messaging.AndroidNotification(channel_id="maintenance_tickets", tag=f"ticket_{ticket.id}"),
                ),
                apns=messaging.APNSConfig(
                    headers={"apns-priority": "10", "apns-push-type": "alert"},
                    payload=messaging.APNSPayload(aps=messaging.Aps(sound="default")),
                ),
            )
            result = messaging.send_each_for_multicast(message, app=app)
            for device, response in zip(batch, result.responses):
                if isinstance(response.exception, messaging.UnregisteredError):
                    stale_tokens.append(device.token_hash)
                elif not response.success:
                    # Não registrar exceção completa: serviços externos podem incluir token.
                    logger.warning("FCM: entrega falhou (%s)", type(response.exception).__name__)
        if stale_tokens:
            db.execute(delete(FCMDevice).where(FCMDevice.token_hash.in_(stale_tokens)))
            db.commit()


def _send_safely(ticket_id: int) -> None:
    try:
        _send_ticket_notification(ticket_id)
    except Exception as exc:
        logger.warning("FCM: envio indisponível (%s)", type(exc).__name__)


def enqueue_ticket_push(ticket_id: int) -> None:
    threading.Thread(target=_send_safely, args=(ticket_id,), name="fcm-ticket", daemon=True).start()
