"""Bearer opaco, expiração e revogação compartilhadas por HTTP e WebSocket."""
import hmac
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import MobileSession, User
from ...security import digest_token, password_fingerprint

bearer = HTTPBearer(auto_error=False)


def resolve_session(db: Session, token: str) -> tuple[MobileSession, User] | None:
    if not token or len(token) > 256:
        return None
    row = db.execute(
        select(MobileSession, User).join(User, User.id == MobileSession.user_id).where(
            MobileSession.token_hash == digest_token(token),
            MobileSession.expires_at > datetime.utcnow(),
            User.is_active.is_(True),
        )
    ).first()
    if row and hmac.compare_digest(row[0].password_fingerprint, password_fingerprint(row[1])):
        return row[0], row[1]
    return None


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> MobileSession:
    resolved = resolve_session(db, credentials.credentials) if credentials else None
    if not resolved:
        raise HTTPException(401, "Sessão inválida ou expirada. Entre novamente.", headers={"WWW-Authenticate": "Bearer"})
    return resolved[0]


def current_user(session: MobileSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    return db.get(User, session.user_id)


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Acesso restrito ao administrador.")
    return user
