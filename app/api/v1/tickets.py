from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import crud
from app.database import get_db
from app.models import Ticket, User
from app.schemas.ticket import TicketClose, TicketRead, ticket_read

from .dependencies import current_user

router = APIRouter(prefix="/tickets", tags=["Chamados"])


def _ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    return ticket


@router.get("", response_model=list[TicketRead])
def tickets_list(
    status: Literal["OPEN", "IN_PROGRESS", "CLOSED", "ALL"] = "OPEN",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    statement = select(Ticket).options(selectinload(Ticket.machine)).order_by(Ticket.created_at.desc(), Ticket.id.desc())
    if status != "ALL":
        statement = statement.where(Ticket.status == status)
    return [ticket_read(ticket) for ticket in db.scalars(statement).all()]


@router.get("/{ticket_id}", response_model=TicketRead)
def tickets_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return ticket_read(_ticket_or_404(db, ticket_id))


@router.post("/{ticket_id}/take", response_model=TicketRead)
def tickets_take(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ticket = _ticket_or_404(db, ticket_id)
    # The shared conditional UPDATE is also used by HTML, including its broadcast.
    if not crud.take_ticket(db, ticket_id, user.username):
        raise HTTPException(status_code=409, detail="Chamado já assumido ou finalizado.")
    db.refresh(ticket)
    return ticket_read(ticket)


@router.post("/{ticket_id}/close", response_model=TicketRead)
def tickets_close(
    ticket_id: int,
    payload: TicketClose | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ticket = _ticket_or_404(db, ticket_id)
    diagnosis = payload.diagnosis if payload else None
    if not crud.close_ticket(db, ticket_id, user.username, diagnosis=diagnosis):
        raise HTTPException(status_code=409, detail="Somente chamados em atendimento podem ser finalizados.")
    db.refresh(ticket)
    return ticket_read(ticket)
