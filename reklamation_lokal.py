"""Lokale Erfassung von Ausfallfracht-/Storno-Reklamationen per Drag & Drop.

Alternative zum Power-Automate-Weg (siehe reklamation_logic.py /
REKLAMATIONEN_SETUP.md, weiterhin nutzbar falls gewuenscht): PDFs werden
manuell per Drag & Drop hochgeladen, landen als echte Datei im
PDF-Unterordner und werden als Zeile in einer Excel-Datei erfasst - beide
in einem frei waehlbaren Basisordner (z.B. einem SharePoint/OneDrive-
synchronisierten Ordner), kein Power-Automate/SharePoint-Setup noetig.

Excel-Spalten und Blattname folgen exakt der vom Nutzer vorgegebenen
Vorlage (VW_Reklamationen.xlsx, Blatt "Tabelle1"):
Eingangsdatum, Absender, Betreff, Dateiname_PDF, OneDrive_Pfad, Status,
Pruefdatum, Ergebnis, Bemerkung.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List

from openpyxl import Workbook, load_workbook

SHEET_NAME = "Tabelle1"
EXCEL_COLUMNS = [
    "Eingangsdatum",
    "Absender",
    "Betreff",
    "Dateiname_PDF",
    "OneDrive_Pfad",
    "Status",
    "Prüfdatum",
    "Ergebnis",
    "Bemerkung",
]
EXCEL_SPALTENBREITEN = [16, 28, 40, 18, 45, 16, 14, 16, 30]

PFAD_CONFIG_DATEI = ".reklamationen_basisordner.txt"
STANDARD_BASISORDNER = (
    r"C:\Users\okan.kocak\norm-fasteners.com.tr"
    r"\Norm Fasteners Germany - VWAI Projekt\VW_Reklamationen"
)
EXCEL_DATEINAME = "VW_Reklamationen.xlsx"
PDF_UNTERORDNER = "Rechnungen_PDF"

ABSENDER_AUSFALLFRACHT = "noreply@duvenbeck.de"
BETREFF_AUSFALLFRACHT = "Rechnung Ausfallfracht zu Frachtbrief"
ABSENDER_STORNO = "ausfallfrachten-herne@duvenbeck.de"
BETREFF_STORNO = "Storno Ausfallfracht zu Frachtbrief"

_DATUM_MUSTER = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def lade_gespeicherten_basisordner() -> str:
    """Liest den zuletzt gespeicherten Basisordner, falls vorhanden."""
    try:
        with open(PFAD_CONFIG_DATEI, "r", encoding="utf-8") as f:
            pfad = f.read().strip()
            if pfad:
                return pfad
    except FileNotFoundError:
        pass
    return STANDARD_BASISORDNER


def speichere_basisordner(pfad: str) -> None:
    """Merkt sich den Basisordner dauerhaft fuer kuenftige Programmstarts."""
    with open(PFAD_CONFIG_DATEI, "w", encoding="utf-8") as f:
        f.write(pfad.strip())


def excel_pfad(basisordner: str) -> str:
    return os.path.join(basisordner, EXCEL_DATEINAME)


def pdf_ordner(basisordner: str) -> str:
    return os.path.join(basisordner, PDF_UNTERORDNER)


def guess_eingangsdatum(dateiname: str) -> str:
    """Rät ein Datum (TT.MM.JJJJ) aus einem JJJJMMTT-Muster im Dateinamen,
    faellt sonst auf das heutige Datum zurueck."""
    match = _DATUM_MUSTER.search(dateiname)
    if match:
        jahr, monat, tag = match.groups()
        if 1 <= int(monat) <= 12 and 1 <= int(tag) <= 31:
            return f"{tag}.{monat}.{jahr}"
    return datetime.date.today().strftime("%d.%m.%Y")


def guess_absender_betreff(dateiname: str) -> Dict[str, str]:
    """Raet Absender/Betreff anhand des Dateinamens (Storno vs. Rechnung)."""
    if "storno" in dateiname.lower():
        return {"Absender": ABSENDER_STORNO, "Betreff": BETREFF_STORNO}
    return {"Absender": ABSENDER_AUSFALLFRACHT, "Betreff": BETREFF_AUSFALLFRACHT}


def _eindeutiger_dateiname(ziel_ordner: str, dateiname: str) -> str:
    """Haengt bei Namenskollision _1, _2, ... an, statt eine Datei zu ueberschreiben."""
    basis, endung = os.path.splitext(dateiname)
    kandidat = dateiname
    zaehler = 1
    while os.path.exists(os.path.join(ziel_ordner, kandidat)):
        kandidat = f"{basis}_{zaehler}{endung}"
        zaehler += 1
    return kandidat


def speichere_pdf(basisordner: str, dateiname: str, inhalt: bytes) -> str:
    """Speichert die PDF-Bytes im PDF-Unterordner und gibt den vollen Pfad zurueck."""
    ziel_ordner = pdf_ordner(basisordner)
    os.makedirs(ziel_ordner, exist_ok=True)
    eindeutiger_name = _eindeutiger_dateiname(ziel_ordner, dateiname)
    ziel_pfad = os.path.join(ziel_ordner, eindeutiger_name)
    with open(ziel_pfad, "wb") as f:
        f.write(inhalt)
    return ziel_pfad


def lade_excel(pfad: str) -> List[Dict[str, Any]]:
    """Liest bestehende Reklamationen aus der Excel-Datei (leer, falls keine existiert)."""
    if not pfad or not os.path.exists(pfad):
        return []

    wb = load_workbook(pfad)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    header = [cell.value for cell in ws[1]]

    rows: List[Dict[str, Any]] = []
    for raw_row in ws.iter_rows(min_row=2, values_only=True):
        if all(value is None for value in raw_row):
            continue
        entry = dict(zip(header, raw_row))
        rows.append({col: entry.get(col) or "" for col in EXCEL_COLUMNS})
    return rows


def speichere_excel(pfad: str, rows: List[Dict[str, Any]]) -> None:
    """Schreibt alle Reklamationen als Excel-Datei (ueberschreibt bestehende Datei)."""
    ordner = os.path.dirname(pfad)
    if ordner:
        os.makedirs(ordner, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    ws.append(EXCEL_COLUMNS)
    for row in rows:
        ws.append([row.get(col, "") for col in EXCEL_COLUMNS])

    for col_idx, width in enumerate(EXCEL_SPALTENBREITEN, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

    wb.save(pfad)
