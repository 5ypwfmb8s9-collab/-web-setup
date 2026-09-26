"""Mahlzeiten-Slots und Zuordnung nach Uhrzeit."""

from __future__ import annotations

from datetime import datetime, time

MEALS = {
    "fruehstueck": "Frühstück",
    "mittag": "Mittagessen",
    "abend": "Abendessen",
    "snack": "Snacks",
}
MEAL_ORDER = list(MEALS)


def guess_meal(at: datetime, meal_times: dict[str, time] | None = None) -> str:
    """Wahrscheinlichste Mahlzeit zur Uhrzeit.

    Mit `meal_times` (aus der Schichtplanung) wird die zeitlich nächste Hauptmahlzeit gewählt,
    sonst gelten feste Zeitfenster.
    """
    if meal_times:
        minutes = at.hour * 60 + at.minute

        def dist(t: time) -> int:
            d = abs(t.hour * 60 + t.minute - minutes)
            return min(d, 1440 - d)

        best = min(meal_times.items(), key=lambda kv: dist(kv[1]))
        return best[0] if dist(best[1]) <= 90 else "snack"
    t = at.time()
    if t < time(4, 0):
        return "snack"
    if t < time(10, 30):
        return "fruehstueck"
    if t < time(14, 30):
        return "mittag"
    if t < time(17, 0):
        return "snack"
    if t < time(21, 30):
        return "abend"
    return "snack"

# Kurze Beschriftungen für Auswahlknöpfe auf dem Handy
MEALS_SHORT = {"fruehstueck": "Frühstück", "mittag": "Mittag", "abend": "Abend", "snack": "Snack"}
