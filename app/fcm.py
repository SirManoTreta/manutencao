"""FCM independente do Web Push; falhas externas não interrompem chamados TCP."""
from __future__ import annotations

import logging
import json
import os
import threading
from datetime import datetime, timedelta

from sqlalchemy import select, update

from .database import SessionLocal
from .models import FCMDevice, MobileSession, Ticket, User
from .security import password_fingerprint

# Herda nível/handlers do servidor Uvicorn: contagens INFO ficam visíveis no
# comando normal do projeto, sem configurar logging global de bibliotecas.
logger = logging.getLogger("uvicorn.error.fcm")
_firebase_lock = threading.Lock()


def _credential_path() -> str | None:
    return os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("FIREBASE_CREDENTIALS")


def configuration_status() -> dict[str, bool]:
    """Só configuração declarada; nunca presume que a credencial é válida."""
    credential_path = _credential_path()
    enabled = os.getenv("FCM_ENABLED", "true" if credential_path else "false").lower() in ("1", "true", "yes")
    return {"enabled": enabled, "credentials_configured": bool(credential_path)}


def _get_firebase_app():
    credential_path = _credential_path()
    if not configuration_status()["enabled"]:
        logger.info("FCM desativado; envio nativo não solicitado.")
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
            app = firebase_admin.initialize_app(credential, options=options, name="maintenance-mobile")
            logger.info("Firebase Admin inicializado por configuração externa.")
            return app


def _truncate_json_text(value: str, max_bytes: int) -> str:
    """Orçamento inclui escapes JSON: aspas, barras e controles também ocupam bytes.

    ensure_ascii=True é conservador para UTF-8 e para APNs. A busca binária
    evita repetir cortes de um caractere em textos longos enviados pelo TCP.
    """
    lower, upper = 0, min(len(value), max_bytes)
    while lower < upper:
        middle = (lower + upper + 1) // 2
        if len(json.dumps(value[:middle], ensure_ascii=True)) <= max_bytes:
            lower = middle
        else:
            upper = middle - 1
    return value[:lower]


def _is_invalid_token(error, messaging) -> bool:
    if isinstance(error, messaging.UnregisteredError):
        return True
    # INVALID_ARGUMENT genérico também pode indicar payload inválido. Somente
    # rejeição FCM estruturada, com nosso payload limitado, autoriza desativar.
    if str(getattr(error, "code", "")).upper().replace("-", "_") != "INVALID_ARGUMENT":
        return False
    response = getattr(error, "http_response", None)
    try:
        details = response.json()["error"]["details"]
        if not isinstance(details, list) or any(not isinstance(item, dict) for item in details):
            return False
        if any(item.get("@type") == "type.googleapis.com/google.rpc.BadRequest" for item in details):
            return False
        return any(
            item.get("@type") == "type.googleapis.com/google.firebase.fcm.v1.FcmError"
            and item.get("errorCode") == "INVALID_ARGUMENT"
            for item in details
        )
    except (AttributeError, TypeError, ValueError, KeyError):
        return False


def _send_ticket_notification(ticket_id: int) -> None:
    app = _get_firebase_app()
    if app is None:
        return
    from firebase_admin import messaging

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            return
        room = _truncate_json_text((ticket.machine.room_name if ticket.machine else None) or "Não cadastrada", 200)
        pc_name = _truncate_json_text(ticket.pc_name, 200)
        body = _truncate_json_text(f"Sala: {room}\nPC: {pc_name}\nProblema: {ticket.problem}", 2000)
        # Só usuários ativos com sessão válida continuam recebendo chamados.
        rows = db.execute(
            select(FCMDevice, MobileSession, User)
            .join(MobileSession, FCMDevice.session_id == MobileSession.id)
            .join(User, FCMDevice.user_id == User.id)
            .where(
                FCMDevice.is_active.is_(True), User.is_active.is_(True),
                MobileSession.expires_at > datetime.utcnow(),
                MobileSession.user_id == FCMDevice.user_id,
            )
        ).all()
        devices = [device for device, session, user in rows if session.password_fingerprint == password_fingerprint(user)]
        for offset in range(0, len(devices), 500):
            batch = devices[offset:offset + 500]
            message = messaging.MulticastMessage(
                tokens=[device.token for device in batch],
                notification=messaging.Notification(title="Novo chamado — TI", body=body),
                data={"type": "new_ticket", "ticket_id": str(ticket.id), "pc_name": pc_name, "room_name": room},
                android=messaging.AndroidConfig(
                    priority="high", ttl=timedelta(hours=1),
                    notification=messaging.AndroidNotification(channel_id="maintenance_tickets", tag=f"ticket_{ticket.id}"),
                ),
                apns=messaging.APNSConfig(
                    headers={"apns-priority": "10", "apns-push-type": "alert"},
                    payload=messaging.APNSPayload(aps=messaging.Aps(sound="default")),
                ),
            )
            try:
                result = messaging.send_each_for_multicast(message, app=app)
            except Exception as exc:
                logger.warning("FCM chamado %s: lote indisponível (%s); dispositivos mantidos ativos.", ticket_id, type(exc).__name__)
                continue
            disabled = delivered = 0
            for device, response in zip(batch, result.responses):
                if response.success:
                    delivered += 1
                elif _is_invalid_token(response.exception, messaging):
                    # Uma resposta antiga não deve invalidar registro renovado
                    # ou transferido para outra sessão durante a chamada externa.
                    changed = db.execute(
                        update(FCMDevice).where(
                            FCMDevice.id == device.id,
                            FCMDevice.session_id == device.session_id,
                            FCMDevice.updated_at == device.updated_at,
                            FCMDevice.is_active.is_(True),
                        ).values(is_active=False, updated_at=datetime.utcnow())
                        .execution_options(synchronize_session=False)
                    )
                    disabled += changed.rowcount
                elif not response.success:
                    # Não registrar exceção completa: serviços externos podem incluir token.
                    logger.warning("FCM chamado %s: entrega falhou (%s).", ticket_id, type(response.exception).__name__)
            if disabled:
                db.commit()
            logger.info("FCM chamado %s: enviados=%s, dispositivos=%s, desativados=%s.", ticket_id, delivered, len(batch), disabled)


def _send_safely(ticket_id: int) -> None:
    try:
        _send_ticket_notification(ticket_id)
    except Exception as exc:
        logger.warning("FCM chamado %s: envio indisponível (%s). Verifique configuração externa e acesso ao Firebase.", ticket_id, type(exc).__name__)


def enqueue_ticket_push(ticket_id: int) -> None:
    try:
        threading.Thread(target=_send_safely, args=(ticket_id,), name="fcm-ticket", daemon=True).start()
    except Exception as exc:
        logger.warning("FCM chamado %s: fila indisponível (%s); chamado já persistido.", ticket_id, type(exc).__name__)
