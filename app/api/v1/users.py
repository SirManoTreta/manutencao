from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.security import hash_password

from .dependencies import admin_user

router = APIRouter(prefix="/users", tags=["Usuários"])


def _user_or_404(db: Session, user_id: int) -> User:
    user = crud.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user


@router.get("", response_model=list[UserRead])
def users_list(
    db: Session = Depends(get_db),
    actor: User = Depends(admin_user),
):
    return crud.list_users(db)


@router.post("", response_model=UserRead, status_code=201)
def users_create(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_user),
):
    if crud.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=409, detail="Usuário já existe.")
    try:
        return crud.create_user(db, payload.username, hash_password(payload.password), is_admin=payload.is_admin)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Usuário já existe.")


@router.put("/{user_id}", response_model=UserRead)
def users_update(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_user),
):
    user = _user_or_404(db, user_id)
    existing = crud.get_user_by_username(db, payload.username)
    if existing and existing.id != user.id:
        raise HTTPException(status_code=409, detail="Usuário já existe.")
    if actor.id == user.id and not payload.is_active:
        raise HTTPException(status_code=409, detail="Você não pode desativar sua própria conta.")
    password_hash = hash_password(payload.password) if payload.password else None
    try:
        return crud.update_user(
            db, user, username=payload.username, password_hash=password_hash,
            is_admin=payload.is_admin, is_active=payload.is_active,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Usuário já existe.")


@router.delete("/{user_id}", status_code=204, summary="Desativar usuário")
def users_delete(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_user),
):
    """Soft deletion preserves historical usernames and the site's account lifecycle."""
    user = _user_or_404(db, user_id)
    if actor.id == user.id:
        raise HTTPException(status_code=409, detail="Você não pode desativar sua própria conta.")
    crud.set_user_active(db, user, False)
    return Response(status_code=204)
