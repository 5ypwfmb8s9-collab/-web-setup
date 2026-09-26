"""Muster im eigenen Essverhalten → Vorschläge wie „Wie letzten Dienstag?“.

Grundlage sind Mahlzeitengruppen (alles, was gemeinsam eingetragen wurde). Vorgeschlagen werden
Mahlzeiten desselben Slots, bevorzugt vom gleichen Wochentag, gewichtet nach Aktualität
und Häufigkeit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from core.clock import WEEKDAYS_DE


@dataclass
class Suggestion:
    title: str
    reason: str
    items: list[dict] = field(default_factory=list)
    kcal: float = 0.0
    score: float = 0.0


def _signature(items: list[dict]) -> str:
    return "|".join(sorted(i["name"].strip().lower() for i in items))


def group_meals(entries: list[dict]) -> list[dict]:
    """Fasst Tagebuch-Einträge zu Mahlzeiten (group_id) zusammen."""
    groups: dict[str, dict] = {}
    for e in entries:
        gid = e.get("group_id") or f"single-{e['id']}"
        g = groups.setdefault(gid, {"date": e["date"], "meal": e["meal"], "items": []})
        g["items"].append(e)
    return list(groups.values())


def suggest(entries: list[dict], today: date, meal: str, limit: int = 3) -> list[Suggestion]:
    """Vorschläge für `meal` am Tag `today` aus den Einträgen der letzten Wochen."""
    todays = {_signature(g["items"]) for g in group_meals([e for e in entries if e["date"] == today and e["meal"] == meal])}
    candidates: dict[str, Suggestion] = {}
    counts: dict[str, int] = defaultdict(int)
    for g in group_meals([e for e in entries if e["date"] < today and e["meal"] == meal]):
        sig = _signature(g["items"])
        if not sig or sig in todays:
            continue
        counts[sig] += 1
        days_ago = (today - g["date"]).days
        same_weekday = g["date"].weekday() == today.weekday()
        score = (3.0 if same_weekday else 1.0) / (1 + days_ago / 7)
        names = [i["name"] for i in g["items"]]
        title = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
        if same_weekday and days_ago <= 7:
            reason = f"Wie letzten {WEEKDAYS_DE[g['date'].weekday()]}?"
        elif days_ago == 1:
            reason = "Wie gestern?"
        else:
            reason = f"Vor {days_ago} Tagen"
        items = [{k: i.get(k) for k in ("name", "grams", "size_label", "kcal", "protein", "carbs", "fat", "food_id")} for i in g["items"]]
        prev = candidates.get(sig)
        if prev is None or score > prev.score:
            candidates[sig] = Suggestion(title, reason, items, sum(i["kcal"] or 0 for i in items), score)
    for sig, s in candidates.items():
        s.score *= 1 + 0.3 * (counts[sig] - 1)  # häufige Mahlzeiten nach oben
        if counts[sig] >= 3 and not s.reason.startswith("Wie letzten"):
            s.reason = f"Isst du oft ({counts[sig]}×)"
    return sorted(candidates.values(), key=lambda s: s.score, reverse=True)[:limit]
