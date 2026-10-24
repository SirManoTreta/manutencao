from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import crud
from app.constants import peripherals_for_profile
from app.database import get_db
from app.models import Machine, User
from app.schemas.common import Profile, RoomStatus, Segment
from app.schemas.machine import MachineCreate, MachineRead, MachineUpdate, machine_read
from app.services.maintenance import apply_auto_reset_checks, derive_segment, normalize_mac

from .dependencies import current_user

router = APIRouter(prefix="/machines", tags=["Máquinas"])


def _machine_or_404(db: Session, machine_id: int) -> Machine:
    machine = crud.get_machine(db, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Máquina não encontrada.")
    return machine


def _peripheral_state(payload, profile: str, machine: Machine | None = None):
    if machine is not None and "peripherals" not in payload.model_fields_set:
        return {
            item.peripheral_code: {
                "present": item.present,
                "tested_working": item.tested_working,
                "quantity": item.quantity,
            }
            for item in machine.peripherals
        }

    definitions = {item.code: item for item in peripherals_for_profile(profile)}
    state = {}
    for item in payload.peripherals:
        definition = definitions.get(item.peripheral_code)
        if definition is None:
            raise HTTPException(status_code=422, detail=f"Periférico inválido para perfil {profile}: {item.peripheral_code}.")
        values = item.model_dump(exclude={"peripheral_code"})
        if definition.has_quantity and item.present and item.quantity <= 0:
            # Same CABO_RCA default used by the existing HTML form.
            values["quantity"] = 2
        state[item.peripheral_code] = values
    return state


def _machine_data(payload, profile: str, *, partial: bool):
    data = payload.model_dump(exclude={"peripherals"}, exclude_unset=partial)
    if "mac_address" in data:
        data["mac_address"] = normalize_mac(data["mac_address"])
    if profile != "A":
        data["projector_lamp_hours"] = None
    for name, value in list(data.items()):
        if isinstance(value, str) and not value:
            data[name] = None
    return data


@router.get("", response_model=list[MachineRead])
def machines_list(
    q: str | None = Query(default=None, max_length=200),
    profile: Profile | None = None,
    segment: Segment | None = None,
    room_status: RoomStatus | None = None,
    inspected: bool | None = None,
    checkup_done: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    apply_auto_reset_checks(db)
    machines = crud.list_machines(
        db, q=q, profile=profile, room_status=room_status,
        inspected=inspected, checkup_done=checkup_done,
    )
    if segment:
        machines = [
            machine for machine in machines
            if derive_segment(machine.room_name or machine.machine_name, machine.profile) == segment
        ]
    return [machine_read(machine) for machine in machines]


@router.get("/{machine_id}", response_model=MachineRead)
def machines_detail(
    machine_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    apply_auto_reset_checks(db)
    return machine_read(_machine_or_404(db, machine_id))


@router.post("", response_model=MachineRead, status_code=201)
def machines_create(
    payload: MachineCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    state = _peripheral_state(payload, payload.profile)
    machine = crud.create_machine(
        db, _machine_data(payload, payload.profile, partial=False), state,
        actor_username=user.username,
    )
    return machine_read(machine)


@router.put("/{machine_id}", response_model=MachineRead)
def machines_update(
    machine_id: int,
    payload: MachineUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    machine = _machine_or_404(db, machine_id)
    profile = payload.profile if "profile" in payload.model_fields_set else machine.profile
    state = _peripheral_state(payload, profile, machine)
    machine = crud.update_machine(
        db, machine, _machine_data(payload, profile, partial=True), state,
        actor_username=user.username,
    )
    return machine_read(machine)


@router.delete("/{machine_id}", status_code=204)
def machines_delete(
    machine_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    crud.delete_machine(db, _machine_or_404(db, machine_id), actor_username=user.username)
    return Response(status_code=204)
