"""Persistência de dispositivos compartilhada pelas APIs FCM nova e legada.

As rotas autenticadas fornecem a sessão; nunca aceitamos identidade do payload.
O chamador controla o commit, mantendo cada operação em uma transação curta.
"""
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models import FCMDevice, MobileSession
from app.security import digest_token


def register_device(
    db: Session,
    session: MobileSession,
    *,
    fcm_token: str,
    platform: str,
    device_name: str | None = None,
) -> None:
    """Um único upsert reativa e reassocia o token, sem duplicar dispositivo."""
    now = datetime.utcnow()
    name = (device_name or "").strip() or None
    values = {
        "token_hash": digest_token(fcm_token),
        "token": fcm_token,
        "platform": platform,
        "device_name": name,
        "user_id": session.user_id,
        "session_id": session.id,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    statement = insert(FCMDevice).values(**values)
    updated = {key: value for key, value in values.items() if key != "created_at"}
    # Clientes antigos não enviam nome; preservar metadados já cadastrados.
    updated["device_name"] = func.coalesce(statement.excluded.device_name, FCMDevice.device_name)
    db.execute(statement.on_conflict_do_update(index_elements=["token_hash"], set_=updated))


def deactivate_device(db: Session, session: MobileSession, *, fcm_token: str) -> None:
    """Desativação idempotente do token pertencente ao usuário autenticado."""
    db.execute(
        update(FCMDevice)
        .where(
            FCMDevice.token_hash == digest_token(fcm_token),
            FCMDevice.user_id == session.user_id,
            FCMDevice.is_active.is_(True),
        )
        .values(is_active=False, updated_at=datetime.utcnow())
    )


def count_active_devices(db: Session, session: MobileSession) -> int:
    """A mesma elegibilidade de sessão usada no envio, sem revelar tokens."""
    return db.scalar(
        select(func.count())
        .select_from(FCMDevice)
        .join(MobileSession, MobileSession.id == FCMDevice.session_id)
        .where(
            FCMDevice.user_id == session.user_id,
            FCMDevice.is_active.is_(True),
            MobileSession.user_id == session.user_id,
            MobileSession.expires_at > datetime.utcnow(),
            MobileSession.password_fingerprint == session.password_fingerprint,
        )
    ) or 0
