from .common import MachineReference, ReadModel, UTCDateTime


class OnlineRead(ReadModel):
    pc_name: str
    machine_id: int | None = None
    room_name: str | None = None
    age_seconds: int
    is_online: bool
    login_active: bool
    last_user: str | None = None
    last_seen: UTCDateTime | None = None
    machine: MachineReference | None = None
