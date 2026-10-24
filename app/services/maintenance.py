"""Regras existentes compartilhadas entre HTML e API mobile."""
import os
import re
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import crud
from ..models import Machine, Ticket, MachineHeartbeat

try:
    BR_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    BR_TZ = timezone(timedelta(hours=-3))

AUTO_RESET_DAYS_BY_STATUS = {"OK": 7, "ATTENTION": 2, "URGENT": 1}
ONLINE_THRESHOLD_SECONDS = int(os.getenv("ONLINE_THRESHOLD_SECONDS", "15"))
STATUS_ORDER = {"OK": 0, "ATTENTION": 1, "URGENT": 2}


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



def worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "OK"
    return max(statuses, key=lambda s: STATUS_ORDER.get(s, 0))



def normalize_mac(value: str | None) -> str | None:
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



def _dashboard_bar_rows(label_map: dict[str, int], total: int):
    rows = []
    for label, count in label_map.items():
        percent = round((count * 100 / total), 1) if total else 0
        rows.append({"label": label, "count": count, "percent": percent})
    return rows



def build_dashboard_context(db: Session):
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

