from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.dashboard import DashboardRead
from app.schemas.machine import machine_read
from app.schemas.ticket import ticket_read
from app.services.maintenance import build_dashboard_context

from .dependencies import current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardRead)
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    context = build_dashboard_context(db)
    return DashboardRead(
        **{
            key: value for key, value in context.items()
            if key not in {"recent_machines", "recent_tickets"}
        },
        recent_machines=[machine_read(machine) for machine in context["recent_machines"]],
        recent_tickets=[ticket_read(ticket) for ticket in context["recent_tickets"]],
    )
