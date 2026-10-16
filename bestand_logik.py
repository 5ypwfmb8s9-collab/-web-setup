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

WICHTIG (siehe Anfrage vom 16.10.): die einfache Summe "Bestand verfügbar"
aus dispo_dashboard/logic.py zaehlt JEDE Charge/Parti-Nr mit, auch wenn
keine einzige davon fuer sich allein eine volle Fuellmenge ergibt - in der
Praxis aber darf eine Fuellmenge (KLT/Packeinheit) nicht aus mehreren
verschiedenen Chargen gemischt werden. nutzbarer_bestand_je_artikel()
rechnet deshalb strenger: je Charge separat auf volle Fuellmengen
abgerundet (Reste verschiedener Chargen werden NICHT addiert), und ohne
Lagerorte, die nicht frei verfuegbar sind (siehe AUSGESCHLOSSENE_LAGERORTE).
Mit echten Daten verifiziert (16.10., Artikel 100217000, Füllmenge 2000):
einfache Summe 62.759 vs. tatsaechlich nutzbar 8.000.

WICHTIG: Reicht der verbleibende Bestand nur fuer einen TEIL einer
einzelnen Position, wird genau dieser Teil als gedeckt (planbar) gezaehlt
und nur der Rest als Rueckstand - nicht die ganze Position. Eine Position
kann dadurch in BEIDEN Ergebnissen auftauchen, je mit ihrer eigenen
Teilmenge (gekennzeichnet ueber den gemeinsamen urspruenglichen Index).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

VORLAGE_DATEI = Path(__file__).resolve().parent / "dispo_dashboard" / "planung_vorlage.xlsx"

# Lagerorte (Depo adresi), deren Bestand NICHT frei fuer neue Planung zaehlt.
# OUT1 = bereits fuer einen Versand bereitgestellter/ausgelagerter Bestand
# (siehe echte Daten vom 16.10.: Stok türü dort zwar "F2"/verfuegbar, aber
# bereits an einem Ausgangs-Lagerort - nicht mehr frei zuteilbar). Bei Fragen
# zu weiteren Sonder-Lagerorten (z. B. INB1 - Wareneingang) bitte Rueckfrage
# stellen statt zu raten.
AUSGESCHLOSSENE_LAGERORTE = {"OUT1"}

# Lagerorte, deren Bestand ZWAR normal mitgezaehlt/eingeplant wird (anders
# als AUSGESCHLOSSENE_LAGERORTE), aber als Hinweis markiert werden soll, weil
# er nicht sofort entnehmbar ist. MGBEKLEYEN = Bestandsart F1 ("Giriş Stoğu
# (Çıkış yapılamaz)" = Wareneingang, Entnahme noch nicht moeglich) - mit
# echten Daten vom 16.10. geprueft: aller F1-Bestand liegt ausschliesslich
# an diesem Lagerort.
HINWEIS_LAGERORTE = {"MGBEKLEYEN"}


def lade_fuellmenge_je_artikel() -> dict:
    """Füllmenge je Norm-Nr (Planung-Vorlage, Blatt "Almanca Hilfsdaten",
    Spalte C/D - genau die Quelle, die auch die Live-Formeln in der
    Vorlage fuer Spalte J (Füllmenge) nutzen). Gemeinsame Quelle fuer
    Planung Erstellung UND die Bestandsrechnung hier."""
    try:
        hilfsdaten = pd.read_excel(VORLAGE_DATEI, sheet_name="Almanca Hilfsdaten")
    except (FileNotFoundError, ValueError):
        return {}
    spalten = hilfsdaten.columns
    if len(spalten) < 4:
        return {}
    norm_nr_spalte, fuellmenge_spalte = spalten[2], spalten[3]
    tabelle = hilfsdaten[[norm_nr_spalte, fuellmenge_spalte]].dropna()
    tabelle.columns = ["Norm-Nr", "Fuellmenge"]
    tabelle = tabelle.drop_duplicates(subset="Norm-Nr", keep="first")
    tabelle["Norm-Nr"] = pd.to_numeric(tabelle["Norm-Nr"], errors="coerce")
    tabelle = tabelle.dropna(subset=["Norm-Nr"])
    tabelle["Norm-Nr"] = tabelle["Norm-Nr"].astype(int)
    return dict(zip(tabelle["Norm-Nr"], tabelle["Fuellmenge"]))


FUELLMENGE_JE_ARTIKEL = lade_fuellmenge_je_artikel()


def fuellmenge(norm_nr) -> float:
    return FUELLMENGE_JE_ARTIKEL.get(norm_nr, 1.0) or 1.0


def nutzbarer_bestand_je_artikel(bestand_je_charge: pd.DataFrame, bestand_verfuegbar_arten) -> dict:
    """Norm-Nr -> tatsaechlich nutzbare Menge, je Charge/Parti-Nr separat auf
    volle Fuellmengen abgerundet (keine Mischung verschiedener Chargen
    innerhalb einer Fuellmenge) und ohne AUSGESCHLOSSENE_LAGERORTE.

    bestand_je_charge: die rohe Charge-Ebene aus loaders.lade_bestand()
    (Spalten Norm-Nr, Menge, Bestandsart, Lagerort, Charge, ...).
    bestand_verfuegbar_arten: dispo_dashboard.config.BESTAND_VERFUEGBAR
    (welche Bestandsarten ueberhaupt als verfuegbar gelten, z. B. F2/F1) -
    bewusst als Parameter, nicht importiert, damit diese eine Stelle in
    config.py die einzige Quelle fuer "was zaehlt als verfuegbar" bleibt.
    """
    if bestand_je_charge is None or bestand_je_charge.empty:
        return {}
    verwendbar = bestand_je_charge[
        bestand_je_charge["Bestandsart"].isin(list(bestand_verfuegbar_arten))
        & ~bestand_je_charge["Lagerort"].isin(AUSGESCHLOSSENE_LAGERORTE)
    ]
    if verwendbar.empty:
        return {}
    je_charge = verwendbar.groupby(["Norm-Nr", "Charge"])["Menge"].sum()

    ergebnis: dict = {}
    for (norm_nr, _charge), menge in je_charge.items():
        f = fuellmenge(norm_nr)
        nutzbar = (menge // f) * f if f else 0
        ergebnis[norm_nr] = ergebnis.get(norm_nr, 0) + nutzbar
    return ergebnis


def artikel_mit_lagerort_hinweis(bestand_je_charge: pd.DataFrame, bestand_verfuegbar_arten) -> set:
    """Norm-Nr-Menge, bei denen die GESAMTE nutzbare Menge (nach Fuellmengen-
    Abrundung je Charge) ausschliesslich aus HINWEIS_LAGERORTE-Lagerorten
    (z. B. MGBEKLEYEN - neue Ware, noch nicht ins Regal eingeraeumt) stammt,
    OHNE jeglichen normalen Bestand an anderen Lagerorten. Gibt es daneben
    auch normalen (nicht-MGBEKLEYEN) nutzbaren Bestand fuer denselben
    Artikel, wird NICHT markiert - der Hinweis soll nur erscheinen, wenn
    wirklich AUSSCHLIESSLICH neue, noch nicht eingelagerte Ware zur
    Verfuegung steht (siehe Anfrage vom 16.10.: "soll nur da stehen, wenn
    da nur MGBEKLEYEN ist ohne normalen Stock")."""
    if bestand_je_charge is None or bestand_je_charge.empty:
        return set()
    verwendbar = bestand_je_charge[
        bestand_je_charge["Bestandsart"].isin(list(bestand_verfuegbar_arten))
        & ~bestand_je_charge["Lagerort"].isin(AUSGESCHLOSSENE_LAGERORTE)
    ]
    if verwendbar.empty:
        return set()
    je_charge = verwendbar.groupby(["Norm-Nr", "Charge", "Lagerort"])["Menge"].sum()

    normal_je_artikel: dict = {}
    hinweis_je_artikel: dict = {}
    for (norm_nr, _charge, lagerort), menge in je_charge.items():
        f = fuellmenge(norm_nr)
        nutzbar = (menge // f) * f if f else 0
        if nutzbar <= 0:
            continue
        ziel = hinweis_je_artikel if lagerort in HINWEIS_LAGERORTE else normal_je_artikel
        ziel[norm_nr] = ziel.get(norm_nr, 0) + nutzbar

    return {
        norm_nr for norm_nr, menge in hinweis_je_artikel.items()
        if menge > 0 and normal_je_artikel.get(norm_nr, 0) == 0
    }


def teile_nach_bestand(
    positionen: pd.DataFrame, nutzbarer_bestand: dict | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """positionen (ein beliebiger Ausschnitt von dispo_dashboard.logic.berechne()
    mit "Kum. Bedarf Artikel", "Bestand verfügbar", "Offene Menge", "Ladedatum",
    "Norm-Nr") in (rueckstand, planbar) aufteilen - je Position ggf. anteilig.

    nutzbarer_bestand: optional das Ergebnis von nutzbarer_bestand_je_artikel()
    (Norm-Nr -> Menge). Wenn angegeben, wird DIESE (chargen-/fuellmengen-
    genaue) Zahl statt der einfachen Spalte "Bestand verfügbar" verwendet -
    das ist der empfohlene, korrekte Aufruf. Ohne das Argument faellt die
    Funktion auf die einfache Summe zurueck (z. B. fuer Tests/Abwaertskomp.).

    "Kum. Bedarf Artikel" ist bereits GLOBAL je Artikel ueber alle
    Positionen aufsummiert (auch ausserhalb des hier uebergebenen
    Ausschnitts) - das bleibt beim Filtern/Teilen unveraendert korrekt,
    da die Spalte unabhaengig vom jeweiligen Ausschnitt vorberechnet ist.
    """
    fenster = positionen.copy().sort_values("Ladedatum")
    if nutzbarer_bestand is not None:
        bestand = fenster["Norm-Nr"].map(nutzbarer_bestand).fillna(0)
    else:
        bestand = fenster["Bestand verfügbar"]
    fehlmenge_nur_bestand = np.minimum(
        fenster["Offene Menge"],
        fenster["Kum. Bedarf Artikel"] - bestand,
    ).clip(lower=0)
    fenster["Menge (Rückstand)"] = fehlmenge_nur_bestand
    fenster["Menge (planbar)"] = fenster["Offene Menge"] - fehlmenge_nur_bestand

    rueckstand = fenster[fenster["Menge (Rückstand)"] > 0].copy()
    rueckstand["Offene Menge"] = rueckstand["Menge (Rückstand)"]
    planbar = fenster[fenster["Menge (planbar)"] > 0].copy()
    planbar["Offene Menge"] = planbar["Menge (planbar)"]
    return rueckstand, planbar
