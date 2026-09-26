"""Datenexport: vollständiger CSV-Export (ZIP) und PDF-Bericht für Ernährungsberatung/Arztpraxis."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from statistics import mean

from core import clock, trend
from core.meals import MEALS
from core.nutrition import DIET_TYPES, GOALS
from db import repo

# --------------------------------------------------------------------------- CSV


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def csv_zip(user_id: int) -> bytes:
    """Alle Daten als ZIP mit einer CSV je Tabelle (Semikolon, UTF-8 mit BOM → öffnet sauber in Excel)."""
    data = repo.export_user_data(user_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, rows in data.items():
            out = io.StringIO()
            if rows:
                cols = [c for c in rows[0].keys() if c not in ("user_id", "password_hash")]
                w = csv.writer(out, delimiter=";")
                w.writerow(cols)
                for r in rows:
                    w.writerow([_cell(r.get(c)) for c in cols])
            zf.writestr(f"{name}.csv", "﻿" + out.getvalue())
        zf.writestr(
            "LIESMICH.txt",
            "KANO – Datenexport vom " + clock.today().strftime("%d.%m.%Y") + "\n\n"
            "Jede Datei enthält eine Tabelle deiner Daten (Trennzeichen: Semikolon, Dezimalzeichen: Komma).\n"
            "food_log = Ernährungstagebuch, weights = Gewicht, wellbeing = Wohlbefinden, strength = Kraftwerte,\n"
            "energy_targets = wöchentliche Zielberechnung, meal_plans = Wochenpläne, coach_messages = Coach-Chat.\n",
        )
    return buf.getvalue()


def diary_csv(user_id: int, start: date, end: date) -> bytes:
    """Ernährungstagebuch eines Zeitraums als einzelne CSV (für Beratung)."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Datum", "Mahlzeit", "Lebensmittel", "Menge (g)", "kcal", "Protein (g)", "Kohlenhydrate (g)", "Fett (g)"])
    for e in repo.get_entries(user_id, start, end):
        w.writerow([e["date"].strftime("%d.%m.%Y"), MEALS.get(e["meal"], e["meal"]), e["name"], _cell(e["grams"]),
                    _cell(e["kcal"]), _cell(e["protein"]), _cell(e["carbs"]), _cell(e["fat"])])
    return ("﻿" + out.getvalue()).encode("utf-8")


# --------------------------------------------------------------------------- PDF

_REPLACE = {"–": "-", "—": "-", "≈": "~", "·": "-", "„": '"', "“": '"', "”": '"', "’": "'", "…": "...", "★": "*", "→": "->"}
GRADIENT = [(0x28, 0x70, 0xEA), (0x7B, 0x61, 0xFF), (0xE3, 0x00, 0x8C), (0xFF, 0x8C, 0x00)]


def _t(text: object) -> str:
    """Text auf Latin-1 abbilden (Standardschrift des PDFs) – Umlaute bleiben erhalten."""
    s = str(text)
    for a, b in _REPLACE.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def _grad(t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t)) * (len(GRADIENT) - 1)
    i = min(int(t), len(GRADIENT) - 2)
    f = t - i
    return tuple(int(a + (b - a) * f) for a, b in zip(GRADIENT[i], GRADIENT[i + 1]))  # type: ignore[return-value]


def _report_class():
    """fpdf2 erst bei Bedarf laden – spart Startzeit der App."""
    from fpdf import FPDF

    class _Report(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 16)
            self.set_text_color(*GRADIENT[1])
            self.cell(0, 10, "KANO", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*GRADIENT[1])
            self.set_line_width(0.6)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)
            self.set_text_color(20, 20, 20)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 6, _t(f"Erstellt mit KANO am {clock.today().strftime('%d.%m.%Y')} - Seite {self.page_no()} - "
                               "Werte sind Selbstangaben bzw. Schätzungen, keine medizinische Diagnose."), align="C")

    return _Report


def _h(pdf, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _t(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)


def _kv(pdf, rows: list[tuple[str, str]]) -> None:
    pdf.set_font("Helvetica", "", 10)
    for k, v in rows:
        pdf.set_text_color(110, 110, 110)
        pdf.cell(55, 6, _t(k))
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 6, _t(v), new_x="LMARGIN", new_y="NEXT")


def _num(v: float | None, digits: int = 0) -> str:
    if v is None:
        return "-"
    return f"{v:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _weight_chart(pdf, series: list[trend.TrendPoint]) -> None:
    """Einfaches Liniendiagramm (Trend im Farbverlauf, Tageswerte als Punkte)."""
    x0, y0, w, h = pdf.l_margin, pdf.get_y() + 2, pdf.w - pdf.l_margin - pdf.r_margin, 45
    lo = min(min(p.weight for p in series), min(p.trend for p in series)) - 0.5
    hi = max(max(p.weight for p in series), max(p.trend for p in series)) + 0.5
    d0, d1 = series[0].date, series[-1].date
    span = max((d1 - d0).days, 1)

    def xy(d: date, v: float) -> tuple[float, float]:
        return x0 + (d - d0).days / span * w, y0 + h - (v - lo) / (hi - lo) * h

    pdf.set_draw_color(225, 225, 225)
    pdf.set_line_width(0.2)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(130, 130, 130)
    for i in range(4):
        v = lo + (hi - lo) * i / 3
        _, y = xy(d0, v)
        pdf.line(x0, y, x0 + w, y)
        pdf.set_xy(x0 - 12, y - 2)
        pdf.cell(10, 4, _num(v, 1), align="R")
    pdf.set_fill_color(170, 170, 170)
    for p in series:
        x, y = xy(p.date, p.weight)
        pdf.ellipse(x - 0.6, y - 0.6, 1.2, 1.2, style="F")
    pdf.set_line_width(0.9)
    for i in range(1, len(series)):
        pdf.set_draw_color(*_grad(i / max(len(series) - 1, 1)))
        pdf.line(*xy(series[i - 1].date, series[i - 1].trend), *xy(series[i].date, series[i].trend))
    pdf.set_xy(x0, y0 + h + 1)
    pdf.cell(w / 2, 4, d0.strftime("%d.%m.%Y"))
    pdf.cell(w / 2, 4, d1.strftime("%d.%m.%Y"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(20, 20, 20)
    pdf.ln(2)


def pdf_report(user_id: int, profile: dict, start: date, end: date) -> bytes:
    """Übersichtlicher Bericht zum Mitnehmen in die Beratung."""
    pdf = _report_class()(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 14, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _t(f"Ernährungsbericht {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"), new_x="LMARGIN", new_y="NEXT")

    age = end.year - (profile.get("birth_year") or end.year)
    _h(pdf, "Profil")
    _kv(pdf, [
        ("Name", profile.get("name") or "-"),
        ("Alter / Größe", f"{age} Jahre / {_num(profile.get('height_cm'))} cm"),
        ("Ziel", GOALS.get(profile.get("goal") or "halten", "-")),
        ("Ernährungsform", DIET_TYPES.get(profile.get("diet_type") or "ausgewogen", "-")),
        ("Abneigungen", profile.get("dislikes") or "-"),
    ])

    targets = [t for t in repo.list_targets(user_id) if t["week_start"] <= end]
    totals = repo.daily_totals(user_id, start, end)
    logged = [v for v in totals.values() if v["kcal"] > 0]
    _h(pdf, "Energie & Nährstoffe")
    rows = [("Getrackte Tage", f"{len(logged)} von {(end - start).days + 1}")]
    if logged:
        rows += [
            ("Ø Energie / Tag", f"{_num(mean(v['kcal'] for v in logged))} kcal"),
            ("Ø Protein / Tag", f"{_num(mean(v['protein'] or 0 for v in logged))} g"),
            ("Ø Kohlenhydrate / Tag", f"{_num(mean(v['carbs'] or 0 for v in logged))} g"),
            ("Ø Fett / Tag", f"{_num(mean(v['fat'] or 0 for v in logged))} g"),
        ]
    if targets:
        t = targets[-1]
        rows += [("Aktuelles Tagesziel", f"{_num(t['target_kcal'])} kcal"),
                 ("Geschätzter Verbrauch", f"{_num(t['tdee'])} kcal ({'adaptiv aus Daten' if t['method'] == 'adaptiv' else 'Formel'})")]
    _kv(pdf, rows)

    weights = repo.list_weights(user_id, since=start - timedelta(days=30))
    series = [p for p in trend.ema_series([(w["date"], w["weight_kg"]) for w in weights]) if start <= p.date <= end]
    if len(series) >= 2:
        _h(pdf, "Gewicht (Punkte: Messungen, Linie: geglätteter Trend)")
        rate = trend.weekly_rate(series)
        _kv(pdf, [
            ("Trend Anfang -> Ende", f"{_num(series[0].trend, 1)} kg -> {_num(series[-1].trend, 1)} kg"),
            ("Tempo (letzte 3 Wochen)", f"{_num(rate, 2)} kg/Woche" if rate is not None else "-"),
        ])
        _weight_chart(pdf, series)

    well = [w for w in repo.list_wellbeing(user_id, since=start) if w["date"] <= end]
    if well:
        def avg(k):
            vals = [w[k] for w in well if w.get(k) is not None]
            return mean(vals) if vals else None

        _h(pdf, "Wohlbefinden (Selbsteinschätzung 1-10)")
        _kv(pdf, [("Energie", _num(avg("energy"), 1)), ("Wohlbefinden", _num(avg("mood"), 1)),
                  ("Hunger", _num(avg("hunger"), 1)), ("Schlaf", f"{_num(avg('sleep_hours'), 1)} h, Qualität {_num(avg('sleep_quality'), 1)}")])

    if totals:
        _h(pdf, "Tagesübersicht")
        pdf.set_font("Helvetica", "B", 9)
        widths = [30, 28, 28, 34, 26, 28]
        for head, wdt in zip(["Datum", "kcal", "Protein g", "Kohlenhydrate g", "Fett g", "Einträge"], widths):
            pdf.cell(wdt, 6, _t(head), border="B")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for d in sorted(totals):
            v = totals[d]
            vals = [clock.format_date_short(d),
                    _num(v["kcal"]), _num(v["protein"]), _num(v["carbs"]), _num(v["fat"]), str(v["entries"])]
            for val, wdt in zip(vals, widths):
                pdf.cell(wdt, 5.5, _t(val))
            pdf.ln()

    out = pdf.output()
    return bytes(out)
