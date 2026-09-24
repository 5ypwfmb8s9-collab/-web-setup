"""Lokale Mustererkennung – ohne KI, nachvollziehbar und datensparsam.

Die gefundenen Muster erscheinen direkt auf der Coach-Seite und fließen (als Text, nicht als
Rohdaten) in die Zusammenfassung für den KI-Coach ein.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

MIN_DAYS = 3  # Mindestanzahl Tage je Vergleichsgruppe


@dataclass
class Insight:
    key: str
    title: str
    text: str  # mit Zahlen
    text_plain: str  # ohne Kalorienzahlen (für „Zahlen ausblenden“)


def _fmt(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def lunch_vs_evening(meals: dict[date, dict[str, float]], low_lunch: float = 400) -> Insight | None:
    """Kleines Mittagessen → größerer Abend? (Abend = Abendessen + Snacks nach dem Mittag)"""
    low, normal = [], []
    for day, m in meals.items():
        if "abend" not in m:
            continue
        evening = m.get("abend", 0) + m.get("snack", 0)
        (low if m.get("mittag", 0) < low_lunch else normal).append(evening)
    if len(low) < MIN_DAYS or len(normal) < MIN_DAYS:
        return None
    diff = mean(low) - mean(normal)
    if diff < 150:
        return None
    return Insight(
        "mittag_abend",
        "Mittag & Abend hängen zusammen",
        f"An Tagen mit kleinem Mittagessen (unter {_fmt(low_lunch)} kcal) war dein Abend im Schnitt "
        f"{_fmt(diff)} kcal größer ({len(low)} vs. {len(normal)} Tage).",
        "An Tagen mit kleinem Mittagessen isst du abends meist deutlich mehr. Ein sättigendes Mittagessen "
        "könnte den Abend entspannter machen.",
    )


def breakfast_effect(meals: dict[date, dict[str, float]]) -> Insight | None:
    """Ohne Frühstück → mehr Snacks?"""
    without, with_ = [], []
    for day, m in meals.items():
        if not m:
            continue
        (with_ if m.get("fruehstueck", 0) > 0 else without).append(m.get("snack", 0))
    if len(without) < MIN_DAYS or len(with_) < MIN_DAYS:
        return None
    diff = mean(without) - mean(with_)
    if diff < 120:
        return None
    return Insight(
        "fruehstueck_snacks",
        "Frühstück & Snacks",
        f"Ohne Frühstück hast du im Schnitt {_fmt(diff)} kcal mehr gesnackt.",
        "An Tagen ohne Frühstück snackst du tendenziell mehr.",
    )


def weekend_shift(daily: dict[date, float]) -> Insight | None:
    weekday = [k for d, k in daily.items() if d.weekday() < 5 and k > 0]
    weekend = [k for d, k in daily.items() if d.weekday() >= 5 and k > 0]
    if len(weekday) < MIN_DAYS or len(weekend) < 2:
        return None
    diff = mean(weekend) - mean(weekday)
    if abs(diff) < 300:
        return None
    more = diff > 0
    return Insight(
        "wochenende",
        "Wochenende vs. Wochentage",
        f"Am Wochenende isst du im Schnitt {_fmt(abs(diff))} kcal {'mehr' if more else 'weniger'} als unter der Woche. "
        + ("Mit dem flexiblen Wochenbudget kannst du das bewusst einplanen." if more else ""),
        f"Am Wochenende isst du spürbar {'mehr' if more else 'weniger'} als unter der Woche"
        + (" – das lässt sich im flexiblen Wochenbudget einplanen." if more else "."),
    )


def sleep_effect(daily: dict[date, float], sleep: dict[date, float], hunger: dict[date, float]) -> Insight | None:
    """Kurzer Schlaf → mehr Hunger / mehr Essen am selben Tag?"""
    short = [d for d, h in sleep.items() if h and h < 6.5]
    good = [d for d, h in sleep.items() if h and h >= 7]
    short_k = [daily[d] for d in short if daily.get(d)]
    good_k = [daily[d] for d in good if daily.get(d)]
    if len(short_k) >= MIN_DAYS and len(good_k) >= MIN_DAYS:
        diff = mean(short_k) - mean(good_k)
        if diff >= 150:
            return Insight(
                "schlaf",
                "Schlaf & Appetit",
                f"Nach kurzen Nächten (unter 6,5 h) hast du im Schnitt {_fmt(diff)} kcal mehr gegessen.",
                "Nach kurzen Nächten hast du mehr Appetit – ganz normal. Mehr Schlaf ist hier ein echter Hebel.",
            )
    short_h = [hunger[d] for d in short if hunger.get(d)]
    good_h = [hunger[d] for d in good if hunger.get(d)]
    if len(short_h) >= MIN_DAYS and len(good_h) >= MIN_DAYS and mean(short_h) - mean(good_h) >= 1.5:
        text = "Nach kurzen Nächten bewertest du deinen Hunger deutlich höher."
        return Insight("schlaf_hunger", "Schlaf & Hunger", text, text)
    return None


def consistency(daily: dict[date, float], today: date, days: int = 14) -> Insight | None:
    logged = sum(1 for i in range(1, days + 1) if daily.get(today - timedelta(days=i), 0) > 0)
    if logged >= days - 2:
        text = f"Du hast an {logged} der letzten {days} Tage getrackt – eine richtig gute Datengrundlage."
        return Insight("konstanz", "Dranbleiben", text, text)
    return None


def all_insights(
    meals: dict[date, dict[str, float]],
    sleep: dict[date, float],
    hunger: dict[date, float],
    today: date,
) -> list[Insight]:
    daily = {d: sum(m.values()) for d, m in meals.items()}
    found = [
        lunch_vs_evening(meals),
        breakfast_effect(meals),
        weekend_shift(daily),
        sleep_effect(daily, sleep, hunger),
        consistency(daily, today),
    ]
    return [i for i in found if i]
