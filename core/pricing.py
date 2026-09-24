"""Preise für den Budget-Modus.

Zunächst eine editierbare Tabelle mit typischen Discounter-Preisen (Stand 2026, gerundet).
Über das `PriceProvider`-Protokoll lassen sich später echte Angebotsdaten anbinden
(z. B. ein Prospekt-/Angebots-API): Man implementiert `prices(user_id)` und ersetzt den
Provider in `services/planning.py`.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Price:
    item: str
    unit: str  # g | ml | Stk
    pack_qty: float
    price_eur: float
    section: str

    @property
    def per_unit(self) -> float:
        return self.price_eur / self.pack_qty if self.pack_qty else 0.0


def _p(item, unit, qty, eur, section) -> Price:
    return Price(item, unit, qty, eur, section)


OG, BB, KR, FF, TW, KG, GO, GT, TK = (
    "Obst & Gemüse", "Brot & Backwaren", "Kühlregal", "Fleisch & Fisch", "Trockenware",
    "Konserven & Gläser", "Gewürze, Öle & Soßen", "Getränke", "Tiefkühl",
)

DEFAULT_PRICES: list[Price] = [
    _p("Äpfel", "g", 1000, 2.49, OG), _p("Bananen", "g", 1000, 1.69, OG), _p("Tomaten", "g", 500, 1.49, OG),
    _p("Gurke", "Stk", 1, 0.69, OG), _p("Paprika", "g", 500, 1.99, OG), _p("Karotten", "g", 1000, 1.19, OG),
    _p("Zwiebeln", "g", 1000, 1.29, OG), _p("Knoblauch", "Stk", 1, 0.49, OG), _p("Kartoffeln", "g", 2500, 2.99, OG),
    _p("Süßkartoffeln", "g", 1000, 2.49, OG), _p("Brokkoli", "g", 500, 1.49, OG), _p("Zucchini", "g", 500, 1.49, OG),
    _p("Champignons", "g", 400, 1.99, OG), _p("Eisbergsalat", "Stk", 1, 0.99, OG), _p("Zitronen", "g", 500, 1.49, OG),
    _p("Avocado", "Stk", 1, 0.99, OG), _p("Frühlingszwiebeln", "Stk", 1, 0.79, OG), _p("Spinat frisch", "g", 250, 1.49, OG),
    _p("Vollkornbrot", "g", 500, 1.49, BB), _p("Toastbrot", "g", 500, 0.99, BB), _p("Brötchen", "Stk", 10, 1.49, BB),
    _p("Tortilla-Wraps", "Stk", 6, 1.29, BB),
    _p("Milch 1,5 %", "ml", 1000, 0.99, KR), _p("Haferdrink", "ml", 1000, 1.19, KR), _p("Joghurt natur", "g", 500, 0.89, KR),
    _p("Magerquark", "g", 500, 1.19, KR), _p("Skyr", "g", 450, 1.49, KR), _p("Hüttenkäse", "g", 200, 0.89, KR),
    _p("Frischkäse", "g", 200, 0.99, KR), _p("Gouda", "g", 400, 2.99, KR), _p("Mozzarella", "g", 125, 0.79, KR),
    _p("Feta", "g", 200, 1.49, KR), _p("Hartkäse gerieben", "g", 200, 1.99, KR), _p("Butter", "g", 250, 2.29, KR),
    _p("Eier", "Stk", 10, 2.49, KR), _p("Tofu", "g", 400, 1.99, KR), _p("Hummus", "g", 200, 1.29, KR),
    _p("Kochschinken", "g", 200, 1.79, KR),
    _p("Hähnchenbrustfilet", "g", 1000, 8.99, FF), _p("Putenbrust", "g", 400, 4.49, FF),
    _p("Hackfleisch gemischt", "g", 500, 3.99, FF), _p("Rinderhackfleisch", "g", 500, 4.99, FF),
    _p("Haferflocken", "g", 500, 0.59, TW), _p("Nudeln", "g", 500, 0.79, TW), _p("Vollkornnudeln", "g", 500, 0.99, TW),
    _p("Reis", "g", 1000, 1.69, TW), _p("Couscous", "g", 500, 1.29, TW), _p("Rote Linsen", "g", 500, 1.49, TW),
    _p("Mehl", "g", 1000, 0.59, TW), _p("Müsli", "g", 750, 1.99, TW), _p("Mandeln", "g", 200, 2.29, TW),
    _p("Walnüsse", "g", 200, 2.49, TW), _p("Chiasamen", "g", 200, 1.99, TW),
    _p("Kichererbsen (Dose)", "g", 400, 0.79, KG), _p("Kidneybohnen (Dose)", "g", 400, 0.69, KG),
    _p("Mais (Dose)", "g", 285, 0.79, KG), _p("Tomaten gehackt (Dose)", "g", 400, 0.59, KG),
    _p("Passierte Tomaten", "g", 500, 0.55, KG), _p("Thunfisch (Dose)", "g", 150, 1.29, KG),
    _p("Kokosmilch", "ml", 400, 1.29, KG), _p("Erdnussbutter", "g", 350, 2.49, KG),
    _p("Olivenöl", "ml", 750, 5.99, GO), _p("Rapsöl", "ml", 1000, 1.99, GO), _p("Sojasauce", "ml", 250, 1.29, GO),
    _p("Gemüsebrühe", "g", 200, 0.99, GO),
    _p("Gemüsemischung TK", "g", 1000, 1.99, TK), _p("Beerenmischung TK", "g", 750, 3.49, TK),
    _p("Spinat TK", "g", 750, 1.49, TK), _p("Lachsfilet TK", "g", 500, 6.49, TK),
    _p("Mineralwasser", "ml", 1500, 0.25, GT),
]


class PriceProvider(Protocol):
    """Schnittstelle für Preisquellen (Tabelle heute, Angebotsdaten morgen)."""

    def prices(self, user_id: int) -> list[Price]: ...


def _norm(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"[^a-zäöüß ]", " ", name)
    words = [w for w in name.split() if w not in {"frisch", "frische", "bio", "natur", "rot", "rote", "gelb", "grün"}]
    return " ".join(words)


def match_price(ingredient: str, prices: list[Price]) -> Price | None:
    """Findet den passendsten Preis zu einer Zutat (Teilwort, sonst unscharfer Vergleich)."""
    n = _norm(ingredient)
    if not n:
        return None
    by_norm = {_norm(p.item): p for p in prices}
    if n in by_norm:
        return by_norm[n]
    for key, p in by_norm.items():  # „Hähnchenbrust“ ↔ „Hähnchenbrustfilet“, „Tomate“ ↔ „Tomaten“
        if key and (key in n or n in key or key.rstrip("n") == n.rstrip("n")):
            return p
    close = difflib.get_close_matches(n, list(by_norm), n=1, cutoff=0.72)
    return by_norm[close[0]] if close else None


@dataclass
class CostEstimate:
    proportional: float  # anteilige Kosten der verbrauchten Mengen
    at_checkout: float  # Kosten ganzer Packungen
    unmatched: list[str]


def estimate(items: list[dict], prices: list[Price]) -> CostEstimate:
    """items: aggregierte Einkaufsliste mit name, qty, unit."""
    prop = checkout = 0.0
    unmatched: list[str] = []
    for it in items:
        p = match_price(it["name"], prices)
        qty = float(it.get("qty") or 0)
        if not p or qty <= 0 or (it.get("unit") and it["unit"] != p.unit):
            unmatched.append(it["name"])
            continue
        prop += qty * p.per_unit
        checkout += math.ceil(qty / p.pack_qty - 1e-9) * p.price_eur
    return CostEstimate(round(prop, 2), round(checkout, 2), unmatched)


def compact_table(prices: list[Price], limit: int = 90) -> str:
    """Kurze Preisliste für den Prompt (Budget-Modus)."""
    lines = [f"- {p.item}: {p.price_eur:.2f} € / {p.pack_qty:g} {p.unit}".replace(".", ",", 1) for p in prices[:limit]]
    return "\n".join(lines)
