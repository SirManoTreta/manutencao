import io
import re
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


def _fmt_br(d: date | None) -> str:
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def _room_group(room_name: str) -> str:
    """Agrupa salas para ficar parecido com a planilha de controle."""
    s = (room_name or "").strip()
    up = s.upper()

    # Infantil
    if "INF" in up or "APOIO INF" in up or "INFANT" in up:
        return "Ensino Infantil"

    # Médio
    if " EM" in up or up.endswith("EM") or "ENSINO MÉDIO" in up or "ENSINO MEDIO" in up:
        return "Ensino Médio"

    # Fundamental (usa "ANO" + número; ex.: "1º ano A", "2 ano B", "5º ANO", etc.)
    m = re.search(r"(\d+)\s*(?:º|°)?\s*ANO\b", up)
    grade = int(m.group(1)) if m else None

    if grade is not None:
        if grade <= 5:
            return "Ensino Fundamental I"
        return "Ensino Fundamental II"

    if "FUNDAMENTAL" in up or up.endswith("FUNDAMENTAL"):
        return "Ensino Fundamental I"

    return "Salas Compartilhadas"


def build_xlsm_report(machines_ab, machines_c, defs_ab, defs_c) -> bytes:
    """Gera o relatório em XLSX com a mesma "visão" da planilha enviada.

    - Aba 1: Informativos Salas (com seções: Médio, Fund II, Fund I, Infantil, Compartilhadas)
    - Aba 2: Informativo Administrativo (lista de PCs do administrativo)

    Obs: algumas colunas do modelo não existem no sistema hoje. Para elas, o relatório deixa em branco.
    """

    wb = Workbook()
    wb.remove(wb.active)

    ws_info = wb.create_sheet("Informativos Salas")
    ws_admin = wb.create_sheet("Informativo Administrativo")

    # remove gridlines (fica mais parecido com o modelo)
    ws_info.sheet_view.showGridLines = False
    ws_admin.sheet_view.showGridLines = False

    # ===== Estilos (simples, mas bem próximos do Excel modelo) =====
    # Cores (aproximação do print)
    title_font = Font(bold=True, size=12, color="000000")  # preto
    interval_font = Font(bold=True)
    header_font = Font(bold=True)

    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    title_fill = PatternFill("solid", fgColor="5B9BD5")     # azul claro
    interval_fill = PatternFill("solid", fgColor="F4B183")  # laranja
    header_fill = PatternFill("solid", fgColor="ACB9CA")    # cinza/azulado

    thin = Side(style="thin", color="000000")
    thick = Side(style="medium", color="000000")  # borda externa mais espessa
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def set_widths(ws, widths: dict[str, float]):
        for col, w in widths.items():
            ws.column_dimensions[col].width = w

    EDU_WIDTHS = {
        "B": 24.50,   # Salas
        "C": 5.14,    # CPU
        "D": 11.43,   # Monitor
        "E": 8.43,    # Teclado
        "F": 7.71,    # Mouse
        "G": 13.29,   # Amplificador
        "H": 11.14,   # Microfone
        "I": 13.0,    # Cabo MIC
        "J": 15.29,   # Tela Interativa
        "K": 13.0,    # Controle Tela
        "L": 14.57,   # Caneta Tela
        "M": 13.43,   # Projetor
        "N": 22.00,   # Horas lâmpada projetor
        "O": 17.71,   # Controle projetor
        "P": 17.43,   # Estojo das canetas
        "Q": 12.86,   # Canetas
        "R": 23.29,   # Suporte câmera Webex
        "S": 18.43,   # Nome resp.
    }
    ADMIN_WIDTHS = {
        "B": 19.43,   # Departamento
        "C": 12.43,   # Hostname
        "D": 20.01,   # Usuário
        "E": 4.86,    # CPU
        "F": 10.43,   # Monitor
        "G": 13.01,   # Teclado
        "H": 7.57,    # Mouse
        "I": 13.29,   # caixa de som
        "J": 13.86,   # Headset/Fone
        "K": 11.29,   # Web cam
        "L": 16.71,   # Nome resp.
    }

    def paint_range(ws, r1, c1, r2, c2, header_row=None, first_col_fill_col=None):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                cell = ws.cell(r, c)
                cell.alignment = center
                cell.border = border

                # Cabeçalho
                if header_row and r == header_row:
                    cell.font = header_font
                    cell.fill = header_fill
                    continue

                # Coluna 1 (ex.: "Sala" / "Departamento") nas linhas de dados
                if first_col_fill_col and c == first_col_fill_col and (not header_row or r > header_row):
                    cell.fill = header_fill

    def box_borders(ws, r1, c1, r2, c2):
        """Bordas finas internas + borda externa mais espessa em um retângulo."""
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                cell = ws.cell(r, c)

                left = thick if c == c1 else thin
                right = thick if c == c2 else thin
                top = thick if r == r1 else thin
                bottom = thick if r == r2 else thin

                cell.border = Border(left=left, right=right, top=top, bottom=bottom)

    # ===== Helpers de dados =====
    from .constants import PROFILE_A, PROFILE_B, peripherals_for_profile

    def _per_present_machine(m, code: str) -> bool:
        for p in (m.peripherals or []):
            if p.peripheral_code != code:
                continue
            if code == "CABO_RCA":
                return (getattr(p, "quantity", 0) or 0) > 0
            return bool(p.present)
        return False

    def aggregate_room(machines_in_room: list) -> dict:
        # responsável: quem mexeu por último
        last = max(
            machines_in_room,
            key=lambda x: getattr(x, "updated_at", None) or getattr(x, "created_at", None) or datetime.min,
        )
        who = (last.updated_by or last.created_by or "")

        profiles = {m.profile for m in machines_in_room if getattr(m, "profile", None)}

        # Horas da lâmpada do projetor (somente Perfil A): pega o valor mais recente preenchido.
        lamp_hours = None
        lamp_candidates = [
            m for m in machines_in_room
            if getattr(m, "profile", None) == PROFILE_A and getattr(m, "projector_lamp_hours", None) is not None
        ]
        if lamp_candidates:
            last_lamp = max(
                lamp_candidates,
                key=lambda x: getattr(x, "updated_at", None) or getattr(x, "created_at", None) or datetime.min,
            )
            lamp_hours = getattr(last_lamp, "projector_lamp_hours", None)

        present_map: dict[str, bool] = {}
        for m in machines_in_room:
            for p in (m.peripherals or []):
                code = p.peripheral_code
                if code == "CABO_RCA":
                    present_map[code] = present_map.get(code, False) or ((getattr(p, "quantity", 0) or 0) > 0)
                else:
                    present_map[code] = present_map.get(code, False) or bool(p.present)

        applicable = set()
        if PROFILE_A in profiles:
            applicable |= {d.code for d in peripherals_for_profile(PROFILE_A)}
        if PROFILE_B in profiles:
            applicable |= {d.code for d in peripherals_for_profile(PROFILE_B)}

        return {
            "room_name": machines_in_room[0].room_name,
            "who": who,
            "profiles": profiles,
            "present": present_map,
            "applicable": applicable,
            "lamp_hours": lamp_hours,
        }

    rooms_map: dict[str, list] = {}
    for m in machines_ab:
        rooms_map.setdefault(m.room_name, []).append(m)

    rooms_agg = [aggregate_room(v) for v in rooms_map.values() if v]

    def pick_date_range(machines) -> tuple[str, str]:
        dates = [m.last_inspection_date for m in machines if getattr(m, "last_inspection_date", None)]
        if dates:
            return _fmt_br(min(dates)), _fmt_br(max(dates))

        d2 = []
        for m in machines:
            dt = getattr(m, "updated_at", None) or getattr(m, "created_at", None)
            if dt:
                d2.append(dt.date())
        if d2:
            return _fmt_br(min(d2)), _fmt_br(max(d2))

        today = date.today()
        start = today.replace(day=1)
        return _fmt_br(start), _fmt_br(today)

    start_ab, end_ab = pick_date_range(machines_ab)
    start_c, end_c = pick_date_range(machines_c)

    # ===== Cabeçalhos (iguais ao modelo) =====
    EDU_HEADERS = [
        "Sala",
        "CPU",
        "Monitor",
        "Teclado",
        "Mouse",
        "Amplificador",
        "Microfone",
        "Cabo MIC",
        "Tela Interativa",
        "Controle tela",
        "Caneta Tela",
        "Projetor",
        "Horas lâmpada projetor",
        "Controle projetor",
        "Estojo das canetas",
        "Canetas",
        "Suporte câmera Webex",
        "Nome resp.",
    ]

    ADMIN_HEADERS = [
        "Departamento",
        "Hostname",
        "Usuário",
        "CPU",
        "Monitor",
        "Teclado",
        "Mouse",
        "Caixa de som",
        "Headset/Fone",
        "Web cam",
        "Nome resp.",
    ]

    EDU_COLS_START = 2  # B
    EDU_COLS_END = EDU_COLS_START + len(EDU_HEADERS) - 1  # U
    ADMIN_COLS_START = 2
    ADMIN_COLS_END = ADMIN_COLS_START + len(ADMIN_HEADERS) - 1  # J

    # Mapeamento de colunas -> código do sistema (quando existe)
    EDU_MAP = {
        "Monitor": "TELA",
        "Teclado": "TECLADO",
        "Mouse": "MOUSE",
        "Amplificador": "AMPLIFICADOR",
        "Microfone": "MICROFONE",
        "Cabo MIC": "CABO_MICROFONE",
        "Tela Interativa": "TELA_INTERATIVA",
        "Controle tela": "CONTROLE_TELA",
        "Controle Tela": "CONTROLE_TELA",
        "Caneta Tela": "CANETA_TELA_INTERATIVA",
        "Projetor": "PROJETOR",
        "Controle projetor": "CONTROLE_PROJETOR",
        "Controle Projetor": "CONTROLE_PROJETOR",
        "Estojo das canetas": "ESTOJO_CANETAS",
        "Estojo canetas": "ESTOJO_CANETAS",
        "Canetas": "CANETAS_PROJETOR",
        "Canetas projetor": "CANETAS_PROJETOR",
        "Canetas Projetor": "CANETAS_PROJETOR",
        "Suporte câmera Webex": "CAMERA_EAD",
    }
    ADMIN_MAP = {
        "Monitor": "TELA",
        "Teclado": "TECLADO",
        "Mouse": "MOUSE",
        "Caixa de som": "CAIXA_SOM",
        "Headset/Fone": "FONE_OUVIDO",
        "Web cam": "WEBCAM",
    }

    def edu_cell(room: dict, header: str) -> str:
        if header == "Sala":
            return room["room_name"]
        if header == "Nome resp.":
            return room["who"]
        if header == "CPU":
            return "OK"  # existe máquina cadastrada para a sala

        if header == "Horas lâmpada projetor":
            v = room.get("lamp_hours", None)
            return str(v) if v is not None else "Não aplica"

        code = EDU_MAP.get(header)
        if not code:
            return ""  # item ainda não controlado no sistema

        if code not in room["applicable"]:
            return "Não aplica"
        return "OK" if room["present"].get(code, False) else "Não tem"

    def section_sort_key(room: dict):
        name = room["room_name"]
        up = (name or "").upper()
        m = re.search(r"(\d+)", up)
        grade = int(m.group(1)) if m else 999
        return (grade, (name or "").lower())

    # Agrupa para as seções
    groups = {
        "Ensino Médio": [],
        "Ensino Fundamental II": [],
        "Ensino Fundamental I": [],
        "Ensino Infantil": [],
        "Salas Compartilhadas": [],
    }
    for r in rooms_agg:
        groups[_room_group(r["room_name"])].append(r)
    for k in groups:
        groups[k].sort(key=section_sort_key)

    intervals = {
        "Ensino Médio": "Intervalos - 08:30 às 08:50 / 11:05 às 11:25",
        "Ensino Fundamental II": "Intervalos - 08:30 às 08:50 / 11:05 às 11:25",
        "Ensino Fundamental I": "Intervalos - 09:15 às 09:35",
        "Ensino Infantil": "Intervalos - 09:15 às 09:35 / 15:15 às 15:35",
        "Salas Compartilhadas": None,
    }

    def write_edu_section(ws, start_row: int, section_title: str, interval_line: str | None, rows: list[dict]) -> int:
        # título (mescla B..U)
        title = f"Controle de equipamentos da sala - {section_title} - {start_ab} à {end_ab}".strip()
        ws.cell(start_row, EDU_COLS_START).value = title
        ws.cell(start_row, EDU_COLS_START).font = title_font
        ws.cell(start_row, EDU_COLS_START).alignment = center
        ws.merge_cells(start_row=start_row, start_column=EDU_COLS_START, end_row=start_row, end_column=EDU_COLS_END)

        # faixa azul do título
        t = ws.cell(start_row, EDU_COLS_START)
        t.fill = title_fill
        t.font = title_font
        ws.row_dimensions[start_row].height = 22

        # linha de intervalos (opcional)
        if interval_line:
            ws.cell(start_row + 1, EDU_COLS_START).value = interval_line
            ws.cell(start_row + 1, EDU_COLS_START).alignment = center
            ws.merge_cells(
                start_row=start_row + 1,
                start_column=EDU_COLS_START,
                end_row=start_row + 1,
                end_column=EDU_COLS_END,
            )

            # faixa laranja do intervalo
            it = ws.cell(start_row + 1, EDU_COLS_START)
            it.fill = interval_fill
            it.font = interval_font
            ws.row_dimensions[start_row + 1].height = 20

        header_row = start_row + (2 if interval_line else 1)

        for i, h in enumerate(EDU_HEADERS):
            ws.cell(header_row, EDU_COLS_START + i).value = h

        r = header_row + 1
        for room in rows:
            for i, h in enumerate(EDU_HEADERS):
                ws.cell(r, EDU_COLS_START + i).value = edu_cell(room, h)
            r += 1

        end_row = max(r - 1, header_row)
        paint_range(
            ws,
            header_row,
            EDU_COLS_START,
            end_row,
            EDU_COLS_END,
            header_row=header_row,
            first_col_fill_col=EDU_COLS_START,
        )
        box_borders(ws, start_row, EDU_COLS_START, end_row, EDU_COLS_END)
        return end_row

    # ===== Aba 1: Informativos Salas (com seções) =====
    set_widths(ws_info, EDU_WIDTHS)

    cur = 2  # deixa a linha 1 vazia como no modelo
    for section_name in [
        "Ensino Médio",
        "Ensino Fundamental II",
        "Ensino Fundamental I",
        "Ensino Infantil",
        "Salas Compartilhadas",
    ]:
        end_row = write_edu_section(ws_info, cur, section_name, intervals.get(section_name), groups[section_name])
        cur = end_row + 3  # 2 linhas em branco

    ws_info.cell(cur, EDU_COLS_START).value = '"Não tem" - nessa sala não estão usando o recurso ou está faltando'
    ws_info.cell(cur + 1, EDU_COLS_START).value = '"Não aplica" - nessa sala não há o recurso'

    # ===== Aba 2: Informativo Administrativo =====
    set_widths(ws_admin, ADMIN_WIDTHS)

    ws_admin.cell(2, ADMIN_COLS_START).value = f"Controle de equipamentos dos computadores do administrativo - {start_c} à {end_c}".strip()
    ws_admin.cell(2, ADMIN_COLS_START).font = title_font
    ws_admin.cell(2, ADMIN_COLS_START).alignment = center
    ws_admin.merge_cells(start_row=2, start_column=ADMIN_COLS_START, end_row=2, end_column=ADMIN_COLS_END)

    # faixa azul do título
    ws_admin.cell(2, ADMIN_COLS_START).fill = title_fill
    ws_admin.cell(2, ADMIN_COLS_START).font = title_font
    ws_admin.row_dimensions[2].height = 22

    header_row = 3
    for i, h in enumerate(ADMIN_HEADERS):
        ws_admin.cell(header_row, ADMIN_COLS_START + i).value = h

    def admin_cell(m, header: str) -> str:
        if header == "Departamento":
            return m.room_name
        if header == "Hostname":
            return m.machine_name
        if header == "Usuário":
            return m.username
        if header == "Nome resp.":
            return (m.updated_by or m.created_by or "")
        if header == "CPU":
            return "OK"

        code = ADMIN_MAP.get(header)
        if not code:
            return ""

        present = _per_present_machine(m, code)

        # No modelo, headset do administrativo costuma ser "Não aplica" quando não existe
        if header == "Headset":
            return "OK" if present else "Não aplica"

        return "OK" if present else "Não tem"

    r = header_row + 1
    for m in machines_c:
        for i, h in enumerate(ADMIN_HEADERS):
            ws_admin.cell(r, ADMIN_COLS_START + i).value = admin_cell(m, h)
        r += 1

    end_row = max(r - 1, header_row)
    paint_range(
        ws_admin,
        header_row,
        ADMIN_COLS_START,
        end_row,
        ADMIN_COLS_END,
        header_row=header_row,
        first_col_fill_col=ADMIN_COLS_START,
    )
    box_borders(ws_admin, 2, ADMIN_COLS_START, end_row, ADMIN_COLS_END)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
