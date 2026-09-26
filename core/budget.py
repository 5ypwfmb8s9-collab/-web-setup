"""Flexibles Wochenbudget.

Das Wochenbudget ist 7 × Tagesziel. Markiert man Ausnahmetage (Geburtstag, Essen gehen …)
mit einer geplanten Energiemenge, wird die Differenz gleichmäßig auf die *verbleibenden*
normalen Tage der Woche (ab heute) verteilt.

Leitplanken:
* Kein Tag fällt unter den sicheren Mindestwert.
* Ein Tag wird um höchstens 30 % gekürzt – lieber bleibt ein Rest übrig.
* Vergangene Tage werden nie nachträglich verändert, und tatsächliches Mehr-Essen wird
  bewusst NICHT „ausgeglichen“ (kein Kompensationsdruck). Nur geplante Ausnahmen zählen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

MAX_REDUCTION = 0.30
MAX_INCREASE = 0.30


@dataclass
class DayBudget:
    date: date
    target: int
    base: int
    exception: bool = False
    note: str = ""

    @property
    def delta(self) -> int:
        return self.target - self.base


@dataclass
class WeekBudget:
    days: list[DayBudget]
    base: int
    unallocated: int = 0
    notes: list[str] = field(default_factory=list)

    def for_day(self, d: date) -> DayBudget | None:
        return next((x for x in self.days if x.date == d), None)

    @property
    def total(self) -> int:
        return sum(d.target for d in self.days)


def plan_week(
    week: list[date],
    base_target: int,
    floor: int,
    exceptions: dict[date, tuple[float, str]],
    today: date,
) -> WeekBudget:
    days: list[DayBudget] = []
    extra = 0.0
    for d in week:
        if d in exceptions:
            planned, note = exceptions[d]
            days.append(DayBudget(d, int(round(planned)), base_target, True, note))
            extra += planned - base_target
        else:
            days.append(DayBudget(d, base_target, base_target))

    flexible = [x for x in days if not x.exception and x.date >= today]
    result = WeekBudget(days=days, base=base_target)
    if not extra or not flexible:
        if extra > 0 and not flexible:
            result.unallocated = int(round(extra))
        return result

    per_day = extra / len(flexible)
    if per_day > 0:
        cap = min(base_target * MAX_REDUCTION, max(0.0, base_target - floor))
        step = min(per_day, cap)
        for x in flexible:
            x.target = int(round(base_target - step))
    else:
        step = max(per_day, -base_target * MAX_INCREASE)
        for x in flexible:
            x.target = int(round(base_target - step))
    result.unallocated = int(round(extra - step * len(flexible)))
    if result.unallocated > 50:
        result.notes.append(
            f"Rund {result.unallocated} kcal lassen sich nicht sinnvoll auf die übrigen Tage verteilen – "
            "völlig okay. Eine Woche muss nicht perfekt aufgehen."
        )
    return result
