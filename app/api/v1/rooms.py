from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import Machine, User
from app.schemas.machine import MachineRead, machine_read
from app.schemas.room import RoomRead, RoomStatusUpdate
from app.services.maintenance import apply_auto_reset_checks, worst_status

from .dependencies import current_user

router = APIRouter(prefix="/rooms", tags=["Salas"])


@router.get("", response_model=list[RoomRead])
def rooms_list(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    grouped = defaultdict(list)
    for machine in crud.list_machines(db):
        grouped[machine.room_name].append(machine.room_status or "OK")
    return [
        RoomRead(room_name=name, room_status=worst_status(statuses), machine_count=len(statuses))
        for name, statuses in sorted(grouped.items(), key=lambda item: item[0].lower())
    ]


@router.patch("/status", response_model=RoomRead)
def rooms_status(
    payload: RoomStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    machines = db.scalars(select(Machine).where(Machine.room_name == payload.room_name)).all()
    if not machines:
        raise HTTPException(status_code=404, detail="Sala não encontrada.")
    now = datetime.utcnow()
    for machine in machines:
        machine.room_status = payload.room_status
        machine.updated_by = user.username
        machine.updated_at = now
    db.commit()
    return RoomRead(room_name=payload.room_name, room_status=payload.room_status, machine_count=len(machines))


@router.get("/machines", response_model=list[MachineRead])
def rooms_machines(
    room_name: str = Query(min_length=1, max_length=120),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    apply_auto_reset_checks(db)
    machines = db.scalars(select(Machine).where(Machine.room_name == room_name).order_by(Machine.machine_name)).all()
    return [machine_read(machine) for machine in machines]
