"""Wochenplan: Auftrag für Claude zusammenstellen, Plan speichern, Einkaufsliste ableiten."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from core import clock, pricing, schedule, shopping
from core.meals import MEALS
from core.nutrition import DIET_TYPES
from db import repo
from services import ai, energy, schedule_service


class TablePriceProvider:
    """Preise aus der (editierbaren) Tabelle des Nutzers, sonst Standardwerte."""

    def prices(self, user_id: int) -> list[pricing.Price]:
        rows = repo.list_prices(user_id)
        if not rows:
            return list(pricing.DEFAULT_PRICES)
        return [pricing.Price(r["item"], r["unit"], r["pack_qty"], r["price_eur"], r["section"]) for r in rows]


# Hier später z. B. einen Angebots-Provider einsetzen
price_provider: pricing.PriceProvider = TablePriceProvider()


@dataclass
class PlanRequest:
    start: date
    days: int
    persons: int
    budget_eur: float | None  # Wochenbudget für alle Personen, None = kein Budget-Modus
    meal_prep: bool
    prep_day: date | None
    prep_portions: int
    prep_meal: str  # mittag | abend
    extra: str  # freie Wünsche


def build_brief(user_id: int, profile: dict, req: PlanRequest) -> tuple[str, dict]:
    """Erzeugt die Aufgabenbeschreibung für Claude und die gespeicherten Parameter."""
    shifts = schedule_service.shifts_between(user_id, profile, req.start, req.days)
    lines = [
        f"Erstelle einen Essensplan für {req.days} Tage ab {req.start.isoformat()} ({clock.WEEKDAYS_DE[req.start.weekday()]}).",
        f"Ernährungsform: {DIET_TYPES.get(profile.get('diet_type') or 'ausgewogen')}.",
        f"Nicht verwenden: {profile.get('dislikes') or 'keine Einschränkungen'}.",
        "Tage (Datum · Schicht · Tagesziel · Mahlzeitenzeiten):",
    ]
    for i in range(req.days):
        d = req.start + timedelta(days=i)
        target = energy.day_target(user_id, profile, d)
        shift = shifts[d]
        times = ", ".join(f"{MEALS[s]} {t.strftime('%H:%M')}" for s, t in sorted(schedule.meal_times(shift).items(), key=lambda kv: kv[1]))
        lines.append(f"- {d.isoformat()} ({clock.WEEKDAYS_SHORT[d.weekday()]}) · {schedule.SHIFTS[shift]} · {target} kcal · {times}")
    if any(s == "nacht" for s in shifts.values()):
        lines.append("Bei Nachtschicht: Hauptmahlzeit vor der Schicht, nachts leicht und gut verdaulich, danach nur kleiner Snack.")
    if req.meal_prep and req.prep_day:
        lines.append(
            f"Meal-Prep: Am {clock.WEEKDAYS_DE[req.prep_day.weekday()]} ({req.prep_day.isoformat()}) wird das "
            f"{MEALS[req.prep_meal]} für {req.prep_portions} Tage vorgekocht (ein Gericht, gut aufwärmbar, "
            f"{req.prep_portions} Portionen). Am Kochtag alle Zutaten für alle Portionen angeben und prep "
            f"'Meal-Prep: für {req.prep_portions} Tage kochen' setzen; an den Folgetagen dasselbe Gericht mit leerer "
            f"Zutatenliste und prep 'vorgekocht vom {clock.WEEKDAYS_DE[req.prep_day.weekday()]}'."
        )
    prices = price_provider.prices(user_id)
    if req.budget_eur:
        per_person = req.budget_eur / max(req.persons, 1) * req.days / 7
        lines.append(
            f"Budget-Modus: Der Einkauf für diesen Plan darf pro Person höchstens ca. {per_person:.2f} € kosten. "
            "Bevorzuge günstige Grundzutaten, saisonales Gemüse, TK-Gemüse, Hülsenfrüchte und Zutaten, die mehrfach "
            "verwendet werden. Orientiere dich an diesen Discounter-Preisen:\n" + pricing.compact_table(prices)
        )
    if req.extra.strip():
        lines.append(f"Wünsche: {req.extra.strip()}")
    params = {
        "start": req.start.isoformat(), "days": req.days, "persons": req.persons, "budget_eur": req.budget_eur,
        "meal_prep": req.meal_prep, "prep_day": req.prep_day.isoformat() if req.prep_day else None,
        "prep_portions": req.prep_portions, "prep_meal": req.prep_meal, "extra": req.extra,
    }
    return "\n".join(lines), params


def generate(user_id: int, profile: dict, req: PlanRequest) -> int:
    """Plan erzeugen, speichern und Einkaufsliste ableiten. Gibt die Plan-ID zurück."""
    brief, params = build_brief(user_id, profile, req)
    plan = ai.generate_week_plan(brief).model_dump()
    plan_id = repo.save_plan(user_id, clock.week_start(req.start), params, plan)
    rebuild_shopping(user_id, plan_id, plan, req.persons)
    return plan_id


def rebuild_shopping(user_id: int, plan_id: int, plan: dict, persons: int) -> None:
    repo.replace_shopping(user_id, plan_id, shopping.aggregate(plan, persons))


def cost(user_id: int, items: list[dict]) -> pricing.CostEstimate:
    return pricing.estimate(items, price_provider.prices(user_id))
