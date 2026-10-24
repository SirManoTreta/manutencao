from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict


def as_utc(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return value


UTCDateTime = Annotated[datetime, BeforeValidator(as_utc)]
Profile = Literal["A", "B", "C"]
RoomStatus = Literal["OK", "ATTENTION", "URGENT"]
Segment = Literal["INFANTIL", "FUND1", "FUND2", "EM", "ADMIN", "OUTRO"]
TicketStatus = Literal["OPEN", "IN_PROGRESS", "CLOSED"]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MachineReference(ReadModel):
    id: int
    machine_name: str
    room_name: str
