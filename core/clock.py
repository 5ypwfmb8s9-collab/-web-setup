"""Zeitfunktionen.

Streamlit Community Cloud läuft in UTC. Für ein Ernährungstagebuch zählt aber der
Kalendertag des Nutzers – deshalb rechnet KANO konsequent in Europe/Berlin.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")

WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WEEKDAYS_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def now() -> datetime:
    """Aktuelle Zeit in Europe/Berlin."""
    return datetime.now(TZ)


def today() -> date:
    """Heutiges Datum in Europe/Berlin."""
    return now().date()


def week_start(d: date) -> date:
    """Montag der Woche, in der `d` liegt."""
    return d - timedelta(days=d.weekday())


def week_days(d: date) -> list[date]:
    """Alle sieben Tage (Mo–So) der Woche von `d`."""
    start = week_start(d)
    return [start + timedelta(days=i) for i in range(7)]


def format_date_long(d: date) -> str:
    """z. B. „Dienstag, 24. September“."""
    return f"{WEEKDAYS_DE[d.weekday()]}, {d.day}. {MONTHS_DE[d.month - 1]}"


def format_date_short(d: date) -> str:
    """z. B. „Di 24.09.“."""
    return f"{WEEKDAYS_SHORT[d.weekday()]} {d.day:02d}.{d.month:02d}."


def greeting(at: datetime | None = None) -> str:
    """Tageszeitabhängige Begrüßung."""
    hour = (at or now()).hour
    if 5 <= hour < 11:
        return "Guten Morgen"
    if 11 <= hour < 17:
        return "Hallo"
    if 17 <= hour < 23:
        return "Guten Abend"
    return "Hallo"
