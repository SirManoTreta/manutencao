from pydantic import Field

from .common import ReadModel, RoomStatus, WriteModel


class RoomRead(ReadModel):
    room_name: str
    room_status: str
    machine_count: int


class RoomStatusUpdate(WriteModel):
    room_name: str = Field(min_length=1, max_length=120)
    room_status: RoomStatus
