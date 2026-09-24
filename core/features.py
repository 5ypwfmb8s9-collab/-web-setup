"""Feature-Flags für ein späteres Freemium-Modell.

* Jeder Nutzer hat eine Stufe (`users.tier`): `free` oder `premium`.
* Die Grundfunktionen (Tracking, Tagesübersicht, Gewichtstrend) sind dauerhaft kostenlos.
* Aktuell ist ALLES freigeschaltet (`ALL_UNLOCKED = True`). Wird das später umgestellt,
  zeigen die Seiten einen ruhigen Hinweis – keine Pop-ups, keine Unterbrechungen.
"""

from __future__ import annotations

ALL_UNLOCKED = True

FREE = "free"
PREMIUM = "premium"

# Funktion → Mindeststufe
FEATURES: dict[str, str] = {
    # dauerhaft kostenlos
    "tracking": FREE,
    "suche_barcode": FREE,
    "tagesuebersicht": FREE,
    "gewichtstrend": FREE,
    "favoriten": FREE,
    "export": FREE,  # Datenhoheit ist kein Premium-Feature
    # Kandidaten für Premium (KI-/Rechenintensiv)
    "freitext_ki": PREMIUM,
    "foto_ki": PREMIUM,
    "wochenplan": PREMIUM,
    "resteverwertung": PREMIUM,
    "coach": PREMIUM,
    "adaptiver_bedarf": PREMIUM,
}

LABELS = {FREE: "Free", PREMIUM: "Premium"}


def enabled(feature: str, tier: str | None) -> bool:
    if ALL_UNLOCKED:
        return True
    needed = FEATURES.get(feature, FREE)
    return needed == FREE or tier == PREMIUM


def locked_note(feature: str) -> str:
    """Ruhiger Hinweistext, falls eine Funktion (später) nicht freigeschaltet ist."""
    return "Diese Funktion ist Teil von KANO Premium. Deine Grundfunktionen bleiben immer kostenlos."
