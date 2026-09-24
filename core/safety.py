"""Sicherheitsfunktionen: Warnzeichen erkennen und behutsam darauf hinweisen.

Alle Hinweise sind freundlich formuliert, nie alarmierend, nie rot – und sie ersetzen
keine Diagnose. Die Schwellen sind bewusst vorsichtig gewählt.
"""

from __future__ import annotations

import re
from datetime import date

from core import trend

LOW_INTAKE_KCAL = 800  # Tage darunter (mit Einträgen) gelten als sehr niedrig
LOW_INTAKE_DAYS = 3  # … wenn das an mind. 3 der letzten 7 Tage vorkommt

SUPPORT_HTML = (
    "Wenn Essen gerade viel Raum einnimmt oder sich belastend anfühlt, bist du damit nicht allein. "
    "Sprich gern mit deiner Hausärztin/deinem Hausarzt oder hol dir anonyme Beratung: "
    "<b>Infotelefon Essstörungen</b> des BIÖG (ehem. BZgA) 0221&nbsp;892031 · "
    "<b>TelefonSeelsorge</b> 0800&nbsp;111&nbsp;0&nbsp;111 (kostenfrei, rund um die Uhr)."
)

# Formulierungen, die auf problematisches Essverhalten hindeuten können (Kleinschreibung)
_WARNING_PATTERNS = [
    r"erbrech", r"übergeb", r"kotz", r"finger in den hals",
    r"abführ", r"entwässerungstablett",
    r"essanf[aä]ll", r"fressattack", r"fressanf[aä]ll", r"kontrollverlust", r"nicht aufhören (zu|mit) essen",
    r"(gar )?nichts (mehr )?(ge)?ess", r"tagelang nicht", r"hunger(n|e) mich", r"will nicht mehr essen",
    r"schäme mich .*ess", r"schuldgefühl", r"ekel(e)? mich", r"hasse meinen körper", r"bin (so )?fett",
    r"untergewicht", r"noch dünner", r"kalorien (ab|weg)trainieren", r"kompensier",
    r"essstörung", r"magersucht", r"bulimi", r"binge",
]
_WARNING_RE = re.compile("|".join(_WARNING_PATTERNS))


def warning_signs_in_text(text: str) -> bool:
    return bool(_WARNING_RE.search(text.lower()))


def rapid_loss_hint(weights: list[tuple[date, float]]) -> str | None:
    """Hinweis, wenn der Trend über 3 Wochen mehr als 1 % Körpergewicht pro Woche fällt."""
    series = trend.ema_series(weights)
    rate = trend.weekly_rate(series, days=21)
    if rate is None or not series:
        return None
    limit = series[-1].trend * 0.01
    if -rate > limit:
        return (
            f"Dein Gewicht sinkt gerade schneller als ~1 % pro Woche ({abs(rate):.1f} kg/Woche). ".replace(".", ",", 1)
            + "Das ist mehr, als langfristig gut tut – iss ruhig etwas mehr, besonders Protein und Gemüse. "
            "Wenn du dich schlapp fühlst oder das ungewollt passiert, sprich bitte mit deiner Ärztin/deinem Arzt."
        )
    return None


def low_intake_hint(daily_kcal: dict[date, float]) -> str | None:
    """Hinweis bei mehreren sehr niedrigen Tagen innerhalb einer Woche."""
    low = [d for d, k in daily_kcal.items() if 0 < k < LOW_INTAKE_KCAL]
    if len(low) >= LOW_INTAKE_DAYS:
        return (
            "An mehreren Tagen dieser Woche hast du sehr wenig eingetragen. Falls das stimmt: "
            "Dein Körper braucht verlässlich Energie – regelmäßige Mahlzeiten helfen auch gegen Heißhunger. "
            "Falls du einfach nicht alles eingetragen hast: alles gut! " + SUPPORT_HTML
        )
    return None
