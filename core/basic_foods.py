"""Eingebaute Grundnahrungsmittel mit Durchschnittswerten.

Dient als Offline-Basis für Suche und Ungefähr-Modus, falls Open Food Facts nicht erreichbar
ist oder ein unverpacktes Lebensmittel (Apfel, Kartoffeln …) gesucht wird.
Werte: typische Durchschnittswerte je 100 g (gerundet, Orientierung an gängigen Nährwerttabellen).
Portionsgrößen: (klein, mittel, groß) in Gramm bzw. Milliliter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasicFood:
    name: str
    kcal: float
    protein: float
    carbs: float
    fat: float
    portions: tuple[int, int, int]
    unit: str  # Beschreibung einer Portion, z. B. „Stück“, „Scheibe“, „Glas“
    section: str

    def as_food(self) -> dict:
        """Gleiche Struktur wie ein Eintrag aus der `foods`-Tabelle."""
        return {
            "id": None,
            "source": "basis",
            "barcode": None,
            "name": self.name,
            "brand": None,
            "kcal_100g": self.kcal,
            "protein_100g": self.protein,
            "carbs_100g": self.carbs,
            "fat_100g": self.fat,
            "serving_g": float(self.portions[1]),
            "portions": self.portions,
            "unit": self.unit,
        }


OG = "Obst & Gemüse"
BB = "Brot & Backwaren"
KR = "Kühlregal"
FF = "Fleisch & Fisch"
TW = "Trockenware"
KG = "Konserven & Gläser"
GO = "Gewürze, Öle & Soßen"
GT = "Getränke"
SN = "Süßes & Snacks"
TK = "Tiefkühl"
FE = "Fertiggerichte & Unterwegs"

_F = BasicFood

FOODS: list[BasicFood] = [
    # Obst & Gemüse
    _F("Apfel", 52, 0.3, 12, 0.2, (100, 150, 200), "Stück", OG),
    _F("Banane", 93, 1.1, 20, 0.2, (90, 120, 150), "Stück", OG),
    _F("Birne", 55, 0.4, 12.4, 0.3, (120, 170, 220), "Stück", OG),
    _F("Orange", 47, 0.9, 9, 0.2, (130, 180, 230), "Stück", OG),
    _F("Mandarine", 50, 0.7, 10, 0.3, (50, 70, 90), "Stück", OG),
    _F("Erdbeeren", 32, 0.7, 5.5, 0.3, (80, 150, 250), "Schale", OG),
    _F("Heidelbeeren", 57, 0.7, 11, 0.3, (50, 100, 150), "Handvoll", OG),
    _F("Weintrauben", 70, 0.7, 16, 0.3, (80, 125, 200), "Portion", OG),
    _F("Kiwi", 61, 1.1, 11, 0.5, (60, 80, 100), "Stück", OG),
    _F("Tomate", 18, 0.9, 3, 0.2, (60, 100, 150), "Stück", OG),
    _F("Gurke", 12, 0.6, 2, 0.1, (50, 100, 200), "Portion", OG),
    _F("Paprika", 31, 1, 5, 0.3, (80, 150, 200), "Stück", OG),
    _F("Karotte", 36, 0.9, 7, 0.2, (50, 80, 120), "Stück", OG),
    _F("Brokkoli", 34, 3, 3, 0.4, (100, 200, 300), "Portion", OG),
    _F("Blumenkohl", 25, 2, 2.5, 0.3, (100, 200, 300), "Portion", OG),
    _F("Zucchini", 19, 1.5, 2.2, 0.4, (100, 200, 300), "Portion", OG),
    _F("Spinat", 23, 2.9, 1, 0.4, (50, 100, 200), "Portion", OG),
    _F("Blattsalat", 15, 1.3, 1.5, 0.2, (40, 80, 120), "Schale", OG),
    _F("Kartoffeln (gekocht)", 72, 2, 15, 0.1, (100, 200, 300), "Portion", OG),
    _F("Süßkartoffel (gegart)", 86, 1.6, 20, 0.1, (100, 200, 300), "Portion", OG),
    _F("Zwiebel", 40, 1.1, 8, 0.1, (40, 80, 120), "Stück", OG),
    _F("Champignons", 22, 3, 0.5, 0.3, (60, 120, 200), "Portion", OG),
    _F("Avocado", 160, 2, 2, 15, (50, 80, 140), "Hälfte", OG),
    # Brot & Backwaren
    _F("Vollkornbrot", 216, 7.5, 38, 1.5, (40, 50, 65), "Scheibe", BB),
    _F("Mischbrot", 225, 6.5, 45, 1.2, (40, 50, 65), "Scheibe", BB),
    _F("Brötchen (Weizen)", 270, 9, 53, 1.5, (40, 55, 70), "Stück", BB),
    _F("Vollkornbrötchen", 240, 9, 42, 2.5, (50, 65, 80), "Stück", BB),
    _F("Toastbrot", 260, 8, 48, 3.5, (25, 30, 40), "Scheibe", BB),
    _F("Croissant", 406, 8, 45, 21, (40, 60, 80), "Stück", BB),
    _F("Knäckebrot", 340, 10, 60, 2, (10, 20, 30), "Scheibe", BB),
    _F("Brezel", 280, 8, 55, 2, (60, 85, 110), "Stück", BB),
    # Kühlregal
    _F("Milch 1,5 %", 47, 3.4, 4.8, 1.5, (150, 250, 350), "Glas", KR),
    _F("Milch 3,5 %", 64, 3.3, 4.8, 3.5, (150, 250, 350), "Glas", KR),
    _F("Haferdrink", 45, 0.8, 6.5, 1.5, (150, 250, 350), "Glas", KR),
    _F("Joghurt natur 3,5 %", 64, 3.8, 4.4, 3.5, (100, 150, 250), "Becher", KR),
    _F("Magerquark", 67, 12, 4, 0.3, (100, 250, 500), "Portion", KR),
    _F("Skyr natur", 63, 11, 4, 0.2, (100, 150, 250), "Becher", KR),
    _F("Hüttenkäse", 98, 12, 2.6, 4.3, (100, 200, 250), "Becher", KR),
    _F("Gouda", 356, 25, 0, 28, (20, 30, 50), "Scheibe", KR),
    _F("Emmentaler", 380, 28, 0, 30, (20, 30, 50), "Scheibe", KR),
    _F("Mozzarella", 250, 18, 1, 19, (60, 125, 200), "Kugel", KR),
    _F("Feta", 264, 17, 0, 21, (30, 60, 100), "Portion", KR),
    _F("Frischkäse", 250, 6, 3, 24, (15, 30, 50), "Portion", KR),
    _F("Butter", 741, 0.7, 0.6, 83, (5, 10, 20), "Portion", KR),
    _F("Ei", 137, 12, 1, 9.5, (55, 110, 165), "1/2/3 Eier", KR),
    _F("Kochschinken", 110, 18, 1, 4, (20, 40, 60), "Scheiben", KR),
    _F("Salami", 380, 21, 1, 33, (15, 30, 50), "Scheiben", KR),
    _F("Tofu natur", 120, 13, 2, 7, (80, 150, 200), "Portion", KR),
    _F("Hummus", 280, 7, 13, 21, (30, 50, 80), "Portion", KR),
    # Fleisch & Fisch
    _F("Hähnchenbrust (gegart)", 150, 30, 0, 3, (100, 150, 200), "Portion", FF),
    _F("Hackfleisch gemischt (gegart)", 250, 20, 0, 19, (100, 150, 200), "Portion", FF),
    _F("Rindersteak (gegart)", 180, 28, 0, 7, (150, 200, 300), "Stück", FF),
    _F("Schweineschnitzel paniert", 250, 20, 12, 13, (120, 170, 220), "Stück", FF),
    _F("Lachs (gegart)", 200, 22, 0, 12, (100, 150, 200), "Filet", FF),
    _F("Thunfisch (Dose, im eigenen Saft)", 110, 25, 0, 1, (50, 100, 150), "Portion", KG),
    # Trockenware & Konserven
    _F("Haferflocken", 370, 13.5, 58.7, 7, (40, 60, 80), "Portion", TW),
    _F("Müsli (ohne Zuckerzusatz)", 360, 10, 60, 7, (40, 60, 80), "Portion", TW),
    _F("Cornflakes", 380, 7, 84, 1, (30, 45, 60), "Portion", TW),
    _F("Nudeln (gekocht)", 150, 5, 30, 0.9, (150, 250, 350), "Portion", TW),
    _F("Vollkornnudeln (gekocht)", 140, 5.5, 26, 1.2, (150, 250, 350), "Portion", TW),
    _F("Reis (gekocht)", 130, 2.7, 28, 0.3, (120, 180, 250), "Portion", TW),
    _F("Couscous (gekocht)", 112, 3.8, 23, 0.2, (120, 180, 250), "Portion", TW),
    _F("Linsen (gekocht)", 116, 9, 20, 0.4, (100, 150, 250), "Portion", TW),
    _F("Kichererbsen (Dose)", 120, 7, 15, 2.5, (80, 130, 200), "Portion", KG),
    _F("Kidneybohnen (Dose)", 100, 7, 14, 0.5, (80, 130, 200), "Portion", KG),
    _F("Mandeln", 600, 21, 6, 52, (15, 30, 50), "Handvoll", TW),
    _F("Walnüsse", 670, 15, 11, 63, (15, 30, 50), "Handvoll", TW),
    _F("Erdnussbutter", 610, 25, 13, 50, (10, 20, 35), "Löffel", KG),
    _F("Honig", 305, 0.4, 80, 0, (8, 15, 25), "Löffel", KG),
    _F("Marmelade", 250, 0.4, 60, 0.1, (15, 25, 35), "Portion", KG),
    _F("Nuss-Nougat-Creme", 540, 6, 57, 31, (10, 20, 35), "Portion", KG),
    _F("Zucker", 400, 0, 100, 0, (4, 8, 12), "Löffel", TW),
    # Öle & Soßen
    _F("Olivenöl", 884, 0, 0, 100, (5, 10, 15), "Löffel", GO),
    _F("Ketchup", 110, 1.5, 25, 0.2, (15, 30, 45), "Portion", GO),
    _F("Mayonnaise", 680, 1, 3, 75, (10, 20, 35), "Portion", GO),
    _F("Pesto", 450, 5, 6, 45, (15, 30, 50), "Portion", GO),
    # Getränke
    _F("Kaffee schwarz", 2, 0.2, 0.3, 0, (150, 250, 350), "Tasse", GT),
    _F("Cappuccino", 45, 2.5, 3.5, 2.3, (150, 250, 350), "Tasse", GT),
    _F("Latte Macchiato", 55, 3, 4, 3, (200, 300, 400), "Glas", GT),
    _F("Orangensaft", 45, 0.7, 10, 0.2, (150, 250, 350), "Glas", GT),
    _F("Apfelschorle", 24, 0.1, 5.5, 0, (200, 330, 500), "Glas", GT),
    _F("Cola", 42, 0, 10.6, 0, (200, 330, 500), "Glas/Dose", GT),
    _F("Cola Zero", 0.3, 0, 0, 0, (200, 330, 500), "Glas/Dose", GT),
    _F("Bier", 43, 0.5, 3.5, 0, (330, 500, 1000), "Flasche", GT),
    _F("Wein (rot)", 85, 0.1, 2.6, 0, (100, 200, 300), "Glas", GT),
    # Süßes & Snacks
    _F("Vollmilchschokolade", 540, 7, 56, 31, (15, 30, 50), "Stück", SN),
    _F("Zartbitterschokolade", 550, 7, 35, 40, (10, 20, 40), "Stück", SN),
    _F("Gummibärchen", 343, 7, 77, 0.1, (20, 50, 100), "Portion", SN),
    _F("Kartoffelchips", 540, 6, 50, 34, (25, 50, 100), "Portion", SN),
    _F("Speiseeis", 200, 3.5, 24, 10, (70, 120, 200), "Kugeln", TK),
    _F("Rührkuchen", 390, 5.5, 50, 18, (60, 90, 120), "Stück", BB),
    _F("Butterkekse", 440, 7, 73, 13, (10, 25, 50), "Portion", SN),
    _F("Müsliriegel", 400, 6, 65, 12, (25, 35, 50), "Stück", SN),
    _F("Proteinriegel", 360, 33, 35, 12, (40, 55, 70), "Stück", SN),
    # Gerichte & Unterwegs
    _F("Pizza Margherita", 250, 10, 30, 9, (150, 300, 450), "Portion", FE),
    _F("Döner Kebab", 215, 12, 20, 10, (250, 350, 450), "Stück", FE),
    _F("Currywurst mit Soße", 250, 9, 10, 20, (150, 220, 300), "Portion", FE),
    _F("Burger", 250, 13, 26, 10, (110, 200, 280), "Stück", FE),
    _F("Pommes frites", 290, 3.4, 36, 14, (100, 150, 220), "Portion", FE),
    _F("Lasagne", 150, 8, 12, 8, (250, 350, 450), "Portion", FE),
    _F("Spaghetti Bolognese", 140, 7, 18, 4.5, (250, 350, 500), "Portion", FE),
]

_BY_NAME = {f.name.lower(): f for f in FOODS}


def search(query: str, limit: int = 8) -> list[BasicFood]:
    """Einfache Teilwort-Suche (alle Wörter müssen vorkommen), kürzere Namen zuerst."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return []
    hits = [f for f in FOODS if all(w in f.name.lower() for w in words)]
    hits.sort(key=lambda f: (not f.name.lower().startswith(words[0]), len(f.name)))
    return hits[:limit]


def get(name: str) -> BasicFood | None:
    return _BY_NAME.get(name.lower())
