"""Gemeinsame "nur physischer Bestand"-Aufteilung fuer Dashboard Dispo und
Planung Erstellung.

Eine Berechnung, von beiden Stellen importiert - damit die Logik, was als
"gedeckt" zaehlt, nicht auseinanderlaufen kann (Wunsch: Dispo-Bereich soll
zeigen, was auch wirklich eingeplant wird, mit derselben Regel).

Anders als die "Fehlmenge" in dispo_dashboard/logic.py (die Bestand UND
bereits unterwegs befindliche Zugaenge als Deckung zaehlt) zaehlt hier NUR
der aktuell physisch vorhandene Bestand als Deckung. Das ist eine eigene,
striktere Lesart derselben Zahlen - dispo_dashboard/logic.py selbst wird
nicht veraendert (Fehlmenge/Status/Ampel dort bleiben unangetastet, werden
fuer andere Zwecke weiter gebraucht, z. B. "Zugang kommt"-Hinweise).

Baut auf den von dispo_dashboard/logic.berechne() bereits berechneten
Spalten auf ("Kum. Bedarf Artikel", "Bestand verfügbar", "Offene Menge") -
keine neue Bestandsrechnung, nur eine strengere Verteilung derselben Zahlen.

WICHTIG: Reicht der verbleibende Bestand nur fuer einen TEIL einer
einzelnen Position, wird genau dieser Teil als gedeckt (planbar) gezaehlt
und nur der Rest als Rueckstand - nicht die ganze Position. Eine Position
kann dadurch in BEIDEN Ergebnissen auftauchen, je mit ihrer eigenen
Teilmenge (gekennzeichnet ueber den gemeinsamen urspruenglichen Index).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def teile_nach_bestand(positionen: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """positionen (ein beliebiger Ausschnitt von dispo_dashboard.logic.berechne()
    mit "Kum. Bedarf Artikel", "Bestand verfügbar", "Offene Menge", "Ladedatum")
    in (rueckstand, planbar) aufteilen - je Position ggf. anteilig.

    "Kum. Bedarf Artikel" ist bereits GLOBAL je Artikel ueber alle
    Positionen aufsummiert (auch ausserhalb des hier uebergebenen
    Ausschnitts) - das bleibt beim Filtern/Teilen unveraendert korrekt,
    da die Spalte unabhaengig vom jeweiligen Ausschnitt vorberechnet ist.
    """
    fenster = positionen.copy().sort_values("Ladedatum")
    fehlmenge_nur_bestand = np.minimum(
        fenster["Offene Menge"],
        fenster["Kum. Bedarf Artikel"] - fenster["Bestand verfügbar"],
    ).clip(lower=0)
    fenster["Menge (Rückstand)"] = fehlmenge_nur_bestand
    fenster["Menge (planbar)"] = fenster["Offene Menge"] - fehlmenge_nur_bestand

    rueckstand = fenster[fenster["Menge (Rückstand)"] > 0].copy()
    rueckstand["Offene Menge"] = rueckstand["Menge (Rückstand)"]
    planbar = fenster[fenster["Menge (planbar)"] > 0].copy()
    planbar["Offene Menge"] = planbar["Menge (planbar)"]
    return rueckstand, planbar
