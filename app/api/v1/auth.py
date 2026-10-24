"""Login mobile, sessões revogáveis e vínculo de dispositivo por sessão."""
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ... import crud
from ...database import get_db
from ...models import FCMDevice, MobileSession, User
from ...schemas.auth import AuthUser, DeviceDelete, DeviceInput, LoginInput, LoginOutput
from ...security import hash_password, verify_password
from .dependencies import current_session, current_user, digest_token, password_fingerprint

router = APIRouter(tags=["Autenticação mobile"])
TOKEN_TTL_SECONDS = max(60, int(os.getenv("MOBILE_TOKEN_TTL_SECONDS", "2592000")))
# Mesmo trabalho criptográfico para usuário inexistente; não revela o cadastro pelo tempo.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
_failures: dict[str, deque] = defaultdict(deque)
_failures_lock = threading.Lock()


def _check_login_limit(key: str):
    now = time.monotonic()
    with _failures_lock:
        attempts = _failures[key]
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "Muitas tentativas. Aguarde um minuto.", headers={"Retry-After": "60"})
        # Limita memória mesmo se várias origens acessarem o servidor LAN.
        if len(_failures) > 4096:
            _failures.clear()
        _failures[key].append(now)


@router.post("/auth/login", response_model=LoginOutput)
def login(body: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "unknown"
    _check_login_limit(key)
    user = crud.get_user_by_username(db, body.username.strip())
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not user.is_active or not password_ok:
        raise HTTPException(401, "Usuário ou senha inválidos.", headers={"WWW-Authenticate": "Bearer"})
    with _failures_lock:
        _failures.pop(key, None)
    # Recolhe sessões vencidas; as FKs removem os dispositivos correspondentes.
    now = datetime.utcnow()
    db.execute(delete(MobileSession).where(MobileSession.expires_at <= now))
    raw_token = secrets.token_urlsafe(48)
    session = MobileSession(
        user_id=user.id, token_hash=digest_token(raw_token),
        password_fingerprint=password_fingerprint(user), expires_at=now + timedelta(seconds=TOKEN_TTL_SECONDS),
    )
    db.add(session)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return LoginOutput(access_token=raw_token, expires_at=session.expires_at, user=AuthUser.model_validate(user))


@router.get("/auth/me", response_model=AuthUser)
def me(user: User = Depends(current_user)):
    return user


@router.post("/auth/logout", status_code=204)
def logout(session: MobileSession = Depends(current_session), db: Session = Depends(get_db)):
    db.delete(session)
    db.commit()
    return Response(status_code=204)


@router.post("/devices", status_code=201)
def register_device(body: DeviceInput, session: MobileSession = Depends(current_session), db: Session = Depends(get_db)):
    values = dict(
        token_hash=digest_token(body.token), token=body.token, platform=body.platform,
        user_id=session.user_id, session_id=session.id, updated_at=datetime.utcnow(),
    )
    db.execute(insert(FCMDevice).values(**values).on_conflict_do_update(index_elements=["token_hash"], set_=values))
    db.commit()
    return {"registered": True}


@router.delete("/devices", status_code=204)
def unregister_device(body: DeviceDelete, session: MobileSession = Depends(current_session), db: Session = Depends(get_db)):
    db.execute(delete(FCMDevice).where(FCMDevice.token_hash == digest_token(body.token), FCMDevice.session_id == session.id))
    db.commit()
    return Response(status_code=204)
