from datetime import date

from pydantic import Field, field_validator

from app.constants import peripherals_for_profile
from app.services.maintenance import derive_segment

from .common import Profile, ReadModel, RoomStatus, UTCDateTime, WriteModel


class PeripheralWrite(WriteModel):
    peripheral_code: str = Field(min_length=1, max_length=64)
    present: bool = False
    tested_working: bool = False
    quantity: int = Field(default=0, ge=0, le=100000)


class PeripheralRead(ReadModel):
    peripheral_code: str
    label: str
    has_quantity: bool
    present: bool
    tested_working: bool
    quantity: int


class MachineOptionalFields(WriteModel):
    inspected: bool = False
    last_inspection_date: date | None = None
    checkup_done: bool = False
    last_checkup_date: date | None = None
    maintenance_description: str | None = Field(default=None, max_length=20000)
    os_name: str | None = Field(default=None, max_length=120)
    gpu_type: str | None = Field(default=None, max_length=32)
    ram_gb: int | None = Field(default=None, ge=0, le=1000000)
    ram_modules: int | None = Field(default=None, ge=0, le=10000)
    cpu_model: str | None = Field(default=None, max_length=120)
    storage_type: str | None = Field(default=None, max_length=16)
    storage_gb: int | None = Field(default=None, ge=0, le=1000000000)
    office_installed: bool | None = None
    office_version: str | None = Field(default=None, max_length=60)
    kaspersky_installed: bool | None = None
    kaspersky_updated: bool | None = None
    usb_ports_qty: int | None = Field(default=None, ge=0, le=10000)
    usb_ports_working: bool | None = None
    adapters: str | None = Field(default=None, max_length=20000)
    hoptodesk_id: str | None = Field(default=None, max_length=64)
    mac_address: str | None = Field(default=None, max_length=32)
    projector_lamp_hours: int | None = Field(default=None, ge=0, le=100000000)
    peripherals: list[PeripheralWrite] = Field(default_factory=list, max_length=100)

    @field_validator("peripherals")
    @classmethod
    def unique_peripherals(cls, value):
        codes = [item.peripheral_code for item in value]
        if len(codes) != len(set(codes)):
            raise ValueError("Periféricos duplicados.")
        return value


class MachineCreate(MachineOptionalFields):
    machine_name: str = Field(min_length=1, max_length=120)
    room_name: str = Field(min_length=1, max_length=120)
    room_status: RoomStatus = "OK"
    ip: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=120)
    profile: Profile


class MachineUpdate(MachineOptionalFields):
    """Omitted fields remain unchanged, including peripherals and remote password."""

    machine_name: str | None = Field(default=None, min_length=1, max_length=120)
    room_name: str | None = Field(default=None, min_length=1, max_length=120)
    room_status: RoomStatus | None = None
    ip: str | None = Field(default=None, min_length=1, max_length=64)
    username: str | None = Field(default=None, min_length=1, max_length=120)
    profile: Profile | None = None

    @field_validator("machine_name", "room_name", "room_status", "ip", "username", "profile")
    @classmethod
    def required_when_present(cls, value):
        if value is None:
            raise ValueError("Campo obrigatório não pode ser nulo.")
        return value


class MachineRead(ReadModel):
    """Allowlist deliberately excludes hoptodesk_password, including nested output."""

    id: int
    machine_name: str
    room_name: str
    room_status: str
    ip: str
    username: str
    profile: str
    segment: str = "OUTRO"
    inspected: bool
    last_inspection_date: date | None = None
    checkup_done: bool
    last_checkup_date: date | None = None
    maintenance_description: str | None = None
    os_name: str | None = None
    gpu_type: str | None = None
    ram_gb: int | None = None
    ram_modules: int | None = None
    cpu_model: str | None = None
    storage_type: str | None = None
    storage_gb: int | None = None
    office_installed: bool | None = None
    office_version: str | None = None
    kaspersky_installed: bool | None = None
    kaspersky_updated: bool | None = None
    usb_ports_qty: int | None = None
    usb_ports_working: bool | None = None
    adapters: str | None = None
    hoptodesk_id: str | None = None
    mac_address: str | None = None
    projector_lamp_hours: int | None = None
    created_by: str | None = None
    created_at: UTCDateTime | None = None
    updated_by: str | None = None
    updated_at: UTCDateTime | None = None
    peripherals: list[PeripheralRead] = Field(default_factory=list)


def machine_read(machine) -> MachineRead:
    # Peripheral definitions come from the same profile catalog used by the site.
    stored = {item.peripheral_code: item for item in machine.peripherals}
    peripheral_rows = []
    for definition in peripherals_for_profile(machine.profile):
        state = stored.get(definition.code)
        peripheral_rows.append(PeripheralRead(
            peripheral_code=definition.code,
            label=definition.label,
            has_quantity=definition.has_quantity,
            present=bool(state and state.present),
            tested_working=bool(state and state.tested_working),
            quantity=(state.quantity or 0) if state else 0,
        ))
    fields = {
        name: getattr(machine, name)
        for name in MachineRead.model_fields
        if name not in {"segment", "peripherals"}
    }
    return MachineRead(
        **fields,
        segment=derive_segment(machine.room_name or machine.machine_name, machine.profile),
        peripherals=peripheral_rows,
    )
