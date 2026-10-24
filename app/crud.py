from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, update
from .models import Machine, MachinePeripheral, User, MachineAudit, Ticket, MachineHeartbeat
from .constants import peripherals_for_profile
from .realtime import broadcast_from_thread


def take_ticket(db: Session, ticket_id: int, actor_username: str) -> bool:
    """Uma única atualização condicional decide quem assume, também entre processos."""
    result = db.execute(
        update(Ticket).where(Ticket.id == ticket_id, Ticket.status == "OPEN").values(
            status="IN_PROGRESS", assigned_at=datetime.utcnow(), assigned_by=actor_username,
        )
    )
    db.commit()
    if result.rowcount:
        broadcast_from_thread({"type": "ticket_taken", "ticket_id": ticket_id, "assigned_by": actor_username})
    return bool(result.rowcount)


def close_ticket(db: Session, ticket_id: int, actor_username: str, diagnosis: str | None = None) -> bool:
    values = {"status": "CLOSED", "closed_at": datetime.utcnow(), "closed_by": actor_username}
    if diagnosis is not None:
        values["resolution_note"] = diagnosis.strip() or None
    result = db.execute(
        update(Ticket).where(Ticket.id == ticket_id, Ticket.status == "IN_PROGRESS").values(**values)
    )
    db.commit()
    if result.rowcount:
        broadcast_from_thread({"type": "ticket_closed", "ticket_id": ticket_id})
    return bool(result.rowcount)


# ----------------- Machines -----------------

def list_machines(
    db: Session,
    *,
    q: str | None = None,
    profile: str | None = None,
    room_status: str | None = None,
    inspected: bool | None = None,
    checkup_done: bool | None = None,
):
    stmt = select(Machine).order_by(Machine.room_name, Machine.machine_name)

    if profile:
        stmt = stmt.where(Machine.profile == profile)

    if room_status:
        stmt = stmt.where(Machine.room_status == room_status)

    if inspected is not None:
        stmt = stmt.where(Machine.inspected == inspected)

    if checkup_done is not None:
        stmt = stmt.where(Machine.checkup_done == checkup_done)

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (Machine.machine_name.ilike(like))
            | (Machine.room_name.ilike(like))
            | (Machine.ip.ilike(like))
            | (Machine.username.ilike(like))
            | (Machine.hoptodesk_id.ilike(like))
            | (Machine.mac_address.ilike(like))
        )
    return list(db.execute(stmt).scalars().all())


def get_machine(db: Session, machine_id: int) -> Machine | None:
    return db.get(Machine, machine_id)


def upsert_peripherals_for_machine(
    machine: Machine,
    peripheral_state: dict[str, dict[str, object]],
):
    existing = {p.peripheral_code: p for p in machine.peripherals}
    relevant = peripherals_for_profile(machine.profile)
    relevant_codes = {d.code for d in relevant}
    relevant_has_qty = {d.code: d.has_quantity for d in relevant}

    for code in relevant_codes:
        state = peripheral_state.get(code, {})
        present = bool(state.get("present", False))
        tested = bool(state.get("tested_working", False))
        qty = int(state.get("quantity", 0) or 0)

        if relevant_has_qty.get(code, False):
            if not present:
                qty = 0
            if qty <= 0:
                present = False
                tested = False
            else:
                present = True
        else:
            qty = 0
            if not present:
                tested = False

        if code in existing:
            existing[code].present = present
            existing[code].tested_working = tested
            existing[code].quantity = qty
        else:
            machine.peripherals.append(
                MachinePeripheral(
                    peripheral_code=code,
                    present=present,
                    tested_working=tested,
                    quantity=qty,
                )
            )

    for code, obj in list(existing.items()):
        if code not in relevant_codes:
            machine.peripherals.remove(obj)


def create_machine(
    db: Session,
    data: dict,
    peripheral_state: dict[str, dict[str, object]],
    actor_username: str,
):
    now = datetime.utcnow()
    machine = Machine(**data)
    machine.created_by = actor_username
    machine.updated_by = actor_username
    machine.created_at = now
    machine.updated_at = now

    db.add(machine)
    db.flush()

    upsert_peripherals_for_machine(machine, peripheral_state)

    db.add(MachineAudit(machine_id=machine.id, action="CREATE", username=actor_username))
    db.commit()
    db.refresh(machine)
    return machine


def update_machine(
    db: Session,
    machine: Machine,
    data: dict,
    peripheral_state: dict[str, dict[str, object]],
    actor_username: str,
):
    for k, v in data.items():
        setattr(machine, k, v)

    machine.updated_by = actor_username
    machine.updated_at = datetime.utcnow()

    upsert_peripherals_for_machine(machine, peripheral_state)

    db.add(MachineAudit(machine_id=machine.id, action="UPDATE", username=actor_username))
    db.commit()
    db.refresh(machine)
    return machine


def delete_machine(db: Session, machine: Machine, actor_username: str):
    """Exclui a máquina e TODOS os vestígios dela no sistema.

    Tickets e heartbeats são ligados tanto por machine_id quanto por pc_name
    (o cliente identifica-se pelo hostname). Removemos pelos dois caminhos,
    senão a página de chamados continua mostrando o PC como "não cadastrado".
    """
    pc_name = (machine.machine_name or "").strip()

    ticket_filter = Ticket.machine_id == machine.id
    hb_filter = MachineHeartbeat.machine_id == machine.id
    if pc_name:
        ticket_filter = or_(ticket_filter, Ticket.pc_name == pc_name)
        hb_filter = or_(hb_filter, MachineHeartbeat.pc_name == pc_name)

    db.query(Ticket).filter(ticket_filter).delete(synchronize_session=False)
    db.query(MachineHeartbeat).filter(hb_filter).delete(synchronize_session=False)

    note = f"Removidos também tickets/heartbeats de '{pc_name}'" if pc_name else None
    db.add(MachineAudit(machine_id=machine.id, action="DELETE", username=actor_username, note=note))
    db.delete(machine)
    db.commit()


# ----------------- Users -----------------

def count_users(db: Session) -> int:
    return db.execute(select(func.count()).select_from(User)).scalar_one()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalars().first()


def list_users(db: Session):
    stmt = select(User).order_by(User.is_admin.desc(), User.username.asc())
    return list(db.execute(stmt).scalars().all())


def create_user(db: Session, username: str, password_hash: str, is_admin: bool):
    user = User(username=username, password_hash=password_hash, is_admin=is_admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_user_active(db: Session, user: User, is_active: bool):
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user: User,
    *,
    username: str,
    password_hash: str | None,
    is_admin: bool,
    is_active: bool,
):
    """Atualiza um usuário existente.

    Observação: validações (ex.: usuário duplicado) ficam na camada de rota.
    """
    user.username = username
    if password_hash:
        user.password_hash = password_hash

    user.is_admin = is_admin
    user.is_active = is_active

    db.commit()
    db.refresh(user)
    return user
