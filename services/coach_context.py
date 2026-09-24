"""Zusammenfassung der Nutzerdaten für den KI-Coach.

Datensparsam: Es gehen nur verdichtete Kennzahlen und erkannte Muster an die KI – keine
E-Mail, kein Name, keine einzelnen Mahlzeiten-Einträge, kein Geburtsdatum (nur Altersdekade).
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from core import clock, insights, trend
from core.meals import MEALS
from core.nutrition import DIET_TYPES, GOALS
from db import repo
from services import energy

WINDOW = 28


def gather(user_id: int, profile: dict, today: date | None = None) -> tuple[str, list[insights.Insight]]:
    today = today or clock.today()
    start = today - timedelta(days=WINDOW)
    yesterday = today - timedelta(days=1)
    meals = repo.meal_totals(user_id, start, yesterday)
    well = repo.list_wellbeing(user_id, since=start)
    sleep = {w["date"]: w["sleep_hours"] for w in well if w.get("sleep_hours")}
    hunger = {w["date"]: w["hunger"] for w in well if w.get("hunger")}
    found = insights.all_insights(meals, sleep, hunger, today)

    current = energy.ensure_current(user_id, profile, today)
    daily = {d: sum(m.values()) for d, m in meals.items()}
    last14 = [daily[d] for d in daily if d >= today - timedelta(days=14)]
    lines = []
    age = today.year - (profile.get("birth_year") or 1990)
    sex = {"w": "Frau", "m": "Mann"}.get(profile.get("sex") or "", "Person")
    lines.append(
        f"Profil: {sex}, "
        f"{age // 10 * 10}–{age // 10 * 10 + 9} Jahre, Ziel: {GOALS.get(profile.get('goal') or 'halten')}, "
        f"Ernährungsform: {DIET_TYPES.get(profile.get('diet_type') or 'ausgewogen')}"
        + (f", mag nicht: {profile['dislikes']}" if profile.get("dislikes") else "")
    )
    if profile.get("care_flag"):
        lines.append("Wichtig: Nutzer hat angegeben, dass Schwangerschaft/Stillzeit, eine (frühere) Essstörung oder eine "
                     "ärztlich begleitete Ernährung zutrifft – kein Abnehm-Coaching, keine Defizit-Empfehlungen.")
    lines.append(f"Tagesziel: {current.target_kcal} kcal (Verbrauch geschätzt {current.tdee} kcal, Methode: {current.method}); "
                 f"Makroziele P {current.macros.protein_g} g / KH {current.macros.carbs_g} g / F {current.macros.fat_g} g")
    if last14:
        lines.append(f"Letzte 14 Tage: an {len(last14)} Tagen getrackt, Ø {int(mean(last14))} kcal pro getracktem Tag")
    totals = repo.daily_totals(user_id, today - timedelta(days=14), yesterday)
    if totals:
        prot = mean(v["protein"] or 0 for v in totals.values())
        lines.append(f"Ø Protein: {int(prot)} g/Tag")
    if meals:
        share = {}
        tot = sum(sum(m.values()) for m in meals.values()) or 1
        for slot in MEALS:
            share[slot] = sum(m.get(slot, 0) for m in meals.values()) / tot
        lines.append("Verteilung: " + ", ".join(f"{MEALS[s]} {int(v * 100)} %" for s, v in share.items()))
    weights = repo.list_weights(user_id, since=today - timedelta(days=60))
    if weights:
        series = trend.ema_series([(w["date"], w["weight_kg"]) for w in weights])
        rate = trend.weekly_rate(series)
        lines.append(f"Gewichtstrend: {series[-1].trend:.1f} kg" + (f", Tempo {rate:+.2f} kg/Woche" if rate is not None else ""))
    if well:
        def avg(key):
            vals = [w[key] for w in well if w.get(key) is not None]
            return round(mean(vals), 1) if vals else None

        parts = [f"{name} {avg(k)}/10" for k, name in (("energy", "Energie"), ("mood", "Wohlbefinden"), ("hunger", "Hunger"), ("sleep_quality", "Schlafqualität")) if avg(k) is not None]
        if avg("sleep_hours") is not None:
            parts.append(f"Schlaf {avg('sleep_hours')} h")
        lines.append("Wohlbefinden (Ø 4 Wochen): " + ", ".join(parts))
    strength = repo.list_strength(user_id)
    if strength:
        lines.append(f"Krafttraining: {len({s['date'] for s in strength if s['date'] >= start})} Trainingstage in 4 Wochen")
    week = clock.week_days(today)
    exc = repo.list_exceptions(user_id, week[0], week[-1])
    if exc:
        lines.append("Geplante Ausnahmetage diese Woche: " + ", ".join(f"{clock.WEEKDAYS_SHORT[e['date'].weekday()]} ({e['note'] or 'Ausnahme'})" for e in exc))
    if found:
        lines.append("Erkannte Muster: " + " | ".join(i.text for i in found))
    return "\n".join(lines), found
