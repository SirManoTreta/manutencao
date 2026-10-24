import os
import io
import secrets
import logging
import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from starlette.middleware.sessions import SessionMiddleware
from datetime import date
from fastapi import FastAPI, Request, Depends, Form, WebSocket
from starlette.websockets import WebSocketDisconnect
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .models import Machine, User, Ticket, MachineHeartbeat, PushSubscription
from .reporting import build_xlsm_report
from collections import defaultdict

from .database import Base, engine, get_db, DATA_DIR
from . import crud
from .constants import PROFILE_A, PROFILE_B, PROFILE_C, peripherals_for_profile

# Servidor de chamados (Professor.py) integrado
from .chamados_socket import start_chamados_server, stop_chamados_server
from .realtime import set_main_loop, manager, broadcast_from_thread
from .push import ensure_vapid_keys, get_public_key, upsert_subscription, delete_subscription
from .fcm import configuration_status

from .security import hash_password, verify_password
from .services.maintenance import (
    derive_segment, _today_br, apply_auto_reset_checks, worst_status,
    normalize_mac as _normalize_mac, build_dashboard_context as _build_dashboard_context,
    BR_TZ, AUTO_RESET_DAYS_BY_STATUS, ONLINE_THRESHOLD_SECONDS,
)

Base.metadata.create_all(bind=engine)


# Migração simples (SQLite) para colunas novas
def _migrate_sqlite():
    with engine.connect() as conn:
        # machines
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(machines)")).fetchall()]
                # status da sala
        if "room_status" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN room_status VARCHAR(16) NOT NULL DEFAULT 'OK'"))
        if "checkup_done" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN checkup_done INTEGER NOT NULL DEFAULT 0"))
        if "last_checkup_date" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN last_checkup_date DATE"))
                # ===== novas colunas opcionais em machines =====
        if "os_name" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN os_name VARCHAR(120)"))
        if "gpu_type" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN gpu_type VARCHAR(32)"))
        if "ram_gb" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN ram_gb INTEGER"))
        if "ram_modules" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN ram_modules INTEGER"))
        if "cpu_model" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN cpu_model VARCHAR(120)"))
        if "storage_type" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN storage_type VARCHAR(16)"))
        if "storage_gb" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN storage_gb INTEGER"))
        if "office_installed" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN office_installed INTEGER"))
        if "office_version" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN office_version VARCHAR(60)"))
        if "kaspersky_installed" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN kaspersky_installed INTEGER"))
        if "kaspersky_updated" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN kaspersky_updated INTEGER"))
        if "usb_ports_qty" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN usb_ports_qty INTEGER"))
        if "usb_ports_working" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN usb_ports_working INTEGER"))
        if "adapters" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN adapters TEXT"))

        # Acesso remoto / rede
        if "hoptodesk_id" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN hoptodesk_id VARCHAR(64)"))
        if "hoptodesk_password" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN hoptodesk_password VARCHAR(128)"))
        if "mac_address" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN mac_address VARCHAR(32)"))

        # Projetor
        if "projector_lamp_hours" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN projector_lamp_hours INTEGER"))
        if "created_by" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN created_by VARCHAR(80)"))
        if "created_at" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN created_at DATETIME"))
        if "updated_by" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN updated_by VARCHAR(80)"))
        if "updated_at" not in cols:
            conn.execute(text("ALTER TABLE machines ADD COLUMN updated_at DATETIME"))


        # machine_peripherals
        cols2 = [r[1] for r in conn.execute(text("PRAGMA table_info(machine_peripherals)")).fetchall()]
        if "quantity" not in cols2:
            conn.execute(text("ALTER TABLE machine_peripherals ADD COLUMN quantity INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text(
                "UPDATE machine_peripherals SET quantity = 2 "
                "WHERE peripheral_code = 'CABO_RCA' AND present = 1 AND quantity = 0"
            ))

        # tickets
        ticket_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tickets)")).fetchall()]
        if "assigned_at" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN assigned_at DATETIME"))
        if "assigned_by" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN assigned_by VARCHAR(80)"))
        if "resolution_note" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN resolution_note TEXT"))

        # Instalações mobile anteriores já têm tokens; acrescentar só metadados.
        device_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(fcm_devices)")).fetchall()]
        if "device_name" not in device_cols:
            conn.execute(text("ALTER TABLE fcm_devices ADD COLUMN device_name VARCHAR(120)"))
        if "is_active" not in device_cols:
            conn.execute(text("ALTER TABLE fcm_devices ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "created_at" not in device_cols:
            conn.execute(text("ALTER TABLE fcm_devices ADD COLUMN created_at DATETIME"))
            conn.execute(text("UPDATE fcm_devices SET created_at = COALESCE(updated_at, CURRENT_TIMESTAMP)"))
        conn.commit()

_migrate_sqlite()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# ===== Timezone padrão do sistema (Brasília / UTC-3) =====
#
# A aplicação salva timestamps em UTC (datetime.utcnow). Para exibição no site,
# convertemos para America/Sao_Paulo. Isso evita confusão quando o servidor
# está em UTC mas os usuários esperam horário local.

def _as_utc(dt: datetime) -> datetime:
    """Garante datetime com tzinfo UTC.

    O banco pode armazenar datetimes 'naive' (sem tz). Tratamos como UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_br_tz(dt: datetime) -> datetime:
    if not dt:
        return None
    return _as_utc(dt).astimezone(BR_TZ)


def fmt_dt_br(dt: datetime, fmt: str = "%d/%m/%Y %H:%M") -> str:
    if not dt:
        return "-"
    try:
        return to_br_tz(dt).strftime(fmt)
    except Exception:
        return "-"


def fmt_time_br(dt: datetime) -> str:
    return fmt_dt_br(dt, "%d/%m %H:%M")


def fmt_date_br(d: date | None) -> str:
    if not d:
        return "-"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return "-"


templates.env.filters["dt_br"] = fmt_dt_br
templates.env.filters["datetime_br"] = fmt_dt_br
templates.env.filters["time_br"] = fmt_time_br
templates.env.filters["date_br"] = fmt_date_br


STATIC_DIR = os.path.join(APP_DIR, "static")

os.makedirs(DATA_DIR, exist_ok=True)

SECRET_FILE = os.path.join(DATA_DIR, "session_secret.key")
if not os.path.exists(SECRET_FILE):
    with open(SECRET_FILE, "wb") as f:
        f.write(secrets.token_bytes(32))
with open(SECRET_FILE, "rb") as f:
    SESSION_SECRET = f.read().hex()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== Startup =====
    # Captura o loop do FastAPI para permitir broadcast WebSocket vindo da thread TCP.
    set_main_loop(asyncio.get_running_loop())

    # Diagnóstico de configuração sem abrir credencial, autenticar ou enviar push.
    mobile_push = configuration_status()
    logging.getLogger("uvicorn.error").info(
        "FCM: enabled=%s, credencial externa informada=%s (entrega ainda não validada)",
        mobile_push["enabled"], mobile_push["credentials_configured"],
    )

    # Web Push: garante chaves VAPID (salvas em /data). Mantém a mesma chave entre reinícios.
    keys = ensure_vapid_keys()
    print(f"[PUSH] VAPID pronto. Public key começa com: {keys['public_key'][:16]}…")

    # Sobe o servidor de chamados (TCP + descoberta UDP) junto com o FastAPI.
    # Configurável por env: CHAMADOS_HOST / CHAMADOS_PORT.
    start_chamados_server()

    # Loop de auto-reset (vistoria/checkup) em background
    reset_task = asyncio.create_task(_auto_reset_loop())

    try:
        yield
    finally:
        # ===== Shutdown =====
        reset_task.cancel()
        try:
            await reset_task
        except asyncio.CancelledError:
            pass
        stop_chamados_server()


app = FastAPI(title="Controle de Manutenção - Computadores", lifespan=lifespan)

from .api.v1.router import router as mobile_api_router
from .api.v1.realtime import router as mobile_ws_router

app.include_router(mobile_api_router)
app.include_router(mobile_ws_router)


# ===== Auto-reset de Vistoria / Checkup =====
# Regras:
# - Verde (OK): expira em 7 dias
# - Amarelo (ATTENTION): expira em 2 dias
# - Vermelho (URGENT): expira em 1 dia
#
# Importante: o sistema NÃO apaga as datas (last_inspection_date/last_checkup_date).
# Ele apenas desmarca os checkboxes quando o prazo vence.
# Frequência do loop (segundos). 3600 = 1 hora.
# Ajustável por env: AUTO_RESET_LOOP_SECONDS
AUTO_RESET_LOOP_SECONDS = int(os.getenv("AUTO_RESET_LOOP_SECONDS", "3600"))


async def _auto_reset_loop():
    """Loop em background para manter o banco 'honesto' sem depender de acessos."""
    # roda uma vez no começo
    try:
        db = SessionLocal()
        try:
            n = apply_auto_reset_checks(db)
            if n:
                print(f"[AUTO-RESET] Desmarcou {n} check(s) vencidos.")
        finally:
            db.close()
    except Exception as e:
        print(f"[AUTO-RESET] Falhou na execução inicial: {e}")

    while True:
        await asyncio.sleep(max(60, AUTO_RESET_LOOP_SECONDS))
        try:
            db = SessionLocal()
            try:
                n = apply_auto_reset_checks(db)
                if n:
                    print(f"[AUTO-RESET] Desmarcou {n} check(s) vencidos.")
            finally:
                db.close()
        except Exception as e:
            print(f"[AUTO-RESET] Falhou no loop: {e}")


from .database import SessionLocal
from fastapi.responses import RedirectResponse

PUBLIC_PATHS = {"/login", "/logout", "/setup"}

@app.middleware("http")
async def auth_guard(request: Request, call_next):
    request.state.user = None
    path = request.url.path

    if path.startswith("/api/v1/") or path.startswith("/static") or path in PUBLIC_PATHS:
        return await call_next(request)

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    db = SessionLocal()
    try:
        user = db.get(User, int(user_id))
    finally:
        db.close()

    if not user or not user.is_active:
        request.session.clear()
        return RedirectResponse("/login", status_code=302)

    request.state.user = user
    return await call_next(request)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")

# --- Service Worker / Web Push (push real exige HTTPS) ---
@app.get("/sw.js")
async def service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")


@app.get("/manifest.webmanifest")
async def manifest_webmanifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")


@app.get("/push/public_key")
def push_public_key():
    return {"publicKey": get_public_key()}


@app.post("/push/subscribe")
async def push_subscribe(request: Request, db: Session = Depends(get_db)):
    sub = await request.json()
    upsert_subscription(db, sub, request.headers.get("user-agent"))
    db.commit()
    return {"ok": True}


@app.post("/push/unsubscribe")
async def push_unsubscribe(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    endpoint = (body.get("endpoint") or "").strip()
    delete_subscription(db, endpoint)
    db.commit()
    return {"ok": True}


from sqlalchemy import select
from collections import defaultdict


@app.get("/rooms", response_class=HTMLResponse)
def rooms_list(request: Request, db: Session = Depends(get_db)):
    machines = crud.list_machines(db)
    grouped = defaultdict(list)
    for m in machines:
        grouped[m.room_name].append(m.room_status or "OK")

    rooms = []
    for room_name, statuses in sorted(grouped.items(), key=lambda x: x[0].lower()):
        rooms.append({"room_name": room_name, "room_status": worst_status(statuses)})

    return templates.TemplateResponse("rooms.html", {"request": request, "rooms": rooms})

@app.post("/rooms/update")
def rooms_update(
    request: Request,
    room_name: str = Form(...),
    room_status: str = Form(...),
    db: Session = Depends(get_db),
):
    room_status = (room_status or "OK").strip() or "OK"
    now = datetime.utcnow()
    actor = request.state.user.username if request.state.user else None
    machines = crud.list_machines(db)
    for m in machines:
        if m.room_name == room_name:
            m.room_status = room_status
            if actor:
                m.updated_by = actor
                m.updated_at = now
    db.commit()
    return RedirectResponse(url="/rooms", status_code=303)

def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _parse_peripherals_from_form(form: dict, profile: str):
    state = {}
    defs = peripherals_for_profile(profile)
    for p in defs:
        present = form.get(f"present_{p.code}") == "on"
        tested = form.get(f"tested_{p.code}") == "on"
        qty = 0

        if p.has_quantity and p.code == "CABO_RCA":
            qty_val = _safe_int(form.get(f"qty_{p.code}"), 0)
            if not present:
                qty_val = 0
            if present and qty_val <= 0:
                qty_val = 2  # padrão A/B
            qty = max(0, qty_val)
            if qty <= 0:
                present = False
                tested = False

        if not present:
            tested = False

        state[p.code] = {"present": present, "tested_working": tested, "quantity": qty}

    return state


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    context = _build_dashboard_context(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            **context,
        },
    )


@app.get("/machines", response_class=HTMLResponse)
def machines_list(
    request: Request,
    q: str | None = None,
    profile: str | None = None,
    segment: str | None = None,
    inspected: str | None = None,
    checkup: str | None = None,
    room_status: str | None = None,
    db: Session = Depends(get_db),
):
    # Garante que os checkboxes refletirão os prazos (mesmo se o servidor acabou de ligar).
    apply_auto_reset_checks(db)

    prof = (profile or "").strip().upper() or None
    if prof not in ("A", "B", "C"):
        prof = None

    seg = (segment or "").strip().upper() or None
    if seg not in ("INFANTIL", "FUND1", "FUND2", "EM", "ADMIN", "OUTRO"):
        seg = None

    rs = (room_status or "").strip().upper() or None
    if rs not in ("OK", "ATTENTION", "URGENT"):
        rs = None

    def _parse_tri(v: str | None):
        v = (v or "").strip().lower()
        if v in ("1", "true", "yes", "sim", "s", "y"):
            return True
        if v in ("0", "false", "no", "nao", "não", "n"):
            return False
        return None

    inspected_b = _parse_tri(inspected)
    checkup_b = _parse_tri(checkup)

    machines = crud.list_machines(
        db,
        q=q,
        profile=prof,
        room_status=rs,
        inspected=inspected_b,
        checkup_done=checkup_b,
    )

    # Segmento é uma 'tag' derivada do nome da sala (nem sempre dá pra filtrar via SQL)
    # então filtramos em memória.
    for m in machines:
        m.segment = derive_segment(m.room_name or m.machine_name, m.profile)

    if seg:
        machines = [m for m in machines if getattr(m, "segment", None) == seg]

    active_filters = {
        "profile": prof or "",
        "segment": seg or "",
        "inspected": inspected or "",
        "checkup": checkup or "",
        "room_status": rs or "",
    }

    return templates.TemplateResponse(
        "machines_list.html",
        {
            "request": request,
            "machines": machines,
            "q": q or "",
            **active_filters,
        },
    )


# ----------------- Chamados (Professor.py) -----------------


TICKET_STATUSES = {"OPEN", "IN_PROGRESS", "CLOSED"}


@app.get("/tickets", response_class=HTMLResponse)
def tickets_list(
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    status = (status or "OPEN").upper().strip()
    if status not in TICKET_STATUSES and status != "ALL":
        status = "ALL"

    stmt = select(Ticket).order_by(Ticket.created_at.desc())
    if status in TICKET_STATUSES:
        stmt = stmt.where(Ticket.status == status)
    tickets = list(db.execute(stmt).scalars().all())

    heartbeats = list(db.execute(select(MachineHeartbeat)).scalars().all())
    hb_map = {hb.pc_name: hb for hb in heartbeats}

    now = datetime.utcnow()
    online = []
    for hb in heartbeats:
        age = (now - hb.last_seen).total_seconds()
        online.append(
            {
                "hb": hb,
                "age_seconds": int(age),
                "is_online": age <= ONLINE_THRESHOLD_SECONDS,
            }
        )

    # online primeiro, depois mais recentes
    online.sort(key=lambda x: (not x["is_online"], x["age_seconds"]))

    return templates.TemplateResponse(
        "tickets_list.html",
        {
            "request": request,
            "tickets": tickets,
            "hb_map": hb_map,
            "status": status,
            "online": online,
            "threshold": ONLINE_THRESHOLD_SECONDS,
        },
    )


@app.post("/tickets/{ticket_id}/take")
def tickets_take(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    crud.take_ticket(db, ticket_id, request.state.user.username)
    return RedirectResponse(url="/tickets?status=IN_PROGRESS", status_code=303)


@app.post("/tickets/{ticket_id}/close")
def tickets_close(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    crud.close_ticket(db, ticket_id, request.state.user.username)
    return RedirectResponse(url="/tickets?status=IN_PROGRESS", status_code=303)


@app.get("/api/tickets")
def api_tickets(status: str | None = None, db: Session = Depends(get_db)):
    """Endpoint JSON para a tela em tempo real (sem reload)."""
    status = (status or "OPEN").upper().strip()
    if status not in TICKET_STATUSES and status != "ALL":
        status = "ALL"
    stmt = select(Ticket).options(selectinload(Ticket.machine)).order_by(Ticket.created_at.desc())
    if status in TICKET_STATUSES:
        stmt = stmt.where(Ticket.status == status)
    tickets = list(db.execute(stmt).scalars().all())

    out = []
    for t in tickets:
        created_iso = _as_utc(t.created_at).isoformat() if t.created_at else None
        assigned_iso = _as_utc(t.assigned_at).isoformat() if t.assigned_at else None
        closed_iso = _as_utc(t.closed_at).isoformat() if t.closed_at else None
        out.append(
            {
                "id": t.id,
                "pc_name": t.pc_name,
                "problem": t.problem,
                "reported_user": t.reported_user,
                "diagnostics_json": t.diagnostics_json,
                "status": t.status,
                # ISO com timezone (UTC). O front converte para o fuso do dispositivo.
                "created_at": created_iso,
                "assigned_at": assigned_iso,
                "assigned_by": t.assigned_by,
                "closed_at": closed_iso,
                "closed_by": t.closed_by,
                "machine": (
                    {
                        "id": t.machine.id,
                        "room_name": t.machine.room_name,
                    }
                    if t.machine
                    else None
                ),
            }
        )
    return {"tickets": out}


@app.get("/api/online")
def api_online(
    threshold: int = ONLINE_THRESHOLD_SECONDS,
    db: Session = Depends(get_db),
):
    stmt = select(MachineHeartbeat).options(selectinload(MachineHeartbeat.machine))
    heartbeats = list(db.execute(stmt).scalars().all())
    now = datetime.utcnow()

    online = []
    for hb in heartbeats:
        age = int((now - hb.last_seen).total_seconds()) if hb.last_seen else 10**9
        last_user = (hb.last_user or "").strip() or None
        online.append(
            {
                "pc_name": hb.pc_name,
                "age_seconds": age,
                "is_online": age <= int(threshold),
                # Login feito sim/não: se há usuário no heartbeat, alguém está logado.
                "login_active": bool(last_user),
                "last_user": last_user,
                "machine": (
                    {
                        "id": hb.machine.id,
                        "room_name": hb.machine.room_name,
                    }
                    if hb.machine
                    else None
                ),
            }
        )

    online.sort(key=lambda x: (not x["is_online"], x["age_seconds"]))
    return {"online": online, "threshold": int(threshold)}


@app.websocket("/ws/tickets")
async def ws_tickets(ws: WebSocket):
    """Canal realtime.

    - Autentica via sessão (mesma do site)
    - Mantém conexão aberta e permite broadcast de eventos
    """

    # SessionMiddleware injeta a sessão em ws.scope
    session = ws.scope.get("session") or {}
    user_id = session.get("user_id")
    if not user_id:
        await ws.close(code=1008)
        return

    # valida usuário ativo
    db = SessionLocal()
    try:
        user = db.get(User, int(user_id))
    finally:
        db.close()
    if not user or not user.is_active:
        await ws.close(code=1008)
        return

    await manager.connect(ws)
    try:
        # sinaliza para o cliente que está pronto
        await ws.send_text('{"type":"ready"}')

        # Mantém aberto. O cliente manda 'ping' a cada ~25s.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)


@app.get("/machines/new", response_class=HTMLResponse)
def machines_new(request: Request, profile: str = PROFILE_A):
    profile = profile if profile in (PROFILE_A, PROFILE_B, PROFILE_C) else PROFILE_A
    return templates.TemplateResponse(
        "machine_form.html",
        {
            "request": request,
            "mode": "create",
            "machine": None,
            "profile": profile,
            "profiles": [
                (PROFILE_A, "Perfil A (Infantil 2–5 + 1º–4º)"),
                (PROFILE_B, "Perfil B (5º–9º + 1ª–3ª série)"),
                (PROFILE_C, "Perfil C (Administrativo)"),
            ],
            "peripherals": peripherals_for_profile(profile),
            "peripheral_values": {},
        },
    )


@app.post("/machines/new")
async def machines_create(
    request: Request,
    room_status: str | None = Form(None),
    machine_name: str = Form(...),
    room_name: str = Form(...),
    ip: str = Form(...),
    username: str = Form(...),
    profile: str = Form(...),
    inspected: str | None = Form(None),
    last_inspection_date: str | None = Form(None),
    checkup_done: str | None = Form(None),
    last_checkup_date: str | None = Form(None),
    maintenance_description: str | None = Form(None),
    os_name: str | None = Form(None),
    gpu_type: str | None = Form(None),
    ram_gb: str | None = Form(None),
    ram_modules: str | None = Form(None),
    cpu_model: str | None = Form(None),
    storage_type: str | None = Form(None),
    storage_gb: str | None = Form(None),
    office_installed: str | None = Form(None),
    office_version: str | None = Form(None),
    kaspersky_installed: str | None = Form(None),
    kaspersky_updated: str | None = Form(None),
    usb_ports_qty: str | None = Form(None),
    usb_ports_working: str | None = Form(None),
    adapters: str | None = Form(None),

    hoptodesk_id: str | None = Form(None),
    hoptodesk_password: str | None = Form(None),
    mac_address: str | None = Form(None),

    projector_lamp_hours: str | None = Form(None),

    db: Session = Depends(get_db),
):
    profile = profile if profile in (PROFILE_A, PROFILE_B, PROFILE_C) else PROFILE_A

    form = dict(await request.form())
    peripheral_state = _parse_peripherals_from_form(form, profile)

    inspected_bool = inspected == "on"
    last_date = _parse_date(last_inspection_date)

    checkup_bool = checkup_done == "on"
    checkup_date = _parse_date(last_checkup_date)

    lamp_val = _safe_int(projector_lamp_hours, 0) if (projector_lamp_hours or "").strip() else None
    # Horas da lâmpada: somente Perfil A
    if profile != PROFILE_A:
        lamp_val = None

    data = {
        "machine_name": machine_name.strip(),
        "room_name": room_name.strip(),
        "room_status": (room_status or "OK").strip() or "OK",
        "ip": ip.strip(),
        "username": username.strip(),
        "profile": profile,
        "inspected": inspected_bool,
        "last_inspection_date": last_date,
        "checkup_done": checkup_bool,
        "last_checkup_date": checkup_date,
        "os_name": (os_name or "").strip() or None,
        "gpu_type": (gpu_type or "").strip() or None,
        "ram_gb": _safe_int(ram_gb, 0) if (ram_gb or "").strip() else None,
        "ram_modules": _safe_int(ram_modules, 0) if (ram_modules or "").strip() else None,
        "cpu_model": (cpu_model or "").strip() or None,
        "storage_type": (storage_type or "").strip() or None,
        "storage_gb": _safe_int(storage_gb, 0) if (storage_gb or "").strip() else None,
        "office_installed": office_installed == "on",
        "office_version": (office_version or "").strip() or None,
        "kaspersky_installed": kaspersky_installed == "on",
        "kaspersky_updated": kaspersky_updated == "on",
        "usb_ports_qty": _safe_int(usb_ports_qty, 0) if (usb_ports_qty or "").strip() else None,
        "usb_ports_working": usb_ports_working == "on",
        "adapters": (adapters or "").strip() or None,

        # Acesso remoto / rede
        "hoptodesk_id": (hoptodesk_id or "").strip() or None,
        "hoptodesk_password": (hoptodesk_password or "").strip() or None,
        "mac_address": _normalize_mac(mac_address),

        # Projetor (apenas Perfil A)
        "projector_lamp_hours": lamp_val,

        "maintenance_description": (maintenance_description or "").strip() or None,
    }
    machine = crud.create_machine(db, data, peripheral_state, actor_username=request.state.user.username)
    return RedirectResponse(url=f"/machines/{machine.id}", status_code=303)


@app.get("/machines/{machine_id}", response_class=HTMLResponse)
def machines_detail(machine_id: int, request: Request, db: Session = Depends(get_db)):
    machine = crud.get_machine(db, machine_id)
    if not machine:
        return RedirectResponse(url="/machines", status_code=302)

    per_map = {p.peripheral_code: p for p in machine.peripherals}
    peripherals = peripherals_for_profile(machine.profile)

    return templates.TemplateResponse(
        "machine_detail.html",
        {"request": request, "machine": machine, "peripherals": peripherals, "per_map": per_map},
    )


@app.get("/machines/{machine_id}/edit", response_class=HTMLResponse)
def machines_edit(machine_id: int, request: Request, profile: str | None = None, db: Session = Depends(get_db)):
    machine = crud.get_machine(db, machine_id)
    if not machine:
        return RedirectResponse(url="/machines", status_code=302)

    effective_profile = profile if profile in (PROFILE_A, PROFILE_B, PROFILE_C) else machine.profile

    per_values = {}
    for p in machine.peripherals:
        per_values[p.peripheral_code] = {
            "present": p.present,
            "tested_working": p.tested_working,
            "quantity": getattr(p, "quantity", 0) or 0,
        }

    return templates.TemplateResponse(
        "machine_form.html",
        {
            "request": request,
            "mode": "edit",
            "machine": machine,
            "profile": effective_profile,
            "profiles": [
                (PROFILE_A, "Perfil A (Infantil 2–5 + 1º–4º)"),
                (PROFILE_B, "Perfil B (5º–9º + 1ª–3ª série)"),
                (PROFILE_C, "Perfil C (Administrativo)"),
            ],
            "peripherals": peripherals_for_profile(effective_profile),
            "peripheral_values": per_values,
        },
    )


@app.post("/machines/{machine_id}/edit")
async def machines_update(
    machine_id: int,
    request: Request,
    room_status: str | None = Form(None),
    machine_name: str = Form(...),
    room_name: str = Form(...),
    ip: str = Form(...),
    username: str = Form(...),
    profile: str = Form(...),
    inspected: str | None = Form(None),
    last_inspection_date: str | None = Form(None),
    checkup_done: str | None = Form(None),
    last_checkup_date: str | None = Form(None),
    maintenance_description: str | None = Form(None),
    os_name: str | None = Form(None),
    gpu_type: str | None = Form(None),
    ram_gb: str | None = Form(None),
    ram_modules: str | None = Form(None),
    cpu_model: str | None = Form(None),
    storage_type: str | None = Form(None),
    storage_gb: str | None = Form(None),
    office_installed: str | None = Form(None),
    office_version: str | None = Form(None),
    kaspersky_installed: str | None = Form(None),
    kaspersky_updated: str | None = Form(None),
    usb_ports_qty: str | None = Form(None),
    usb_ports_working: str | None = Form(None),
    adapters: str | None = Form(None),

    hoptodesk_id: str | None = Form(None),
    hoptodesk_password: str | None = Form(None),
    mac_address: str | None = Form(None),

    projector_lamp_hours: str | None = Form(None),

    db: Session = Depends(get_db),
):
    machine = crud.get_machine(db, machine_id)
    if not machine:
        return RedirectResponse(url="/machines", status_code=302)

    profile = profile if profile in (PROFILE_A, PROFILE_B, PROFILE_C) else PROFILE_A

    form = dict(await request.form())
    peripheral_state = _parse_peripherals_from_form(form, profile)

    inspected_bool = inspected == "on"
    last_date = _parse_date(last_inspection_date)

    checkup_bool = checkup_done == "on"
    checkup_date = _parse_date(last_checkup_date)

    lamp_val = _safe_int(projector_lamp_hours, 0) if (projector_lamp_hours or "").strip() else None
    # Horas da lâmpada: somente Perfil A
    if profile != PROFILE_A:
        lamp_val = None

    data = {
        "machine_name": machine_name.strip(),
        "room_name": room_name.strip(),
        "room_status": (room_status or "OK").strip() or "OK",
        "ip": ip.strip(),
        "username": username.strip(),
        "profile": profile,
        "inspected": inspected_bool,
        "last_inspection_date": last_date,
        "checkup_done": checkup_bool,
        "last_checkup_date": checkup_date,
        "os_name": (os_name or "").strip() or None,
        "gpu_type": (gpu_type or "").strip() or None,
        "ram_gb": _safe_int(ram_gb, 0) if (ram_gb or "").strip() else None,
        "ram_modules": _safe_int(ram_modules, 0) if (ram_modules or "").strip() else None,
        "cpu_model": (cpu_model or "").strip() or None,
        "storage_type": (storage_type or "").strip() or None,
        "storage_gb": _safe_int(storage_gb, 0) if (storage_gb or "").strip() else None,
        "office_installed": office_installed == "on",
        "office_version": (office_version or "").strip() or None,
        "kaspersky_installed": kaspersky_installed == "on",
        "kaspersky_updated": kaspersky_updated == "on",
        "usb_ports_qty": _safe_int(usb_ports_qty, 0) if (usb_ports_qty or "").strip() else None,
        "usb_ports_working": usb_ports_working == "on",
        "adapters": (adapters or "").strip() or None,

        # Acesso remoto / rede
        "hoptodesk_id": (hoptodesk_id or "").strip() or None,
        "hoptodesk_password": (hoptodesk_password or "").strip() or None,
        "mac_address": _normalize_mac(mac_address),

        # Projetor (apenas Perfil A)
        "projector_lamp_hours": lamp_val,

        "maintenance_description": (maintenance_description or "").strip() or None,
    }
    crud.update_machine(db, machine, data, peripheral_state, actor_username=request.state.user.username)
    return RedirectResponse(url=f"/machines/{machine_id}", status_code=303)

from fastapi import HTTPException

@app.get("/setup", response_class=HTMLResponse)
def setup_admin_get(request: Request, db: Session = Depends(get_db)):
    users = crud.list_users(db)
    if users:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("setup_admin.html", {"request": request})

@app.post("/setup")
def setup_admin_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    users = crud.list_users(db)
    if users:
        return RedirectResponse("/login", status_code=302)

    u = username.strip()
    if not u:
        raise HTTPException(status_code=400, detail="Usuário inválido")

    admin = crud.create_user(db, u, hash_password(password), is_admin=True)
    request.session["user_id"] = admin.id
    return RedirectResponse("/machines", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/machines", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = crud.get_user_by_username(db, username.strip())
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuário ou senha inválidos."})

    request.session["user_id"] = user.id
    return RedirectResponse("/machines", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

def require_admin(request: Request):
    user = request.state.user
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao admin.")

@app.get("/users", response_class=HTMLResponse)
def users_list(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    users = crud.list_users(db)
    return templates.TemplateResponse("users_list.html", {"request": request, "users": users})

@app.get("/users/new", response_class=HTMLResponse)
def users_new(request: Request):
    require_admin(request)
    return templates.TemplateResponse(
        "user_form.html",
        {
            "request": request,
            "error": None,
            "mode": "new",
            "action": "/users/new",
            "user": None,
        },
    )

@app.post("/users/new", response_class=HTMLResponse)
def users_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str | None = Form(None),
    db: Session = Depends(get_db),
):
    require_admin(request)
    u = username.strip()
    if not u:
        return templates.TemplateResponse(
            "user_form.html",
            {
                "request": request,
                "error": "Usuário inválido.",
                "mode": "new",
                "action": "/users/new",
                "user": None,
            },
        )

    if crud.get_user_by_username(db, u):
        return templates.TemplateResponse(
            "user_form.html",
            {
                "request": request,
                "error": "Usuário já existe.",
                "mode": "new",
                "action": "/users/new",
                "user": None,
            },
        )

    crud.create_user(db, u, hash_password(password), is_admin=(is_admin == "on"))
    return RedirectResponse("/users", status_code=303)


@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
def users_edit(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    u = crud.get_user_by_id(db, user_id)
    if not u:
        return RedirectResponse("/users", status_code=302)

    return templates.TemplateResponse(
        "user_form.html",
        {
            "request": request,
            "error": None,
            "mode": "edit",
            "action": f"/users/{u.id}/edit",
            "user": u,
        },
    )


@app.post("/users/{user_id}/edit", response_class=HTMLResponse)
def users_update(
    user_id: int,
    request: Request,
    username: str = Form(...),
    password: str | None = Form(None),
    is_admin: str | None = Form(None),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    require_admin(request)
    u = crud.get_user_by_id(db, user_id)
    if not u:
        return RedirectResponse("/users", status_code=302)

    new_username = (username or "").strip()
    if not new_username:
        return templates.TemplateResponse(
            "user_form.html",
            {
                "request": request,
                "error": "Usuário inválido.",
                "mode": "edit",
                "action": f"/users/{u.id}/edit",
                "user": u,
            },
        )

    existing = crud.get_user_by_username(db, new_username)
    if existing and existing.id != u.id:
        return templates.TemplateResponse(
            "user_form.html",
            {
                "request": request,
                "error": "Usuário já existe.",
                "mode": "edit",
                "action": f"/users/{u.id}/edit",
                "user": u,
            },
        )

    new_is_admin = is_admin == "on"
    new_is_active = is_active == "on"

    # não deixa desativar a si mesmo por acidente
    if request.state.user.id == u.id and not new_is_active:
        new_is_active = True

    new_password_hash = None
    if password and password.strip():
        new_password_hash = hash_password(password.strip())

    crud.update_user(
        db,
        u,
        username=new_username,
        password_hash=new_password_hash,
        is_admin=new_is_admin,
        is_active=new_is_active,
    )

    return RedirectResponse("/users", status_code=303)

@app.post("/users/{user_id}/toggle")
def users_toggle(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    u = crud.get_user_by_id(db, user_id)
    if u:
        # não deixa desativar a si mesmo por acidente
        if request.state.user.id == u.id:
            return RedirectResponse("/users", status_code=303)
        crud.set_user_active(db, u, not u.is_active)
    return RedirectResponse("/users", status_code=303)


@app.post("/machines/{machine_id}/delete")
def machines_delete(machine_id: int, request: Request, db: Session = Depends(get_db)):
    machine = crud.get_machine(db, machine_id)
    if machine:
        crud.delete_machine(db, machine, actor_username=request.state.user.username)
    return RedirectResponse(url="/machines", status_code=303)

@app.get("/reports/relatorio.xlsm")
def report_xlsm(db: Session = Depends(get_db)):
    # A + B na mesma aba (união de periféricos mantendo ordem)
    defs_a = peripherals_for_profile(PROFILE_A)
    defs_b = peripherals_for_profile(PROFILE_B)
    codes = {d.code for d in defs_a}
    defs_ab = list(defs_a) + [d for d in defs_b if d.code not in codes]

    defs_c = peripherals_for_profile(PROFILE_C)

    stmt_ab = (
        select(Machine)
        .options(selectinload(Machine.peripherals))
        .where(Machine.profile.in_([PROFILE_A, PROFILE_B]))
        .order_by(Machine.room_name, Machine.machine_name)
    )
    machines_ab = list(db.execute(stmt_ab).scalars().all())

    stmt_c = (
        select(Machine)
        .options(selectinload(Machine.peripherals))
        .where(Machine.profile == PROFILE_C)
        .order_by(Machine.room_name, Machine.machine_name)
    )
    machines_c = list(db.execute(stmt_c).scalars().all())

    content = build_xlsm_report(machines_ab, machines_c, defs_ab, defs_c)

    filename = "relatorio_manutencao.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.ms-excel.sheet.macroEnabled.12",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    import uvicorn
    # Voltando para HTTP/porta 8000 (sem SSL), pois o ambiente do serviço bloqueia 8443.
    # Se algum dia você quiser mudar a porta sem editar código:
    #   set PORT=8000
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
