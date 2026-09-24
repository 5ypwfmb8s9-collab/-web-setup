"""Gewichtstrend als zeitgewichteter exponentieller Durchschnitt (EMA).

Tageswerte schwanken durch Wasser, Salz, Verdauung usw. um bis zu ±1–2 kg. Der Trend glättet
das: Jeder neue Wert zieht den Trend nur um einen Bruchteil α in seine Richtung.

    trend_neu = trend_alt + a · (gewicht − trend_alt)
    a = 1 − (1 − α)^Δt      (Δt = Tage seit der letzten Messung, α = 0,1)

Durch den Exponenten Δt ist die Glättung unabhängig davon, ob täglich oder nur alle paar Tage
gewogen wird: Eine Messung nach 7 Tagen Pause zählt so viel wie 7 tägliche Messungen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

ALPHA = 0.1


@dataclass
class TrendPoint:
    date: date
    weight: float
    trend: float


def ema_series(points: list[tuple[date, float]], alpha: float = ALPHA) -> list[TrendPoint]:
    """Berechnet den Trend für eine Liste (Datum, Gewicht) – Reihenfolge egal."""
    ordered = sorted(points, key=lambda p: p[0])
    out: list[TrendPoint] = []
    for d, w in ordered:
        if not out:
            out.append(TrendPoint(d, w, w))
            continue
        prev = out[-1]
        dt = max((d - prev.date).days, 1)
        a = 1 - (1 - alpha) ** dt
        out.append(TrendPoint(d, w, prev.trend + a * (w - prev.trend)))
    return out


def weekly_rate(series: list[TrendPoint], days: int = 21) -> float | None:
    """Steigung des Trends in kg/Woche über die letzten `days` Tage (lineare Regression).

    Negativ = Abnahme. None, wenn zu wenige Messungen (< 4) oder < 7 Tage Spannweite.
    """
    if not series:
        return None
    end = series[-1].date
    window = [p for p in series if (end - p.date).days <= days]
    if len(window) < 4 or (window[-1].date - window[0].date).days < 7:
        return None
    xs = [(p.date - window[0].date).days for p in window]
    ys = [p.trend for p in window]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var
    return slope * 7


def change_over(series: list[TrendPoint], days: int) -> float | None:
    """Trendveränderung der letzten `days` Tage (kg)."""
    if len(series) < 2:
        return None
    end = series[-1]
    earlier = [p for p in series if (end.date - p.date).days >= days]
    if not earlier:
        return None
    return end.trend - earlier[-1].trend
