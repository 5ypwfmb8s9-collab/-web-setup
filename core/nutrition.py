"""Energiebedarf, Kalorienziel und Makronährstoffe.

Grundlage ist die Mifflin-St-Jeor-Formel für den Grundumsatz (BMR), multipliziert mit
einem Aktivitätsfaktor (PAL). Daraus ergibt sich der Gesamtumsatz (TDEE), von dem je nach
Ziel ein Defizit abgezogen wird.

Sicherheitsregeln (hart, nicht abschaltbar):
* Das Kalorienziel fällt nie unter einen geschlechtsabhängigen Mindestwert.
* Das Defizit ist doppelt begrenzt: max. 1 % Körpergewicht pro Woche und max. 25 % des TDEE.
* Bei Untergewicht (BMI < 18,5) oder Minderjährigen wird kein Defizit angesetzt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KCAL_PER_KG = 7700  # Energiegehalt von ~1 kg Körpermasse (Fettgewebe) – übliche Näherung

SEX_LABELS = {"w": "weiblich", "m": "männlich", "d": "divers / keine Angabe"}

# Sicherer Mindestwert fürs Tagesziel (übliche Empfehlung ohne ärztliche Begleitung)
MIN_KCAL = {"w": 1200, "m": 1500, "d": 1350}

MAX_WEEKLY_LOSS_FRACTION = 0.01  # max. 1 % des Körpergewichts pro Woche
MAX_DEFICIT_FRACTION = 0.25  # max. 25 % unter dem Gesamtumsatz
GAIN_SURPLUS_KCAL = 250  # moderater Überschuss beim Muskelaufbau

ACTIVITY_LEVELS: dict[str, tuple[str, float, str]] = {
    "sitzend": ("Überwiegend sitzend", 1.2, "Bürojob, kaum Bewegung"),
    "leicht": ("Leicht aktiv", 1.375, "Bürojob + 1–3× Sport oder viel zu Fuß"),
    "maessig": ("Mäßig aktiv", 1.55, "Stehender Job oder 3–5× Sport pro Woche"),
    "aktiv": ("Sehr aktiv", 1.725, "Körperliche Arbeit oder 6–7× Sport"),
    "extrem": ("Extrem aktiv", 1.9, "Schwere körperliche Arbeit + Training"),
}

GOALS = {
    "abnehmen": "Abnehmen",
    "halten": "Gewicht halten",
    "aufbauen": "Muskeln aufbauen",
}

# Tempo in kg pro Woche
PACES: dict[str, tuple[str, float]] = {
    "sanft": ("Sanft (≈ 0,25 kg/Woche)", 0.25),
    "normal": ("Normal (≈ 0,5 kg/Woche)", 0.5),
    "zuegig": ("Zügig (≈ 0,75 kg/Woche)", 0.75),
}

DIET_TYPES = {
    "ausgewogen": "Ausgewogen",
    "high_protein": "High Protein",
    "low_carb": "Low Carb",
    "vegetarisch": "Vegetarisch",
    "vegan": "Vegan",
    "pescetarisch": "Pescetarisch",
}


def bmi(weight_kg: float, height_cm: float) -> float:
    """Body-Mass-Index."""
    h = height_cm / 100
    return weight_kg / (h * h)


def bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Grundumsatz nach Mifflin-St-Jeor (1990).

    Männer: 10·kg + 6,25·cm − 5·Jahre + 5
    Frauen: 10·kg + 6,25·cm − 5·Jahre − 161
    Divers/keine Angabe: Mittelwert beider Konstanten (−78).
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    offset = {"m": 5, "w": -161}.get(sex, -78)
    return base + offset


def activity_factor(level: str) -> float:
    return ACTIVITY_LEVELS.get(level, ACTIVITY_LEVELS["leicht"])[1]


def tdee_formula(sex: str, weight_kg: float, height_cm: float, age: int, activity: str) -> float:
    """Gesamtumsatz = Grundumsatz × Aktivitätsfaktor."""
    return bmr_mifflin(sex, weight_kg, height_cm, age) * activity_factor(activity)


def min_kcal(sex: str) -> int:
    return MIN_KCAL.get(sex, MIN_KCAL["d"])


def max_daily_deficit(weight_kg: float, tdee: float) -> float:
    """Größtes erlaubtes Tagesdefizit (das kleinere der beiden Limits)."""
    by_weight = weight_kg * MAX_WEEKLY_LOSS_FRACTION * KCAL_PER_KG / 7
    by_tdee = tdee * MAX_DEFICIT_FRACTION
    return min(by_weight, by_tdee)


@dataclass
class TargetResult:
    """Ergebnis der Zielberechnung inklusive nachvollziehbarer Hinweise."""

    target_kcal: int
    tdee: int
    deficit: int  # positiv = Defizit, negativ = Überschuss
    floor: int
    capped: bool = False
    notes: list[str] = field(default_factory=list)


def safe_target(
    tdee: float,
    weight_kg: float,
    sex: str,
    goal: str,
    pace_kg_week: float,
    *,
    height_cm: float | None = None,
    age: int | None = None,
) -> TargetResult:
    """Berechnet das Tagesziel aus dem Gesamtumsatz – mit allen Sicherheitsgrenzen."""
    floor = min_kcal(sex)
    notes: list[str] = []
    capped = False

    if goal == "abnehmen":
        blocked = False
        if age is not None and age < 18:
            notes.append("Unter 18 Jahren setzt KANO kein Kaloriendefizit an – Ziel ist „Gewicht halten“.")
            blocked = True
        if height_cm and bmi(weight_kg, height_cm) < 18.5:
            notes.append("Dein BMI liegt unter 18,5 – KANO plant deshalb kein Defizit.")
            blocked = True
        if blocked:
            deficit = 0.0
        else:
            wanted = pace_kg_week * KCAL_PER_KG / 7
            limit = max_daily_deficit(weight_kg, tdee)
            deficit = min(wanted, limit)
            if deficit < wanted - 1:
                capped = True
                notes.append(
                    "Das gewünschte Tempo wurde auf ein sicheres Maß begrenzt "
                    "(max. 1 % Körpergewicht pro Woche bzw. 25 % unter deinem Bedarf)."
                )
    elif goal == "aufbauen":
        deficit = -GAIN_SURPLUS_KCAL
    else:
        deficit = 0.0

    target = tdee - deficit
    if target < floor:
        target = floor
        capped = True
        notes.append(f"Dein Ziel liegt beim sicheren Mindestwert von {floor} kcal.")

    target = int(round(target / 10) * 10)
    return TargetResult(
        target_kcal=target,
        tdee=int(round(tdee)),
        deficit=int(round(tdee - target)),
        floor=floor,
        capped=capped,
        notes=notes,
    )


@dataclass
class Macros:
    protein_g: int
    carbs_g: int
    fat_g: int


def macro_targets(target_kcal: float, weight_kg: float, diet_type: str, goal_weight_kg: float | None = None) -> Macros:
    """Makronährstoff-Ziele.

    * Protein: 1,6 g/kg (High Protein: 2,0 g/kg) bezogen auf das Referenzgewicht – bei
      Abnehmzielen das Mittel aus aktuellem und Zielgewicht, damit Menschen mit viel
      Körpergewicht keine unrealistisch hohen Proteinmengen bekommen.
    * Fett: 30 % der Energie (Low Carb: 40 %), mindestens 0,6 g/kg.
    * Kohlenhydrate: der Rest (Low Carb: max. 25 % der Energie, Rest geht in Fett).
    """
    ref = weight_kg if not goal_weight_kg else (weight_kg + goal_weight_kg) / 2
    per_kg = 2.0 if diet_type == "high_protein" else 1.6
    protein = ref * per_kg
    # Protein nicht über 35 % der Energie
    protein = min(protein, target_kcal * 0.35 / 4)

    fat_share = 0.40 if diet_type == "low_carb" else 0.30
    fat = max(target_kcal * fat_share / 9, weight_kg * 0.6)

    carbs = (target_kcal - protein * 4 - fat * 9) / 4
    if diet_type == "low_carb":
        max_carbs = target_kcal * 0.25 / 4
        if carbs > max_carbs:
            fat += (carbs - max_carbs) * 4 / 9
            carbs = max_carbs
    carbs = max(carbs, 0)
    return Macros(protein_g=int(round(protein)), carbs_g=int(round(carbs)), fat_g=int(round(fat)))


def initial_target_from_profile(profile: dict, weight_kg: float, age: int) -> TargetResult:
    """Startwert fürs Onboarding bzw. solange noch keine adaptiven Daten vorliegen."""
    tdee = tdee_formula(profile["sex"], weight_kg, profile["height_cm"], age, profile["activity"])
    return safe_target(
        tdee,
        weight_kg,
        profile["sex"],
        profile["goal"],
        profile.get("pace_kg_week") or 0.5,
        height_cm=profile["height_cm"],
        age=age,
    )


def goal_weight_issues(goal: str, height_cm: float, weight_kg: float, goal_weight_kg: float | None) -> list[str]:
    """Freundliche Hinweise zu unrealistischen oder ungesunden Zielgewichten."""
    issues: list[str] = []
    if not goal_weight_kg:
        return issues
    if bmi(goal_weight_kg, height_cm) < 18.5:
        issues.append(
            "Dieses Zielgewicht läge im Untergewicht (BMI unter 18,5). "
            "Bitte wähle ein höheres Ziel – oder sprich vorher mit deiner Ärztin/deinem Arzt."
        )
    if goal == "abnehmen" and goal_weight_kg >= weight_kg:
        issues.append("Für „Abnehmen“ sollte das Zielgewicht unter deinem aktuellen Gewicht liegen.")
    return issues
