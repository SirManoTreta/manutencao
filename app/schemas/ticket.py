from pydantic import Field

from .common import MachineReference, ReadModel, TicketStatus, UTCDateTime, WriteModel


class TicketRead(ReadModel):
    id: int
    machine_id: int | None = None
    pc_name: str
    reported_user: str | None = None
    problem: str
    diagnostics_json: str | None = None
    status: TicketStatus
    created_at: UTCDateTime | None = None
    assigned_at: UTCDateTime | None = None
    assigned_by: str | None = None
    closed_at: UTCDateTime | None = None
    closed_by: str | None = None
    resolution_note: str | None = None
    diagnosis: str | None = None
    room_name: str | None = None
    machine: MachineReference | None = None


class TicketClose(WriteModel):
    diagnosis: str | None = Field(default=None, max_length=10000)


def ticket_read(ticket) -> TicketRead:
    result = TicketRead.model_validate(ticket)
    result.room_name = ticket.machine.room_name if ticket.machine else None
    result.diagnosis = result.resolution_note
    return result
