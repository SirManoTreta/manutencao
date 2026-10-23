import os
import io
import base64
import hashlib
import hmac
import secrets
import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from starlette.middleware.sessions import SessionMiddleware
from datetime import date
from fastapi import FastAPI, Request, Depends, Form, WebSocket
from starlette.websockets import WebSocketDisconnect
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text, update
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .models import Machine, User, Ticket, MachineHeartbeat, PushSubscription
from .reporting import build_xlsm_report
from collections import defaultdict

from .database import Base, engine, get_db
from . import crud
from .constants import PROFILE_A, PROFILE_B, PROFILE_C, peripherals_for_profile

# Servidor de chamados (Professor.py) integrado
from .chamados_socket import start_chamados_server, stop_chamados_server
from .realtime import set_main_loop, manager, broadcast_from_thread
from .push import ensure_vapid_keys, get_public_key, upsert_subscription, delete_subscription

Base.metadata.create_all(bind=engine)

def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(dk).decode("ascii"),
    )

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it_s, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(it_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


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
        conn.commit()

_migrate_sqlite()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# ===== Timezone padrão do sistema (Brasília / UTC-3) =====
#
# A aplicação salva timestamps em UTC (datetime.utcnow). Para exibição no site,
# convertemos para America/Sao_Paulo. Isso evita confusão quando o servidor
# está em UTC mas os usuários esperam horário local.
try:
    # Em algumas instalações do Windows, a base de timezones IANA não vem no sistema.
    # O Python tenta usar o pacote "tzdata" nesses casos. Se não estiver instalado,
    # fazemos fallback para UTC-3 fixo (Brasília).
    BR_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    BR_TZ = timezone(timedelta(hours=-3))


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


def derive_segment(room_or_name: str | None, profile: str | None) -> str:
    """Deriva um 'segmento' educacional simples a partir do nome da sala/PC.

    Retorna chaves estáveis para filtro: INFANTIL, FUND1, FUND2, EM, ADMIN, OUTRO.
    """
    prof = (profile or "").strip().upper()
    if prof == "C":
        return "ADMIN"

    txt = (room_or_name or "").strip().upper()
    # Normalização leve de acentos mais comuns
    txt = (
        txt.replace("Ç", "C")
        .replace("Ã", "A")
        .replace("Á", "A")
        .replace("Â", "A")
        .replace("É", "E")
        .replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ô", "O")
        .replace("Õ", "O")
        .replace("Ú", "U")
    )

    if "INFANTIL" in txt or re.search(r"\bINF\b", txt):
        return "INFANTIL"

    # Ensino Médio: 1ºEM / 2ºEM / 3ºEM | 1ª SÉRIE / 2ª SÉRIE / 3ª SÉRIE
    if re.search(r"\bENSINO\s+MEDIO\b", txt):
        return "EM"
    m_em = re.search(r"(\d+)\s*[ºª]?\s*(EM|SERIE|S[EÉ]RIE)", txt)
    if m_em:
        return "EM"

    # Fundamental por 'ANO'
    m_fund = re.search(r"(\d+)\s*[ºª]?\s*ANO", txt)
    if m_fund:
        n = int(m_fund.group(1))
        if 1 <= n <= 5:
            return "FUND1"
        if 6 <= n <= 9:
            return "FUND2"

    # Fallback por perfil
    if prof == "A":
        # Perfil A = Infantil 2–5 + 1º–4º (na dúvida, Fund1)
        return "FUND1"
    if prof == "B":
        # Perfil B = 5º–9º + EM (na dúvida, Fund2)
        return "FUND2"

    return "OUTRO"

STATIC_DIR = os.path.join(APP_DIR, "static")

DATA_DIR = os.path.join(os.path.dirname(APP_DIR), "data")
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


# ===== Auto-reset de Vistoria / Checkup =====
# Regras:
# - Verde (OK): expira em 7 dias
# - Amarelo (ATTENTION): expira em 2 dias
# - Vermelho (URGENT): expira em 1 dia
#
# Importante: o sistema NÃO apaga as datas (last_inspection_date/last_checkup_date).
# Ele apenas desmarca os checkboxes quando o prazo vence.
AUTO_RESET_DAYS_BY_STATUS = {
    "OK": 7,
    "ATTENTION": 2,
    "URGENT": 1,
}

# Frequência do loop (segundos). 3600 = 1 hora.
# Ajustável por env: AUTO_RESET_LOOP_SECONDS
AUTO_RESET_LOOP_SECONDS = int(os.getenv("AUTO_RESET_LOOP_SECONDS", "3600"))


def _today_br() -> date:
    """Data corrente no fuso de Brasília."""
    try:
        return datetime.now(BR_TZ).date()
    except Exception:
        return datetime.utcnow().date()


def apply_auto_reset_checks(db: Session) -> int:
    """Desmarca inspected/checkup_done quando vencidos, conforme room_status.

    Retorna quantas marcações foram desfeitas.
    """
    today = _today_br()
    # Observação: não alteramos updated_by/updated_at para não "atropelar" a auditoria humana.

    stmt = select(Machine).where((Machine.inspected == True) | (Machine.checkup_done == True))  # noqa: E712
    machines = list(db.execute(stmt).scalars().all())

    changed = 0
    for m in machines:
        status = (m.room_status or "OK").strip().upper() or "OK"
        days_limit = AUTO_RESET_DAYS_BY_STATUS.get(status, 7)

        dirty = False
        if m.inspected and m.last_inspection_date:
            delta = (today - m.last_inspection_date).days
            if delta >= days_limit:
                m.inspected = False
                dirty = True
                changed += 1

        if m.checkup_done and m.last_checkup_date:
            delta = (today - m.last_checkup_date).days
            if delta >= days_limit:
                m.checkup_done = False
                dirty = True
                changed += 1

    if changed:
        db.commit()

    return changed


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

    if path.startswith("/static") or path in PUBLIC_PATHS:
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

STATUS_ORDER = {"OK": 0, "ATTENTION": 1, "URGENT": 2}

def worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "OK"
    return max(statuses, key=lambda s: STATUS_ORDER.get(s, 0))

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


def _normalize_mac(value: str | None) -> str | None:
    """Normaliza MAC para o formato AA:BB:CC:DD:EE:FF quando possível.

    - Aceita: AA-BB-CC-DD-EE-FF, AABB.CCDD.EEFF, aabbccddeeff
    - Se não bater formato conhecido, devolve o texto 'limpo' (maiúsculo) sem bloquear o salvamento.
    """
    if not value:
        return None
    s = (value or "").strip().upper()
    if not s:
        return None

    # Formato com pontos (Cisco): AABB.CCDD.EEFF
    if re.fullmatch(r"[0-9A-F]{4}\.[0-9A-F]{4}\.[0-9A-F]{4}", s):
        raw = s.replace(".", "")
        return ":".join(raw[i:i+2] for i in range(0, 12, 2))

    # Formato com separador: AA:BB:CC:DD:EE:FF ou AA-BB-CC-DD-EE-FF
    if re.fullmatch(r"([0-9A-F]{2}[:-]){5}[0-9A-F]{2}", s):
        return s.replace("-", ":")

    # Formato puro: AABBCCDDEEFF
    raw = s.replace(":", "").replace("-", "").replace(".", "")
    if re.fullmatch(r"[0-9A-F]{12}", raw):
        return ":".join(raw[i:i+2] for i in range(0, 12, 2))

    return s


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


def _dashboard_bar_rows(label_map: dict[str, int], total: int):
    rows = []
    for label, count in label_map.items():
        percent = round((count * 100 / total), 1) if total else 0
        rows.append({"label": label, "count": count, "percent": percent})
    return rows


def _build_dashboard_context(db: Session):
    apply_auto_reset_checks(db)

    machines = crud.list_machines(db)
    for m in machines:
        m.segment = derive_segment(m.room_name or m.machine_name, m.profile)

    total_machines = len(machines)
    rooms_count = len({(m.room_name or "").strip() for m in machines if (m.room_name or "").strip()})

    status_counts = {
        "OK": len([m for m in machines if m.room_status == "OK"]),
        "Atenção": len([m for m in machines if m.room_status == "ATTENTION"]),
        "Urgente": len([m for m in machines if m.room_status == "URGENT"]),
    }

    profile_counts = {
        "Perfil A": len([m for m in machines if m.profile == "A"]),
        "Perfil B": len([m for m in machines if m.profile == "B"]),
        "Perfil C": len([m for m in machines if m.profile == "C"]),
    }

    segment_counts = {
        "Infantil": len([m for m in machines if getattr(m, "segment", None) == "INFANTIL"]),
        "Fundamental 1": len([m for m in machines if getattr(m, "segment", None) == "FUND1"]),
        "Fundamental 2": len([m for m in machines if getattr(m, "segment", None) == "FUND2"]),
        "Ensino Médio": len([m for m in machines if getattr(m, "segment", None) == "EM"]),
        "Administrativo": len([m for m in machines if getattr(m, "segment", None) == "ADMIN"]),
        "Outros": len([m for m in machines if getattr(m, "segment", None) == "OUTRO"]),
    }

    room_rank = {"OK": 0, "ATTENTION": 1, "URGENT": 2}
    room_worst = {}
    for m in machines:
        room = (m.room_name or "").strip()
        if not room:
            continue
        current = room_worst.get(room, "OK")
        if room_rank.get(m.room_status or "OK", 0) > room_rank.get(current, 0):
            room_worst[room] = m.room_status or "OK"
        elif room not in room_worst:
            room_worst[room] = m.room_status or "OK"

    attention_rooms = len([status for status in room_worst.values() if status == "ATTENTION"])
    urgent_rooms = len([status for status in room_worst.values() if status == "URGENT"])

    tickets = list(db.execute(select(Ticket).order_by(Ticket.created_at.desc())).scalars().all())
    open_tickets = len([t for t in tickets if t.status != "CLOSED"])
    in_progress_tickets = len([t for t in tickets if t.status == "IN_PROGRESS"])
    closed_tickets = len([t for t in tickets if t.status == "CLOSED"])
    recent_tickets = tickets[:5]

    pending_inspections = len([m for m in machines if not m.inspected])
    pending_checkups = len([m for m in machines if not m.checkup_done])

    heartbeats = list(db.execute(select(MachineHeartbeat)).scalars().all())
    now = datetime.utcnow()
    online_count = len([hb for hb in heartbeats if hb.last_seen and (now - hb.last_seen).total_seconds() <= ONLINE_THRESHOLD_SECONDS])

    recent_machines = sorted(
        machines,
        key=lambda m: (m.updated_at or m.created_at or datetime.min),
        reverse=True,
    )[:5]

    return {
        "total_machines": total_machines,
        "rooms_count": rooms_count,
        "open_tickets": open_tickets,
        "in_progress_tickets": in_progress_tickets,
        "closed_tickets": closed_tickets,
        "pending_inspections": pending_inspections,
        "pending_checkups": pending_checkups,
        "online_count": online_count,
        "total_heartbeats": len(heartbeats),
        "attention_rooms": attention_rooms,
        "urgent_rooms": urgent_rooms,
        "status_rows": _dashboard_bar_rows(status_counts, total_machines),
        "profile_rows": _dashboard_bar_rows(profile_counts, total_machines),
        "segment_rows": _dashboard_bar_rows(segment_counts, total_machines),
        "recent_machines": recent_machines,
        "recent_tickets": recent_tickets,
    }


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


ONLINE_THRESHOLD_SECONDS = int(os.getenv("ONLINE_THRESHOLD_SECONDS", "15"))
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
    """Assume atomicamente um chamado ainda aberto.

    O UPDATE condicional evita que duas pessoas assumam o mesmo chamado ao
    mesmo tempo. Somente a primeira transição OPEN -> IN_PROGRESS prevalece.
    """
    assigned_by = request.state.user.username if request.state.user else None
    assigned_at = datetime.utcnow()
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "OPEN")
        .values(
            status="IN_PROGRESS",
            assigned_at=assigned_at,
            assigned_by=assigned_by,
        )
    )
    db.commit()

    if result.rowcount:
        broadcast_from_thread(
            {
                "type": "ticket_taken",
                "ticket_id": ticket_id,
                "assigned_by": assigned_by,
            }
        )

    return RedirectResponse(url="/tickets?status=IN_PROGRESS", status_code=303)


@app.post("/tickets/{ticket_id}/close")
def tickets_close(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    ticket_closed = False
    if t and t.status == "IN_PROGRESS":
        t.status = "CLOSED"
        t.closed_at = datetime.utcnow()
        t.closed_by = request.state.user.username if request.state.user else None
        db.commit()
        ticket_closed = True
    if ticket_closed:
        broadcast_from_thread({"type": "ticket_closed", "ticket_id": ticket_id})
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
