"""Einkaufsliste aus einem Wochenplan: zusammenfassen, skalieren, nach Supermarkt-Bereichen sortieren."""

from __future__ import annotations

import re

SECTION_ORDER = [
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

# Fallback, falls eine Zutat ohne (gültigen) Bereich kommt
_KEYWORDS = {
    "Obst & Gemüse": ["apfel", "banane", "tomate", "gurke", "paprika", "karotte", "möhre", "zwiebel", "knoblauch", "kartoffel",
                      "brokkoli", "zucchini", "salat", "spinat", "beere", "zitrone", "avocado", "pilz", "champignon", "kräuter", "petersilie"],
    "Brot & Backwaren": ["brot", "brötchen", "toast", "wrap", "tortilla", "baguette"],
    "Kühlregal": ["milch", "joghurt", "quark", "skyr", "käse", "butter", "eier", "tofu", "hummus", "sahne", "schinken", "feta", "mozzarella"],
    "Fleisch & Fisch": ["hähnchen", "huhn", "pute", "rind", "schwein", "hack", "lachs", "fisch", "garnele"],
    "Tiefkühl": ["tk", "tiefkühl", "gefroren"],
    "Trockenware": ["hafer", "nudel", "pasta", "reis", "couscous", "linse", "mehl", "müsli", "nuss", "mandel", "samen", "bulgur", "quinoa"],
    "Konserven & Gläser": ["dose", "kichererbse", "bohne", "mais", "passiert", "gehackt", "kokosmilch", "erdnussbutter", "thunfisch"],
    "Gewürze, Öle & Soßen": ["öl", "essig", "soße", "sauce", "brühe", "gewürz", "senf", "honig", "paste", "salz", "pfeffer"],
    "Getränke": ["wasser", "saft", "tee", "kaffee"],
}

# Grundvorrat – taucht nicht auf der Liste auf
PANTRY = {"salz", "pfeffer", "wasser", "leitungswasser"}


def guess_section(name: str) -> str:
    n = name.lower()
    if n.strip() in ("ei", "eier"):
        return "Kühlregal"
    for section, words in _KEYWORDS.items():
        if any(w in n for w in words):
            return section
    return "Sonstiges"


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def aggregate(plan: dict, persons: int = 1) -> list[dict]:
    """Summiert alle Zutaten des Plans (pro Person) × Personen."""
    acc: dict[tuple[str, str], dict] = {}
    for day in plan.get("days", []):
        for meal in day.get("meals", []):
            for ing in meal.get("ingredients", []):
                name = (ing.get("name") or "").strip()
                if not name or _key(name) in PANTRY:
                    continue
                unit = ing.get("unit") or "Stk"
                section = ing.get("section") if ing.get("section") in SECTION_ORDER else guess_section(name)
                k = (_key(name), unit)
                entry = acc.setdefault(k, {"name": name, "qty": 0.0, "unit": unit, "section": section})
                entry["qty"] += float(ing.get("qty") or 0) * persons
    items = list(acc.values())
    for it in items:
        it["qty"] = _round_qty(it["qty"], it["unit"])
    items.sort(key=lambda i: (SECTION_ORDER.index(i["section"]) if i["section"] in SECTION_ORDER else 99, i["name"].lower()))
    return items


def _round_qty(qty: float, unit: str) -> float:
    if unit == "Stk":
        return float(max(1, round(qty + 0.49)))  # angebrochene Stücke aufrunden
    if qty >= 100:
        return float(round(qty / 10) * 10)
    return float(round(qty))


def format_qty(qty: float | None, unit: str | None) -> str:
    if not qty:
        return ""
    if unit in ("g", "ml") and qty >= 1000:
        big = "kg" if unit == "g" else "l"
        return f"{qty / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + f" {big}"
    return f"{qty:g} {unit or ''}".strip()


def as_text(items: list[dict]) -> str:
    """Liste als Text zum Teilen (z. B. in Messenger)."""
    lines, current = [], None
    for it in items:
        if it["section"] != current:
            current = it["section"]
            lines.append(f"\n{current}")
        mark = "☑" if it.get("checked") else "☐"
        qty = format_qty(it.get("qty"), it.get("unit"))
        lines.append(f"{mark} {it['name']}" + (f" – {qty}" if qty else ""))
    return "\n".join(lines).strip()
