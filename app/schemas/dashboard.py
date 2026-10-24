from pydantic import BaseModel

from .machine import MachineRead
from .ticket import TicketRead


class DistributionRow(BaseModel):
    label: str
    count: int
    percent: float


class DashboardRead(BaseModel):
    total_machines: int
    rooms_count: int
    open_tickets: int
    in_progress_tickets: int
    closed_tickets: int
    pending_inspections: int
    pending_checkups: int
    online_count: int
    total_heartbeats: int
    attention_rooms: int
    urgent_rooms: int
    status_rows: list[DistributionRow]
    profile_rows: list[DistributionRow]
    segment_rows: list[DistributionRow]
    recent_machines: list[MachineRead]
    recent_tickets: list[TicketRead]
