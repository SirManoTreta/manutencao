from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import MachineHeartbeat, User
from app.schemas.common import MachineReference, as_utc
from app.schemas.online import OnlineRead
from app.services.maintenance import ONLINE_THRESHOLD_SECONDS

from .dependencies import current_user

router = APIRouter(prefix="/online", tags=["Computadores online"])


@router.get("", response_model=list[OnlineRead])
def online_list(
    threshold: int = Query(default=ONLINE_THRESHOLD_SECONDS, ge=1, le=86400),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    heartbeats = db.scalars(select(MachineHeartbeat).options(selectinload(MachineHeartbeat.machine))).all()
    now = datetime.now(timezone.utc)
    rows = []
    for heartbeat in heartbeats:
        age = max(0, int((now - as_utc(heartbeat.last_seen)).total_seconds())) if heartbeat.last_seen else 10**9
        last_user = (heartbeat.last_user or "").strip() or None
        rows.append(OnlineRead(
            pc_name=heartbeat.pc_name,
            machine_id=heartbeat.machine_id,
            room_name=heartbeat.machine.room_name if heartbeat.machine else None,
            age_seconds=age,
            is_online=age <= threshold,
            login_active=bool(last_user),
            last_user=last_user,
            last_seen=heartbeat.last_seen,
            machine=MachineReference.model_validate(heartbeat.machine) if heartbeat.machine else None,
        ))
    rows.sort(key=lambda row: (not row.is_online, row.age_seconds, row.pc_name.lower()))
    return rows
