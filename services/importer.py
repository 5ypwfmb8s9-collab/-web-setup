"""Import von Gewichts- und Aktivitätsdaten.

Eine Web-App kann nicht direkt auf Apple Health, Google Fit, Garmin & Co. zugreifen – aber
fast alle bieten einen Export an. Unterstützt werden:

* CSV-Dateien (Komma, Semikolon oder Tab; deutsche oder englische Spaltennamen; kg oder lbs)
  z. B. von Garmin Connect, Google Fit/Takeout, Withings, Fitbit, smarten Waagen oder Apps wie
  „Health Auto Export“.
* Apple-Health-`export.xml` (aus „Health → Profil → Alle Gesundheitsdaten exportieren“, entpackt):
  Körpergewicht, Schritte und aktive Energie.
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

LB_TO_KG = 0.45359237

DATE_COLS = ["date", "datum", "day", "tag", "time", "zeit", "timestamp", "startdate", "start", "date/time", "datum/uhrzeit", "start time", "startzeit"]
WEIGHT_COLS = ["weight", "gewicht", "körpergewicht", "body mass", "bodymass", "weight (kg)", "gewicht (kg)", "weight(kg)", "weight (lbs)", "weight (lb)", "masse"]
STEPS_COLS = ["steps", "schritte", "step count", "stepcount", "anzahl schritte"]
KCAL_COLS = ["active calories", "aktive kalorien", "active energy", "activeenergyburned", "kalorien", "calories", "kcal", "energy burned", "aktivitätskalorien", "calories burned"]
MIN_COLS = ["duration", "dauer", "minutes", "minuten", "move minutes", "aktive minuten", "active minutes"]
KIND_COLS = ["activity type", "aktivitätstyp", "type", "typ", "sport", "activity", "aktivität"]


@dataclass
class ImportResult:
    weights: list[tuple[date, float]] = field(default_factory=list)
    activities: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected: dict[str, str] = field(default_factory=dict)


def _find(columns: list[str], candidates: list[str]) -> str | None:
    lower = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for cand in candidates:  # Teiltreffer, z. B. „Weight (kg)“
        for lc, orig in lower.items():
            if cand in lc:
                return orig
    return None


def _number(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:  # 1.234,5 bzw. 1,234.5
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _integer(value) -> int | None:
    """Ganzzahl (z. B. Schritte) – Tausendertrennzeichen („10.050“, „10,050“) werden entfernt."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if re.fullmatch(r"\d+[.,]\d{1,2}", s):  # echte Dezimalzahl, z. B. „8123,0“
        s = re.split(r"[.,]", s)[0]
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


def _read_csv(data: bytes) -> pd.DataFrame:
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        sep = dialect.delimiter
    except csv.Error:
        sep = ";" if text.count(";") > text.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=str)


def _parse_dates(series: pd.Series) -> pd.Series:
    sample = " ".join(series.dropna().astype(str).head(20))
    dayfirst = bool(re.search(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}", sample)) or bool(re.search(r"\b(1[3-9]|2\d|3[01])/\d{1,2}/\d{4}", sample))
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=dayfirst, utc=True, format="mixed")
    return parsed.dt.tz_convert("Europe/Berlin").dt.date


def parse_csv(data: bytes) -> ImportResult:
    res = ImportResult()
    try:
        df = _read_csv(data)
    except Exception:  # noqa: BLE001
        res.warnings.append("Die Datei konnte nicht als CSV gelesen werden.")
        return res
    cols = list(df.columns)
    date_col = _find(cols, DATE_COLS)
    if not date_col:
        res.warnings.append("Keine Datumsspalte gefunden (erwartet z. B. „Datum“ oder „Date“).")
        return res
    dates = _parse_dates(df[date_col])
    res.detected["Datum"] = date_col

    weight_col = _find(cols, WEIGHT_COLS)
    if weight_col:
        res.detected["Gewicht"] = weight_col
        values = [_number(v) for v in df[weight_col]]
        is_lbs = "lb" in weight_col.lower() or any("lb" in str(v).lower() for v in df[weight_col].head(10))
        by_day: dict[date, float] = {}
        for d, v in zip(dates, values):
            if d is None or pd.isna(d) or v is None:
                continue
            kg = v * LB_TO_KG if is_lbs else v
            if 25 <= kg <= 350:
                by_day[d] = round(kg, 1)  # bei mehreren Messungen am Tag zählt die letzte
        res.weights = sorted(by_day.items())
        if is_lbs:
            res.warnings.append("Gewicht war in Pfund angegeben und wurde in kg umgerechnet.")

    steps_col, kcal_col = _find(cols, STEPS_COLS), _find(cols, KCAL_COLS)
    min_col, kind_col = _find(cols, MIN_COLS), _find(cols, KIND_COLS)
    if steps_col or kcal_col or min_col:
        for key, col in (("Schritte", steps_col), ("Aktive kcal", kcal_col), ("Minuten", min_col), ("Art", kind_col)):
            if col:
                res.detected[key] = col
        for i, d in enumerate(dates):
            if d is None or pd.isna(d):
                continue
            steps = _integer(df[steps_col].iloc[i]) if steps_col else None
            kcal = _number(df[kcal_col].iloc[i]) if kcal_col else None
            minutes = _number(df[min_col].iloc[i]) if min_col else None
            if not any((steps, kcal, minutes)):
                continue
            kind = str(df[kind_col].iloc[i]) if kind_col and pd.notna(df[kind_col].iloc[i]) else "Aktivität"
            res.activities.append({"date": d, "kind": kind[:80], "steps": int(steps) if steps else None,
                                   "kcal": kcal, "minutes": minutes, "source": "import"})
    if not res.weights and not res.activities:
        res.warnings.append("Keine Gewichts- oder Aktivitätsdaten erkannt. Enthält die Datei Spalten wie „Gewicht“ oder „Schritte“?")
    return res


def parse_apple_health_xml(data: bytes) -> ImportResult:
    """Liest Körpergewicht, Schritte und aktive Energie aus Apple-Health-export.xml."""
    res = ImportResult()
    weights: dict[date, float] = {}
    steps: dict[date, float] = defaultdict(float)
    kcal: dict[date, float] = defaultdict(float)
    try:
        for _, el in ET.iterparse(io.BytesIO(data), events=("end",)):
            if el.tag != "Record":
                el.clear()
                continue
            typ = el.get("type", "")
            raw_date = (el.get("startDate") or "")[:10]
            try:
                d = date.fromisoformat(raw_date)
                v = float(el.get("value", ""))
            except ValueError:
                el.clear()
                continue
            if typ == "HKQuantityTypeIdentifierBodyMass":
                unit = (el.get("unit") or "kg").lower()
                weights[d] = round(v * LB_TO_KG if unit.startswith("lb") else v, 1)
            elif typ == "HKQuantityTypeIdentifierStepCount":
                steps[d] += v
            elif typ == "HKQuantityTypeIdentifierActiveEnergyBurned":
                kcal[d] += v if (el.get("unit") or "kcal").lower() != "kj" else v / 4.184
            el.clear()
    except ET.ParseError:
        res.warnings.append("Die XML-Datei ist unvollständig oder beschädigt.")
    res.weights = sorted(weights.items())
    for d in sorted(set(steps) | set(kcal)):
        res.activities.append({"date": d, "kind": "Tagesaktivität (Apple Health)", "steps": int(steps[d]) if steps.get(d) else None,
                               "kcal": round(kcal[d]) if kcal.get(d) else None, "minutes": None, "source": "import"})
    res.detected = {"Quelle": "Apple Health export.xml"}
    if not res.weights and not res.activities:
        res.warnings.append("Keine Gewichts-, Schritt- oder Energiedaten gefunden.")
    return res


def parse(filename: str, data: bytes) -> ImportResult:
    if filename.lower().endswith(".xml"):
        return parse_apple_health_xml(data)
    return parse_csv(data)
