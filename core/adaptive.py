"""Adaptiver Energiebedarf.

Idee (Energiebilanz): Wer im Schnitt X kcal isst und dabei Y kg Körpermasse pro Tag verliert,
verbraucht tatsächlich ungefähr

    TDEE_beobachtet = Ø Energiezufuhr − (Δ Trendgewicht · 7700 kcal/kg) / Tage

Details, Grenzen und Begründung aller Konstanten: docs/ALGORITHMUS.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from core import trend
from core.nutrition import KCAL_PER_KG

WINDOW_DAYS = 28  # Betrachtungszeitraum
MIN_SPAN_DAYS = 14  # Mindestabstand zwischen erster und letzter Wägung im Fenster
MIN_LOGGED_DAYS = 10  # Mindestanzahl vollständig getrackter Tage
MIN_WEIGHINS = 4  # Mindestanzahl Wägungen im Fenster
MAX_WEEKLY_CHANGE = 150  # max. Änderung des TDEE pro Woche (kcal)
MAX_FIRST_CHANGE = 250  # max. Abweichung beim ersten Wechsel von Formel → adaptiv
INCOMPLETE_FRACTION = 0.5  # Tage unter 50 % des Ziels gelten als unvollständig getrackt
INCOMPLETE_MIN_KCAL = 700


@dataclass
class Estimate:
    tdee: float
    method: str  # formel | adaptiv
    confidence: float  # 0..1
    explanation: str
    details: dict = field(default_factory=dict)


def _fmt(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def estimate_tdee(
    *,
    weights: list[tuple[date, float]],
    intakes: dict[date, float],
    window_end: date,
    formula_tdee: float,
    previous_tdee: float | None,
    bmr: float,
    previous_method: str | None = None,
    planned_targets: float | None = None,
) -> Estimate:
    """Schätzt den tatsächlichen Gesamtumsatz aus Gewichtstrend und getrackter Energie."""
    window_start = window_end - timedelta(days=WINDOW_DAYS - 1)
    # Solange noch nie adaptiv gerechnet wurde, ist die (mit dem Gewicht mitwandernde) Formel die Basis.
    was_adaptive = bool(previous_tdee) and previous_method == "adaptiv"
    base = previous_tdee if was_adaptive else formula_tdee
    base_label = "letzte Schätzung" if was_adaptive else "Formel (Mifflin-St-Jeor)"

    # 1) Vollständig getrackte Tage im Fenster
    reference = planned_targets or formula_tdee * 0.8
    threshold = max(INCOMPLETE_MIN_KCAL, reference * INCOMPLETE_FRACTION)
    in_window = {d: k for d, k in intakes.items() if window_start <= d <= window_end and k and k > 0}
    logged = {d: k for d, k in in_window.items() if k >= threshold}
    skipped = len(in_window) - len(logged)

    # 2) Gewichtstrend im Fenster
    series = trend.ema_series(weights)
    in_range = [p for p in series if window_start <= p.date <= window_end]
    span = (in_range[-1].date - in_range[0].date).days if len(in_range) >= 2 else 0

    missing = []
    if len(logged) < MIN_LOGGED_DAYS:
        missing.append(f"mindestens {MIN_LOGGED_DAYS} vollständig getrackte Tage (bisher {len(logged)})")
    if len(in_range) < MIN_WEIGHINS or span < MIN_SPAN_DAYS:
        missing.append(f"mindestens {MIN_WEIGHINS} Wägungen über {MIN_SPAN_DAYS} Tage (bisher {len(in_range)} über {span} Tage)")

    if missing:
        tdee = base
        text = (
            f"Grundlage: {base_label} – {_fmt(tdee)} kcal/Tag. "
            "Für die adaptive Berechnung fehlen noch " + " und ".join(missing) + "."
        )
        return Estimate(tdee=tdee, method="adaptiv" if was_adaptive else "formel", confidence=0.0, explanation=text,
                        details={"logged_days": len(logged), "weighins": len(in_range), "span": span})

    # 3) Beobachteter Verbrauch
    mean_intake = sum(logged.values()) / len(logged)
    delta_kg = in_range[-1].trend - in_range[0].trend
    observed = mean_intake - delta_kg * KCAL_PER_KG / span

    # 4) Vertrauen: Anteil getrackter Tage und Länge der Messspanne
    coverage = len(logged) / WINDOW_DAYS
    confidence = max(0.0, min(1.0, coverage)) * min(1.0, span / 21)

    # 5) Gedämpfte Anpassung: je sicherer die Daten, desto stärker folgt die Schätzung
    k = 0.3 + 0.4 * confidence
    proposed = base + k * (observed - base)
    max_step = MAX_WEEKLY_CHANGE if was_adaptive else MAX_FIRST_CHANGE
    step = max(-max_step, min(max_step, proposed - base))
    tdee = base + step

    # 6) Plausibilitätsgrenzen
    tdee = max(bmr * 1.1, min(bmr * 2.4, tdee))

    direction = "verloren" if delta_kg < 0 else "zugenommen"
    delta_txt = f"{abs(delta_kg):.1f}".replace(".", ",")
    text = (
        f"In den letzten {WINDOW_DAYS} Tagen hast du an {len(logged)} Tagen vollständig getrackt "
        f"(Ø {_fmt(mean_intake)} kcal) und laut Trend {delta_txt} kg in {span} Tagen {direction}. "
        f"Daraus ergibt sich ein beobachteter Verbrauch von ≈ {_fmt(observed)} kcal/Tag. "
        f"Ausgehend von {base_label} ({_fmt(base)} kcal) wurde die Schätzung vorsichtig auf "
        f"{_fmt(tdee)} kcal angepasst (max. ±{max_step} kcal pro Woche)."
    )
    if skipped:
        text += f" {skipped} Tag(e) mit sehr wenig Einträgen wurden als unvollständig ignoriert."
    return Estimate(
        tdee=tdee,
        method="adaptiv",
        confidence=round(confidence, 2),
        explanation=text,
        details={
            "logged_days": len(logged),
            "weighins": len(in_range),
            "span": span,
            "mean_intake": mean_intake,
            "delta_kg": delta_kg,
            "observed": observed,
        },
    )
