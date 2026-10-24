from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    machine_name: Mapped[str] = mapped_column(String(120), nullable=False)
    room_name: Mapped[str] = mapped_column(String(120), nullable=False)
    room_status: Mapped[str] = mapped_column(String(16), nullable=False, default="OK")  # OK/ATTENTION/URGENT

    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(String(120), nullable=False)

    profile: Mapped[str] = mapped_column(String(1), nullable=False)  # A, B ou C

    inspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_inspection_date: Mapped[object] = mapped_column(Date, nullable=True)

    checkup_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_checkup_date: Mapped[object] = mapped_column(Date, nullable=True)

    maintenance_description: Mapped[str] = mapped_column(Text, nullable=True)

    # ===== Campos opcionais (Hardware/Software) =====
    os_name: Mapped[str] = mapped_column(String(120), nullable=True)
    gpu_type: Mapped[str] = mapped_column(String(32), nullable=True)  # integrada/offboard
    ram_gb: Mapped[int] = mapped_column(Integer, nullable=True)
    ram_modules: Mapped[int] = mapped_column(Integer, nullable=True)
    cpu_model: Mapped[str] = mapped_column(String(120), nullable=True)
    storage_type: Mapped[str] = mapped_column(String(16), nullable=True)  # HDD/SSD/NVME
    storage_gb: Mapped[int] = mapped_column(Integer, nullable=True)

    office_installed: Mapped[bool] = mapped_column(Boolean, nullable=True)
    office_version: Mapped[str] = mapped_column(String(60), nullable=True)

    kaspersky_installed: Mapped[bool] = mapped_column(Boolean, nullable=True)
    kaspersky_updated: Mapped[bool] = mapped_column(Boolean, nullable=True)

    usb_ports_qty: Mapped[int] = mapped_column(Integer, nullable=True)
    usb_ports_working: Mapped[bool] = mapped_column(Boolean, nullable=True)

    adapters: Mapped[str] = mapped_column(Text, nullable=True)

    # ===== Acesso remoto / rede (opcional) =====
    hoptodesk_id: Mapped[str] = mapped_column(String(64), nullable=True)
    hoptodesk_password: Mapped[str] = mapped_column(String(128), nullable=True)
    mac_address: Mapped[str] = mapped_column(String(32), nullable=True)

    # ===== Projetor (opcional) =====
    projector_lamp_hours: Mapped[int] = mapped_column(Integer, nullable=True)

    # ===== Auditoria automática (quem fez / quando) =====
    created_by: Mapped[str] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    updated_by: Mapped[str] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    peripherals: Mapped[list["MachinePeripheral"]] = relationship(
        back_populates="machine",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MachinePeripheral(Base):
    __tablename__ = "machine_peripherals"
    __table_args__ = (
        UniqueConstraint("machine_id", "peripheral_code", name="uq_machine_peripheral"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    peripheral_code: Mapped[str] = mapped_column(String(64), nullable=False)
    present: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tested_working: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    machine: Mapped["Machine"] = relationship(back_populates="peripherals")


class MachineAudit(Base):
    __tablename__ = "machine_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(16), nullable=False)  # CREATE / UPDATE / DELETE
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=True)


# ================= Chamados (Professor.py) =================


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    machine_id: Mapped[int | None] = mapped_column(
        ForeignKey("machines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    pc_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reported_user: Mapped[str | None] = mapped_column(String(120), nullable=True)

    problem: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostics_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="OPEN"
    )  # OPEN/IN_PROGRESS/CLOSED

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Em SQLAlchemy, o relacionamento pode apontar para None.
    # Usamos Optional["Machine"] (e não "Machine" | None), porque
    # a anotação "Machine" está em string e o operador | não funciona em string.
    machine: Mapped[Optional["Machine"]] = relationship(lazy="selectin")


class MachineHeartbeat(Base):
    __tablename__ = "machine_heartbeats"
    __table_args__ = (
        UniqueConstraint("pc_name", name="uq_heartbeat_pc_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    pc_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    machine_id: Mapped[int | None] = mapped_column(
        ForeignKey("machines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_user: Mapped[str | None] = mapped_column(String(120), nullable=True)
    diagnostics_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    machine: Mapped[Optional["Machine"]] = relationship(lazy="selectin")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    subscription_json: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MobileSession(Base):
    """Sessão mobile revogável; o Bearer original nunca é persistido."""

    __tablename__ = "mobile_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class FCMDevice(Base):
    __tablename__ = "fcm_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("mobile_sessions.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
