"""Tagesstruktur bei Schichtarbeit: Schichttyp → passende Mahlzeitenzeiten.

Die Zeiten orientieren sich an gängigen Empfehlungen für Schichtarbeit: Hauptmahlzeit vor
der Schicht, leichte Mahlzeit in der Pause, nachts eher kleine, gut verdauliche Portionen und
vor dem Schlafen nach der Nachtschicht nur ein kleiner Snack.
"""

from __future__ import annotations

from datetime import time

SHIFTS: dict[str, str] = {
    "frei": "Frei / Normal",
    "frueh": "Frühschicht (6–14 Uhr)",
    "spaet": "Spätschicht (14–22 Uhr)",
    "nacht": "Nachtschicht (22–6 Uhr)",
}
SHIFT_SHORT = {"frei": "Frei", "frueh": "Früh", "spaet": "Spät", "nacht": "Nacht"}

# Slot → Uhrzeit. Bei der Nachtschicht ist „abend“ die Mahlzeit in der Nacht.
MEAL_TIMES: dict[str, dict[str, time]] = {
    "frei": {"fruehstueck": time(8, 0), "mittag": time(12, 30), "snack": time(15, 30), "abend": time(18, 30)},
    "frueh": {"fruehstueck": time(5, 0), "snack": time(9, 30), "mittag": time(14, 30), "abend": time(18, 30)},
    "spaet": {"fruehstueck": time(9, 0), "mittag": time(13, 0), "snack": time(18, 0), "abend": time(22, 30)},
    "nacht": {"mittag": time(13, 0), "abend": time(19, 30), "snack": time(1, 30), "fruehstueck": time(6, 30)},
}

MEAL_HINTS: dict[str, str] = {
    "frei": "",
    "frueh": "Kleines Frühstück vor der Schicht, Hauptmahlzeit nach Feierabend.",
    "spaet": "Hauptmahlzeit mittags vor der Schicht, in der Pause etwas Leichtes.",
    "nacht": "Hauptmahlzeit vor der Schicht, nachts leicht essen, nach der Schicht nur ein kleiner Snack vor dem Schlafen.",
}


def meal_times(shift: str) -> dict[str, time]:
    return MEAL_TIMES.get(shift, MEAL_TIMES["frei"])


def shift_for_day(weekday: int, pattern: dict | None, overrides: dict | None = None, day=None) -> str:
    """Schicht eines Tages: Einzelfestlegung > Wochenmuster > „frei“."""
    if overrides and day in overrides:
        return overrides[day]
    if pattern:
        return pattern.get(str(weekday)) or pattern.get(weekday) or "frei"
    return "frei"
