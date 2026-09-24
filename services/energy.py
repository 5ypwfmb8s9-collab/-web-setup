"""Aktuelles Kalorienziel ermitteln und wöchentlich fortschreiben.

Pro Kalenderwoche wird genau ein Ziel gespeichert (`energy_targets`). Beim ersten Öffnen
einer neuen Woche wird neu gerechnet – zunächst per Formel, sobald genug Daten da sind
adaptiv (siehe core/adaptive.py und docs/ALGORITHMUS.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from core import adaptive, budget, clock, nutrition, trend
from db import repo


@dataclass
class CurrentTarget:
    target_kcal: int
    tdee: int
    method: str  # formel | adaptiv
    confidence: float
    explanation: str
    macros: nutrition.Macros
    week_start: date


def _age(profile: dict, on: date) -> int:
    return on.year - (profile.get("birth_year") or 1990)


def _reference_weight(user_id: int, profile: dict, on: date) -> float:
    """Trendgewicht (geglättet) statt Tageswert – robuster gegen Wasser-Schwankungen."""
    rows = repo.list_weights(user_id, since=on - timedelta(days=60))
    if rows:
        points = trend.ema_series([(r["date"], r["weight_kg"]) for r in rows])
        return points[-1].trend
    latest = repo.latest_weight(user_id)
    return latest["weight_kg"] if latest else 70.0


def compute_week_target(user_id: int, profile: dict, week_start: date) -> dict:
    """Berechnet das Ziel für eine Woche (ohne zu speichern)."""
    weight = _reference_weight(user_id, profile, week_start)
    age = _age(profile, week_start)
    formula_tdee = nutrition.tdee_formula(profile["sex"], weight, profile["height_cm"], age, profile["activity"])

    previous = repo.target_for_week(user_id, week_start - timedelta(days=1))
    estimate = adaptive.estimate_tdee(
        weights=[(r["date"], r["weight_kg"]) for r in repo.list_weights(user_id, since=week_start - timedelta(days=60))],
        intakes={d: v["kcal"] for d, v in repo.daily_totals(user_id, week_start - timedelta(days=adaptive.WINDOW_DAYS), week_start - timedelta(days=1)).items()},
        window_end=week_start - timedelta(days=1),
        formula_tdee=formula_tdee,
        previous_tdee=previous["tdee"] if previous else None,
        bmr=nutrition.bmr_mifflin(profile["sex"], weight, profile["height_cm"], age),
        planned_targets=previous["target_kcal"] if previous else None,
        previous_method=previous["method"] if previous else None,
    )
    result = nutrition.safe_target(
        estimate.tdee,
        weight,
        profile["sex"],
        profile.get("goal") or "halten",
        profile.get("pace_kg_week") or 0.5,
        height_cm=profile["height_cm"],
        age=age,
    )
    explanation = estimate.explanation
    if result.notes:
        explanation += "\n\n" + " ".join(result.notes)
    return {
        "tdee": float(result.tdee),
        "target_kcal": float(result.target_kcal),
        "method": estimate.method,
        "confidence": estimate.confidence,
        "explanation": explanation,
    }


def ensure_current(user_id: int, profile: dict, on: date | None = None, force: bool = False) -> CurrentTarget:
    """Liefert das gültige Ziel der aktuellen Woche und rechnet bei Wochenwechsel neu."""
    on = on or clock.today()
    ws = clock.week_start(on)
    row = repo.target_for_week(user_id, ws)
    if force or row is None or row["week_start"] < ws:
        values = compute_week_target(user_id, profile, ws)
        repo.upsert_target(user_id, ws, **values)
        row = repo.target_for_week(user_id, ws)
    weight = _reference_weight(user_id, profile, on)
    macros = nutrition.macro_targets(row["target_kcal"], weight, profile.get("diet_type") or "ausgewogen", profile.get("goal_weight_kg"))
    return CurrentTarget(
        target_kcal=int(row["target_kcal"]),
        tdee=int(row["tdee"]),
        method=row["method"],
        confidence=float(row["confidence"] or 0),
        explanation=row["explanation"] or "",
        macros=macros,
        week_start=row["week_start"],
    )


def week_budget(user_id: int, profile: dict, on: date | None = None) -> tuple[CurrentTarget, budget.WeekBudget]:
    """Aktuelles Ziel plus flexible Verteilung über die Woche (inkl. Ausnahmetagen)."""
    on = on or clock.today()
    current = ensure_current(user_id, profile, on)
    week = clock.week_days(on)
    exceptions = {e["date"]: (e["planned_kcal"], e["note"] or "") for e in repo.list_exceptions(user_id, week[0], week[-1])}
    wb = budget.plan_week(week, current.target_kcal, nutrition.min_kcal(profile.get("sex") or "d"), exceptions, clock.today())
    return current, wb


def day_target(user_id: int, profile: dict, day: date) -> int:
    _, wb = week_budget(user_id, profile, day)
    entry = wb.for_day(day)
    return entry.target if entry else wb.base
