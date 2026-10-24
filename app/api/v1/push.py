"""Registro FCM nativo: o Web Push do navegador continua em suas rotas atuais."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import fcm
from app.database import get_db
from app.models import MobileSession
from app.schemas.push import (
    PushRegister,
    PushRegistrationStatus,
    PushStatus,
    PushUnregister,
    PushUnregistrationStatus,
)
from app.services.mobile_devices import count_active_devices, deactivate_device, register_device

from .dependencies import current_session

router = APIRouter(prefix="/push", tags=["Notificações mobile"])


@router.post("/register", response_model=PushRegistrationStatus)
def push_register(
    body: PushRegister,
    session: MobileSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    register_device(
        db, session, fcm_token=body.fcm_token,
        platform=body.platform, device_name=body.device_name,
    )
    db.commit()
    return PushRegistrationStatus()


@router.post("/unregister", response_model=PushUnregistrationStatus)
def push_unregister(
    body: PushUnregister,
    session: MobileSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    deactivate_device(db, session, fcm_token=body.fcm_token)
    db.commit()
    return PushUnregistrationStatus()


@router.get("/status", response_model=PushStatus)
def push_status(
    session: MobileSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    return PushStatus(
        **fcm.configuration_status(),
        active_devices=count_active_devices(db, session),
    )
