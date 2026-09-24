"""Mengen & Nährwertberechnung, inkl. Ungefähr-Modus (klein/mittel/groß)."""

from __future__ import annotations

SIZES = {"klein": "Klein", "mittel": "Mittel", "gross": "Groß"}
SIZE_INDEX = {"klein": 0, "mittel": 1, "gross": 2}

# Faktoren relativ zur Standardportion, falls ein Lebensmittel keine eigenen Portionsgrößen hat
SIZE_FACTORS = {"klein": 0.65, "mittel": 1.0, "gross": 1.5}
DEFAULT_PORTION_G = 150.0


def grams_for_size(food: dict, size: str) -> float:
    """Gramm für klein/mittel/groß – aus den Portionsgrößen des Lebensmittels oder per Faktor."""
    portions = food.get("portions")
    if portions:
        return float(portions[SIZE_INDEX[size]])
    base = food.get("serving_g") or DEFAULT_PORTION_G
    return round(float(base) * SIZE_FACTORS[size])


def nutrients_for(food: dict, grams: float) -> dict:
    """Nährwerte für eine Menge eines Lebensmittels mit Angaben je 100 g."""
    f = grams / 100.0
    return {
        "kcal": round((food.get("kcal_100g") or 0) * f, 1),
        "protein": round((food.get("protein_100g") or 0) * f, 1),
        "carbs": round((food.get("carbs_100g") or 0) * f, 1),
        "fat": round((food.get("fat_100g") or 0) * f, 1),
    }


def scale_item(item: dict, new_grams: float) -> dict:
    """Skaliert einen Eintrag (z. B. von Claude geschätzt) auf eine neue Menge."""
    old = item.get("grams") or 0
    if old <= 0:
        return {**item, "grams": new_grams}
    f = new_grams / old
    return {
        **item,
        "grams": new_grams,
        **{k: round((item.get(k) or 0) * f, 1) for k in ("kcal", "protein", "carbs", "fat")},
    }


def size_from_grams(grams: float, food: dict) -> str:
    """Ordnet eine Grammzahl der nächstliegenden Größe zu (für die Anzeige im Ungefähr-Modus)."""
    options = {s: grams_for_size(food, s) for s in SIZES}
    return min(options, key=lambda s: abs(options[s] - grams))
