"""Pydantic-Schemas für strukturierte Claude-Antworten (Structured Outputs).

Die Beschreibungen (`description`) landen im JSON-Schema und helfen dem Modell,
die Felder richtig zu füllen.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Slot = Literal["fruehstueck", "mittag", "abend", "snack"]
Section = Literal[
    "Obst & Gemüse",
    "Brot & Backwaren",
    "Kühlregal",
    "Fleisch & Fisch",
    "Tiefkühl",
    "Trockenware",
    "Konserven & Gläser",
    "Gewürze, Öle & Soßen",
    "Getränke",
    "Süßes & Snacks",
    "Sonstiges",
]


class FoodEstimate(BaseModel):
    name: str = Field(description="Kurzer deutscher Name inkl. Zubereitung, z. B. 'Vollkornbrot' oder 'Kaffee mit Milch'")
    grams: float = Field(description="Geschätzte Menge in Gramm (Getränke: ml)")
    size_label: Literal["klein", "mittel", "gross"] = Field(description="Grobe Portionsgröße im Vergleich zu einer üblichen Portion")
    kcal: float = Field(description="Energie für die gesamte Menge in kcal")
    protein: float = Field(description="Protein für die gesamte Menge in g")
    carbs: float = Field(description="Kohlenhydrate für die gesamte Menge in g")
    fat: float = Field(description="Fett für die gesamte Menge in g")
    confidence: Literal["hoch", "mittel", "niedrig"]


class MealEstimate(BaseModel):
    items: list[FoodEstimate]
    meal_guess: Slot = Field(description="Wahrscheinlichste Mahlzeit")
    note: str = Field(description="Ein kurzer Satz zu wichtigen Annahmen (z. B. 'Käse als Gouda angenommen'), sonst leer")


class BarcodeDigits(BaseModel):
    digits: str = Field(description="Die Ziffern unter dem Barcode ohne Leerzeichen; leer, wenn nicht lesbar")


class Ingredient(BaseModel):
    name: str = Field(description="Einkaufsname, z. B. 'Haferflocken', 'Paprika rot'")
    qty: float
    unit: Literal["g", "ml", "Stk"]
    section: Section


class PlannedMeal(BaseModel):
    slot: Slot
    time: str = Field(description="Uhrzeit HH:MM passend zur Schicht")
    name: str
    kcal: float
    protein: float
    carbs: float
    fat: float
    ingredients: list[Ingredient] = Field(
        description="Zutaten für EINE Person. Beim Meal-Prep: am Kochtag alle Portionen, an den Folgetagen leer."
    )
    instructions: str = Field(description="1–3 kurze Sätze Zubereitung")
    prep: str = Field(description="'' oder z. B. 'Meal-Prep: für 3 Tage kochen' bzw. 'vorgekocht vom Sonntag'")


class PlannedDay(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    shift: str
    meals: list[PlannedMeal]


class WeekPlan(BaseModel):
    days: list[PlannedDay]
    prep_notes: str = Field(description="Hinweise zum Vorkochen, sonst leer")
    estimated_cost_eur: float = Field(description="Geschätzte Kosten des Wocheneinkaufs für eine Person")
    tips: str = Field(description="1–2 alltagstaugliche Tipps zum Plan")


class Recipe(BaseModel):
    name: str
    servings: int
    time_minutes: int
    kcal_per_serving: float
    protein: float
    carbs: float
    fat: float
    ingredients: list[Ingredient]
    steps: list[str]
    uses: list[str] = Field(description="Welche vorhandenen Zutaten verwertet werden")
    missing: list[str] = Field(description="Zutaten, die ggf. noch fehlen (Grundvorrat wie Salz/Öl nicht aufzählen)")
    note: str
