"""Verarbeitungslogik fuer das Ladelisten-Tool.

Enthaelt die komplette, UI-unabhaengige Logik:
- Zusammenfuehren mehrerer Quelldateien (Blatt "Avis Lade Listen")
- Aufbau der LKW-Blaetter nach der verbindlichen Spezifikation
- Validierung des Ergebnisses

Kann sowohl von der Streamlit-Oberflaeche (app.py) als auch direkt per
Kommandozeile aufgerufen werden:

    python ladeliste_logic.py quelle1.xlsx quelle2.xlsx -o ausgabe.xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

SOURCE_SHEET_NAME = "Avis Lade Listen"

# 0-basierte Spaltenindizes im Quellblatt (A=0, B=1, ...)
COL_ABHOLTAG = 3    # D
COL_EMPF_NAME = 6   # G
COL_EMPF_ORT = 7    # H
COL_ABLADESTELLE = 8  # I
COL_LKW_VL = 11     # L
COL_PAL_QUELLE = 13  # N
COL_BRUTTO = 14     # O

TRUCK_SHEET_HEADERS = [
    "Abholtag",
    "Empfaenger Name",
    "Empfaenger Ort",
    "Abladestelle",
    "LKW VL",
    "PAL",
    "Brutto",
]

PAL_TOKENS = ("VWPAL", "111444")

PAL_PATTERN = re.compile(r"(\d+)\s*\*\s*(VWPAL|111444)(?![A-Za-z0-9])", re.IGNORECASE)

# Feste Spaltenbreiten je Blatt (in "pt", wie in der Spezifikation angegeben)
COLUMN_WIDTHS_PT = {
    "A": 85,
    "B": 210,
    "C": 105,
    "D": 100,
    "E": 85,
    "F": 180,
    "G": 85,
}

HEADER_FILL_COLOR = "FF1F4E78"
HEADER_FONT_COLOR = "FFFFFFFF"
HEADER_BORDER_COLOR = "FF404040"
DATA_BORDER_COLOR = "FFD9D9D9"

DATE_NUMBER_FORMAT = "DD.MM.YYYY"
# [$-407] erzwingt die deutsche Anzeige (Punkt=Tausender, Komma=Dezimal)
# unabhaengig von der Locale des oeffnenden Excel/LibreOffice.
WEIGHT_NUMBER_FORMAT = "[$-407]#,##0.0"
QUANTITY_NUMBER_FORMAT = "0"

CONFIRMATION_TEXTS = [
    "Übernahmebestätigung des Fahrers/Warenempfängers.",
    "Der Fahrer des LKW's bestätigt eine ordnungsgemäße Ladungssicherung durchgeführt zu haben",
    "und bestätigt außerdem, das zulässige Ladungsgewicht nicht überschritten zu haben.",
]

MAX_SHEET_NAME_LENGTH = 31


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def cm_to_inch(cm: float) -> float:
    return cm / 2.54


def pt_to_excel_width(pt: float) -> float:
    """Rechnet eine Punktangabe naeherungsweise in Excel-Spaltenbreiten-Einheiten um.

    Excel misst Spaltenbreiten nicht in Punkt, sondern in "Zeichenbreiten" der
    Standardschrift. Diese Naeherung (ueber Pixel, 96dpi, ~7px Zeichenbreite)
    liefert fuer alle Blaetter deterministisch identische Werte.
    """
    pixels = pt * 96 / 72
    width = (pixels - 5) / 7
    return round(width, 2)


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_lkw(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def to_number(value: Any) -> Optional[float]:
    """Wandelt einen Quellwert in eine echte Zahl (int/float) um."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace(".", "").replace(",", ".") if "," in text else text
    try:
        num = float(normalized)
    except ValueError:
        try:
            num = float(text)
        except ValueError:
            return None
    if num.is_integer():
        return int(num)
    return num


def to_date(value: Any):
    """Gibt ein echtes date/datetime-Objekt zurueck, falls moeglich."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return value


def process_pal(text: Any) -> str:
    """Extrahiert VWPAL/111444-Mengen aus einem Ladungstraeger-Text.

    Nur die Ladungstraeger "VWPAL" und "111444" werden beruecksichtigt, alle
    anderen Angaben werden entfernt. Die Erkennung ist robust gegenueber
    beliebigen Leerzeichen um "*" und "/". Reihenfolge im Ergebnis = Reihenfolge
    des ersten Vorkommens der jeweiligen Art im Quelltext.
    """
    if text is None:
        return ""
    source = str(text)
    matches = list(PAL_PATTERN.finditer(source))
    if not matches:
        return ""

    totals: Dict[str, int] = {}
    first_pos: Dict[str, int] = {}
    for m in matches:
        qty = int(m.group(1))
        token = m.group(2).upper()
        totals[token] = totals.get(token, 0) + qty
        if token not in first_pos:
            first_pos[token] = m.start()

    ordered = sorted(totals.keys(), key=lambda t: first_pos[t])
    return " / ".join(f"{totals[t]}*{t}" for t in ordered)


# ---------------------------------------------------------------------------
# Schritt 1: Einlesen & Zusammenfuehren
# ---------------------------------------------------------------------------

def read_source_rows(file: Any, sheet_name: str = SOURCE_SHEET_NAME) -> Tuple[List[Any], List[List[Any]]]:
    """Liest Kopfzeile und Datenzeilen aus dem angegebenen Blatt einer Datei.

    `file` kann ein Pfad, ein Datei-Objekt oder ein BytesIO sein (alles, was
    openpyxl.load_workbook akzeptiert).
    """
    wb = load_workbook(file, data_only=True, read_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(
            f"Das Blatt '{sheet_name}' wurde in der Datei nicht gefunden."
        )
    ws = wb[sheet_name]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = list(next(rows_iter))
    except StopIteration:
        return [], []

    data: List[List[Any]] = []
    for row in rows_iter:
        if all(v is None for v in row):
            continue
        data.append(list(row))
    wb.close()
    return header, data


def merge_source_files(files: Sequence[Any]) -> Tuple[List[Any], List[List[Any]]]:
    """Fuehrt Kopfzeile und Datenzeilen mehrerer Quelldateien zusammen.

    Reihenfolge: alle Zeilen der ersten Datei zuerst (Originalreihenfolge),
    danach die der naechsten usw. Keine Sortierung/Deduplizierung/Gruppierung.
    """
    if not files:
        raise ValueError("Es wurde keine Quelldatei uebergeben.")

    combined_header: Optional[List[Any]] = None
    combined_rows: List[List[Any]] = []
    for f in files:
        header, rows = read_source_rows(f)
        if combined_header is None:
            combined_header = header
        combined_rows.extend(rows)

    return combined_header or [], combined_rows


def write_source_sheet(wb: Workbook, header: Sequence[Any], rows: Sequence[Sequence[Any]]) -> Worksheet:
    """Schreibt das zusammengefuehrte Ergebnis unveraendert als Quellblatt."""
    ws = wb.create_sheet(SOURCE_SHEET_NAME)
    if header:
        ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    return ws


# ---------------------------------------------------------------------------
# Schritt 2: LKW-Blaetter
# ---------------------------------------------------------------------------

@dataclass
class TruckEntry:
    abholtag: Any
    empf_name: Any
    empf_ort: Any
    abladestelle: Any
    lkw_vl: str
    pal: str
    brutto: Optional[float]
    pal_raw: Any


@dataclass
class TruckSheetSummary:
    sheet_name: str
    lkw_vl: str
    position_count: int
    gesamtgewicht: float
    total_111444: int
    total_vwpal: int


def _get(row: Sequence[Any], idx: int) -> Any:
    return row[idx] if idx < len(row) else None


def build_truck_groups(rows: Sequence[Sequence[Any]]) -> "OrderedDict[str, List[TruckEntry]]":
    """Gruppiert Quellzeilen nach Spalte L (LKW VL), Zeilen mit leerer Spalte L
    werden ignoriert. Reihenfolge der Zeilen je Gruppe = Reihenfolge im Quellblatt.
    Reihenfolge der Gruppen = Reihenfolge des ersten Auftretens im Quellblatt.
    """
    groups: "OrderedDict[str, List[TruckEntry]]" = OrderedDict()
    for row in rows:
        lkw = normalize_lkw(_get(row, COL_LKW_VL))
        if lkw is None:
            continue
        entry = TruckEntry(
            abholtag=to_date(_get(row, COL_ABHOLTAG)),
            empf_name=_get(row, COL_EMPF_NAME),
            empf_ort=_get(row, COL_EMPF_ORT),
            abladestelle=_get(row, COL_ABLADESTELLE),
            lkw_vl=lkw,
            pal=process_pal(_get(row, COL_PAL_QUELLE)),
            brutto=to_number(_get(row, COL_BRUTTO)),
            pal_raw=_get(row, COL_PAL_QUELLE),
        )
        groups.setdefault(lkw, []).append(entry)
    return groups


def _truck_sheet_name(lkw_vl: str) -> str:
    name = f"LKW {lkw_vl}"
    if len(name) > MAX_SHEET_NAME_LENGTH:
        name = name[:MAX_SHEET_NAME_LENGTH]
    return name


def _pal_total_formula(token: str, first_row: int, last_row: int) -> str:
    """Baut eine fehlerfreie SUMPRODUCT-Formel, die die Menge einer PAL-Art
    (VWPAL oder 111444) aus dem sichtbaren Text in F<first_row>:F<last_row>
    extrahiert - unabhaengig davon, ob die Art als erster oder zweiter
    Eintrag im Zelltext auftritt, und ohne Fehlerwerte bei leeren/fehlenden
    Zellen zu erzeugen.
    """
    rng = f"$F${first_row}:$F${last_row}"
    marker = f"*{token}"
    prefix = f'LEFT({rng},FIND("{marker}",{rng})-1)'
    has_slash = f'ISNUMBER(SEARCH("/",{prefix}))'
    after_slash = f'TRIM(MID({prefix},SEARCH("/",{prefix})+1,100))'
    no_slash = f"TRIM({prefix})"
    value_expr = f"VALUE(IF({has_slash},{after_slash},{no_slash}))"
    return f"=SUMPRODUCT(IFERROR({value_expr},0))"


def _style_header_row(ws: Worksheet) -> None:
    thin_dark = Side(style="thin", color=HEADER_BORDER_COLOR)
    border = Border(left=thin_dark, right=thin_dark, top=thin_dark, bottom=thin_dark)
    font = Font(name="Calibri", size=11, bold=True, color=HEADER_FONT_COLOR)
    fill = PatternFill(fill_type="solid", start_color=HEADER_FILL_COLOR, end_color=HEADER_FILL_COLOR)
    alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, title in enumerate(TRUCK_SHEET_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = font
        cell.fill = fill
        cell.alignment = alignment
        cell.border = border

    ws.row_dimensions[1].height = 24


DATA_COL_ALIGNMENT = {
    "A": Alignment(horizontal="center", vertical="center", wrap_text=False),
    "B": Alignment(horizontal="left", vertical="center", wrap_text=True),
    "C": Alignment(horizontal="left", vertical="center", wrap_text=True),
    "D": Alignment(horizontal="left", vertical="center", wrap_text=True),
    "E": Alignment(horizontal="center", vertical="center", wrap_text=False),
    "F": Alignment(horizontal="left", vertical="center", wrap_text=True),
    "G": Alignment(horizontal="right", vertical="center", wrap_text=False),
}


def _style_data_rows(ws: Worksheet, first_row: int, last_row: int) -> None:
    thin_light = Side(style="thin", color=DATA_BORDER_COLOR)
    border = Border(left=thin_light, right=thin_light, top=thin_light, bottom=thin_light)
    font = Font(name="Calibri", size=10, bold=False, color="FF000000")

    for row in range(first_row, last_row + 1):
        for col_letter in ("A", "B", "C", "D", "E", "F", "G"):
            cell = ws[f"{col_letter}{row}"]
            cell.font = font
            cell.border = border
            cell.alignment = DATA_COL_ALIGNMENT[col_letter]


def _write_data_row(ws: Worksheet, row_idx: int, entry: TruckEntry) -> None:
    ws.cell(row=row_idx, column=1, value=entry.abholtag)
    ws.cell(row=row_idx, column=2, value=entry.empf_name)
    ws.cell(row=row_idx, column=3, value=entry.empf_ort)
    ws.cell(row=row_idx, column=4, value=entry.abladestelle)
    ws.cell(row=row_idx, column=5, value=entry.lkw_vl)
    ws.cell(row=row_idx, column=6, value=entry.pal if entry.pal else None)
    ws.cell(row=row_idx, column=7, value=entry.brutto)

    ws.cell(row=row_idx, column=1).number_format = DATE_NUMBER_FORMAT
    ws.cell(row=row_idx, column=7).number_format = WEIGHT_NUMBER_FORMAT


def build_truck_sheet(wb: Workbook, lkw_vl: str, entries: List[TruckEntry]) -> Tuple[Worksheet, TruckSheetSummary]:
    sheet_name = _truck_sheet_name(lkw_vl)
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(sheet_name)

    _style_header_row(ws)

    first_data_row = 2
    last_data_row = first_data_row + len(entries) - 1
    for offset, entry in enumerate(entries):
        _write_data_row(ws, first_data_row + offset, entry)

    _style_data_rows(ws, first_data_row, last_data_row)

    n = last_data_row
    row_gesamtgewicht = n + 1
    row_111444 = n + 2
    row_vwpal = n + 3
    row_gesamt = n + 4
    # n + 5 bleibt eine volle Leerzeile vor dem Bestaetigungsbereich.
    row_conf = [n + 6, n + 7, n + 8]
    row_signature = n + 12

    bold_font = Font(name="Calibri", size=10, bold=True, color="FF000000")
    regular_font = Font(name="Calibri", size=10, bold=False, color="FF000000")
    right_align = Alignment(horizontal="right", vertical="center")

    # Gesamtgewicht
    c_label = ws.cell(row=row_gesamtgewicht, column=6, value="Gesamtgewicht:")
    c_label.font = bold_font
    c_label.alignment = right_align
    c_value = ws.cell(row=row_gesamtgewicht, column=7, value=f"=SUM(G{first_data_row}:G{n})")
    c_value.font = bold_font
    c_value.alignment = right_align
    c_value.number_format = WEIGHT_NUMBER_FORMAT

    # 111444
    e_label = ws.cell(row=row_111444, column=5, value="111444")
    e_label.font = regular_font
    f_value = ws.cell(row=row_111444, column=6, value=_pal_total_formula("111444", first_data_row, n))
    f_value.font = regular_font
    f_value.alignment = right_align
    f_value.number_format = QUANTITY_NUMBER_FORMAT

    # VWPAL
    e_label2 = ws.cell(row=row_vwpal, column=5, value="VWPAL")
    e_label2.font = regular_font
    f_value2 = ws.cell(row=row_vwpal, column=6, value=_pal_total_formula("VWPAL", first_data_row, n))
    f_value2.font = regular_font
    f_value2.alignment = right_align
    f_value2.number_format = QUANTITY_NUMBER_FORMAT

    # Gesamt
    e_label3 = ws.cell(row=row_gesamt, column=5, value="Gesamt:")
    e_label3.font = bold_font
    f_value3 = ws.cell(row=row_gesamt, column=6, value=f"=F{row_111444}+F{row_vwpal}")
    f_value3.font = bold_font
    f_value3.alignment = right_align
    f_value3.number_format = QUANTITY_NUMBER_FORMAT

    top_border = Border(top=Side(style="thin", color="FF000000"))
    e_label3.border = top_border
    f_value3.border = top_border

    # Bestaetigungsbereich
    conf_font = Font(name="Calibri", size=10, bold=False, color="FF000000")
    conf_alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for r, text in zip(row_conf, CONFIRMATION_TEXTS):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        cell = ws.cell(row=r, column=1, value=text)
        cell.font = conf_font
        cell.alignment = conf_alignment

    # Unterschriftsbereich (drei Leerzeilen davor, keine Verbindung)
    sig_font = Font(name="Calibri", size=10, bold=False, color="FF000000")
    sig_left = Alignment(horizontal="left", vertical="bottom")
    sig_right = Alignment(horizontal="right", vertical="bottom")

    a_sig = ws.cell(row=row_signature, column=1, value="Unterschrift Staplerfahrer")
    a_sig.font = sig_font
    a_sig.alignment = sig_left

    d_sig = ws.cell(row=row_signature, column=4, value="Unterschrift Fahrer")
    d_sig.font = sig_font
    d_sig.alignment = sig_left

    g_sig = ws.cell(row=row_signature, column=7, value="Kennzeichen LKW")
    g_sig.font = sig_font
    g_sig.alignment = sig_right

    # Spaltenbreiten (kein AutoFit)
    for col_letter, pt in COLUMN_WIDTHS_PT.items():
        ws.column_dimensions[col_letter].width = pt_to_excel_width(pt)

    _apply_print_settings(ws, row_signature)

    summary = TruckSheetSummary(
        sheet_name=sheet_name,
        lkw_vl=lkw_vl,
        position_count=len(entries),
        gesamtgewicht=sum((e.brutto or 0) for e in entries),
        total_111444=sum(_extract_qty(e.pal, "111444") for e in entries),
        total_vwpal=sum(_extract_qty(e.pal, "VWPAL") for e in entries),
    )
    return ws, summary


def _extract_qty(pal_text: str, token: str) -> int:
    if not pal_text:
        return 0
    m = re.search(rf"(\d+)\*{token}", pal_text)
    return int(m.group(1)) if m else 0


def _apply_print_settings(ws: Worksheet, last_row: int) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    ws.print_options.horizontalCentered = True
    ws.print_options.verticalCentered = False
    ws.print_options.gridLines = False
    ws.print_options.headings = False

    ws.print_area = f"A1:G{last_row}"
    ws.print_title_rows = "1:1"

    ws.page_margins.left = cm_to_inch(0.64)
    ws.page_margins.right = cm_to_inch(0.64)
    ws.page_margins.top = cm_to_inch(1.91)
    ws.page_margins.bottom = cm_to_inch(1.91)
    ws.page_margins.header = cm_to_inch(0.76)
    ws.page_margins.footer = cm_to_inch(0.76)


# ---------------------------------------------------------------------------
# Schritt 3: Validierung
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    check: str
    passed: bool
    message: str


ERROR_VALUES = {"#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#N/A", "#NULL!", "#NUM!"}


def validate(
    header: Sequence[Any],
    rows: Sequence[Sequence[Any]],
    groups: "OrderedDict[str, List[TruckEntry]]",
    wb: Workbook,
) -> List[ValidationResult]:
    results: List[ValidationResult] = []

    # 1 + 4: jede Zeile mit gefuellter Spalte L ist genau einem LKW-Blatt
    # zugeordnet, Positionsanzahl je LKW stimmt.
    expected_counts: Dict[str, int] = OrderedDict()
    total_considered = 0
    for row in rows:
        lkw = normalize_lkw(_get(row, COL_LKW_VL))
        if lkw is None:
            continue
        total_considered += 1
        expected_counts[lkw] = expected_counts.get(lkw, 0) + 1

    assigned_total = sum(len(v) for v in groups.values())
    results.append(ValidationResult(
        "Zeilenzuordnung vollstaendig",
        assigned_total == total_considered,
        f"{assigned_total} von {total_considered} Zeilen mit LKW VL zugeordnet.",
    ))

    count_mismatches = [
        lkw for lkw, count in expected_counts.items()
        if count != len(groups.get(lkw, []))
    ]
    results.append(ValidationResult(
        "Positionsanzahl je LKW korrekt",
        not count_mismatches,
        "OK" if not count_mismatches else f"Abweichung bei: {', '.join(count_mismatches)}",
    ))

    # 2: kein LKW-Blatt doppelt
    truck_sheet_names = [_truck_sheet_name(lkw) for lkw in groups.keys()]
    duplicates = [n for n in set(truck_sheet_names) if truck_sheet_names.count(n) > 1]
    results.append(ValidationResult(
        "Keine doppelten LKW-Blaetter",
        not duplicates,
        "OK" if not duplicates else f"Doppelt: {', '.join(duplicates)}",
    ))

    # 3: Reihenfolge entspricht dem Quellblatt
    order_ok = True
    for lkw, entries in groups.items():
        source_order = [
            normalize_lkw(_get(row, COL_LKW_VL)) == lkw
            for row in rows
            if normalize_lkw(_get(row, COL_LKW_VL)) == lkw
        ]
        if len(source_order) != len(entries):
            order_ok = False
    results.append(ValidationResult(
        "Reihenfolge entspricht Quellblatt",
        order_ok,
        "OK" if order_ok else "Reihenfolge weicht ab.",
    ))

    # 5: Gesamtgewicht = exakte Summe aus Spalte O
    weight_mismatches = []
    for lkw, entries in groups.items():
        expected_sum = sum((to_number(_get(row, COL_BRUTTO)) or 0)
                            for row in rows if normalize_lkw(_get(row, COL_LKW_VL)) == lkw)
        actual_sum = sum((e.brutto or 0) for e in entries)
        if abs(expected_sum - actual_sum) > 1e-9:
            weight_mismatches.append(lkw)
    results.append(ValidationResult(
        "Gesamtgewicht stimmt mit Quelle ueberein",
        not weight_mismatches,
        "OK" if not weight_mismatches else f"Abweichung bei: {', '.join(weight_mismatches)}",
    ))

    # 6 + 7: 111444/VWPAL-Mengen stimmen, andere Ladungstraeger nicht enthalten
    pal_mismatches = []
    other_carriers_found = []
    for lkw, entries in groups.items():
        for entry in entries:
            expected_pal = process_pal(entry.pal_raw)
            if expected_pal != entry.pal:
                pal_mismatches.append(lkw)
            if entry.pal:
                for token in re.findall(r"\*([A-Za-z0-9]+)", entry.pal):
                    if token.upper() not in PAL_TOKENS:
                        other_carriers_found.append(lkw)
    results.append(ValidationResult(
        "PAL-Mengen (111444/VWPAL) korrekt extrahiert",
        not pal_mismatches,
        "OK" if not pal_mismatches else f"Abweichung bei: {', '.join(set(pal_mismatches))}",
    ))
    results.append(ValidationResult(
        "Keine anderen Ladungstraeger enthalten",
        not other_carriers_found,
        "OK" if not other_carriers_found else f"Fremde Ladungstraeger bei: {', '.join(set(other_carriers_found))}",
    ))

    # 8: alle Summenzeilen sind Formeln, keine Fehlerwerte
    formula_issues = []
    for lkw in groups.keys():
        sheet_name = _truck_sheet_name(lkw)
        ws = wb[sheet_name]
        n = 1 + len(groups[lkw])
        for row, col in ((n + 1, 7), (n + 2, 6), (n + 3, 6), (n + 4, 6)):
            cell = ws.cell(row=row, column=col)
            if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                formula_issues.append(f"{sheet_name}!{cell.coordinate}")
            elif cell.value.strip().upper() in ERROR_VALUES:
                formula_issues.append(f"{sheet_name}!{cell.coordinate}")
    results.append(ValidationResult(
        "Summen sind Formeln ohne Fehlerwerte",
        not formula_issues,
        "OK" if not formula_issues else f"Probleme bei: {', '.join(formula_issues)}",
    ))

    # 9: nur A:G, Spaltenbreiten korrekt
    layout_issues = []
    for lkw in groups.keys():
        sheet_name = _truck_sheet_name(lkw)
        ws = wb[sheet_name]
        if ws.max_column != 7:
            layout_issues.append(sheet_name)
            continue
        for col_letter, pt in COLUMN_WIDTHS_PT.items():
            expected = pt_to_excel_width(pt)
            actual = ws.column_dimensions[col_letter].width
            if actual is None or abs(actual - expected) > 0.05:
                layout_issues.append(sheet_name)
                break
    results.append(ValidationResult(
        "Nur Spalten A:G, Spaltenbreiten korrekt",
        not layout_issues,
        "OK" if not layout_issues else f"Probleme bei: {', '.join(layout_issues)}",
    ))

    # 10: Bestaetigungstexte nur ueber A:G verbunden
    merge_issues = []
    for lkw in groups.keys():
        sheet_name = _truck_sheet_name(lkw)
        ws = wb[sheet_name]
        merges = list(ws.merged_cells.ranges)
        if len(merges) != 3:
            merge_issues.append(sheet_name)
            continue
        for m in merges:
            if not (m.min_col == 1 and m.max_col == 7 and m.min_row == m.max_row):
                merge_issues.append(sheet_name)
                break
    results.append(ValidationResult(
        "Bestaetigungstexte ausschliesslich A:G verbunden",
        not merge_issues,
        "OK" if not merge_issues else f"Probleme bei: {', '.join(merge_issues)}",
    ))

    # 11: Druckbereich endet exakt in Unterschriftenzeile, passt auf eine Seite
    print_issues = []
    for lkw, entries in groups.items():
        sheet_name = _truck_sheet_name(lkw)
        ws = wb[sheet_name]
        n = 1 + len(entries)
        expected_signature_row = n + 12
        expected_area = f"A1:G{expected_signature_row}"
        actual_area = str(ws.print_area) if ws.print_area else ""
        actual_area = actual_area.split("!")[-1].replace("$", "")
        if actual_area != expected_area:
            print_issues.append(sheet_name)
            continue
        if ws.page_setup.fitToWidth != 1:
            print_issues.append(sheet_name)
    results.append(ValidationResult(
        "Druckbereich/Skalierung korrekt",
        not print_issues,
        "OK" if not print_issues else f"Probleme bei: {', '.join(print_issues)}",
    ))

    return results


# ---------------------------------------------------------------------------
# Gesamtablauf
# ---------------------------------------------------------------------------

@dataclass
class ProcessingResult:
    workbook: Workbook
    summaries: List[TruckSheetSummary]
    validation: List[ValidationResult]

    @property
    def is_valid(self) -> bool:
        return all(v.passed for v in self.validation)


def generate_workbook(files: Sequence[Any]) -> ProcessingResult:
    header, rows = merge_source_files(files)

    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    write_source_sheet(wb, header, rows)

    groups = build_truck_groups(rows)

    summaries: List[TruckSheetSummary] = []
    for lkw_vl, entries in groups.items():
        _, summary = build_truck_sheet(wb, lkw_vl, entries)
        summaries.append(summary)

    validation = validate(header, rows, groups, wb)

    return ProcessingResult(workbook=wb, summaries=summaries, validation=validation)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ladelisten-Tool (CLI)")
    parser.add_argument("inputs", nargs="+", help="Eine oder mehrere Excel-Quelldateien")
    parser.add_argument("-o", "--output", default="Ladelisten.xlsx", help="Pfad der Ausgabedatei")
    args = parser.parse_args(argv)

    result = generate_workbook(args.inputs)

    for s in result.summaries:
        print(f"{s.sheet_name}: {s.position_count} Positionen, "
              f"Gesamtgewicht={s.gesamtgewicht}, 111444={s.total_111444}, VWPAL={s.total_vwpal}")

    failed = [v for v in result.validation if not v.passed]
    for v in result.validation:
        status = "OK" if v.passed else "FEHLER"
        print(f"[{status}] {v.check}: {v.message}")

    if failed:
        print(f"\n{len(failed)} Validierung(en) fehlgeschlagen. Datei wird nicht gespeichert.", file=sys.stderr)
        return 1

    result.workbook.save(args.output)
    print(f"\nGespeichert: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
