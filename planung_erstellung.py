"""Planung Erstellung: taegliche Kommissionier-/Palettenplanung fuer VW aus
Kundenauftraegen (Dashboard Dispo: Bedarf) und Bestand erzeugen.

Nutzt die vom Kunden bereitgestellte Excel-Vorlage (dispo_dashboard/
planung_vorlage.xlsx, alle 17 Blaetter inkl. Referenzdaten/Formeln bleiben
unveraendert) und befuellt nur die hellgrauen Eingabespalten in den
Blaettern "Almanca" (Hauptplanung), "Rueckstaende" und "DHL UPS".

Datengrundlage: dieselben positionen wie im Dashboard Dispo (Bedarf +
Bestand, bereits mit Fehlmenge/Status berechnet) - kein erneuter Upload
noetig, Dispo muss vorher geladen sein.

Geschaeftslogik (siehe Anfrage, anhand der Vorlage/Formeln verifiziert):
- Kundenauftraege vom aeltesten Ladedatum bis zum gewaehlten Planungsdatum.
- Planbar ist NUR, was der aktuell PHYSISCH VORHANDENE Bestand deckt (nicht
  die "Fehlmenge" aus dem Dashboard Dispo, die auch unterwegs befindliche
  Zugaenge mitzaehlt). Das ergibt eine eigene, strengere Kennzahl
  "Fehlmenge (nur Bestand)" - Zugaenge zaehlen fuer die Planung nicht als
  verfuegbar, auch wenn sie laut SAP ZMM1000 vor dem Ladedatum ankommen
  wuerden.
- Reicht der Bestand fuer eine Position nur TEILWEISE, wird genau der
  gedeckte Teil eingeplant und nur der fehlende Rest geht in die
  Rueckstaende - nicht die ganze Position. Dieselbe Abladestelle/Artikel-
  Kombination kann dadurch in beiden Blaettern auftauchen, je mit ihrer
  eigenen Teilmenge.
- Fehlmenge (nur Bestand) > 0 -> Teilmenge in Blatt "Rueckstaende", rote
  Schrift. Dort wird zusaetzlich - je Artikel, nach Dringlichkeit
  (aeltestes Ladedatum zuerst) - der naechste noch nicht zugeordnete
  Zugang aus ZMM1000 in Spalte M "Lieferschein" eingetragen
  (Referenznummer/NRI, Ankunft-Datum, Menge), damit erkennbar ist,
  was/wann dafuer bereits unterwegs ist - auch wenn die Ankunft erst NACH
  dem Planungsdatum liegt.
- Durch physischen Bestand gedeckte Teilmenge -> Blatt "Almanca": Spalte
  C "Lagerort"
  = Abladestelle aus dem Kundenauftrag (per echten Daten verifiziert:
  Dispo-Abladestelle entspricht hier der Vorlagen-Spalte "Lagerort", NICHT
  der Vorlagen-Spalte "Abladestelle" - letztere wird aus einer anderen
  Codierung ueber das Blatt "Werke" abgeleitet), Spalte G = Norm-Nr,
  Spalte I = Menge. Sortiert nach Abladestelle aufsteigend, Leerzeile
  zwischen Abladestellen-Gruppen.
- Menge wird auf das naechste volle Vielfache der Fuellmenge aufgerundet
  (ganze KLT/Packeinheiten), angepasste Menge in roter Schrift.
- Packeinheiten < 5 je Artikel -> komplette Zeile zu "DHL UPS" (gruen
  ausgefuellt), da zu wenig fuer eine eigene Palette.
- Rest-Packeinheiten (nach vollen Paletten) werden je Abladestelle
  versucht mit anderen Artikeln zu einer Mix-Palette zusammenzulegen
  (bis zur Lagen-Kapazitaet lt. Stammdaten: 10 bei Standard-Paletten,
  20 bei VWPAL), damit keine Palette mit nur bis zu 5 Stueck alleine
  dasteht. Nicht unterzubringende Reste -> ebenfalls "DHL UPS". Ein
  zugeordneter Rest wird IMMER zur bestehenden Zeile desselben Artikels an
  dieser Abladestelle addiert statt eine zweite Zeile zu erzeugen - pro
  Artikel und Abladestelle gibt es in Almanca/DHL UPS nie zwei Zeilen.
- Abholdatum (Planungsdatum) wird einmalig in Zelle M2 eingetragen.
- Liegt ein Teil des genutzten Bestands eines Artikels am Lagerort
  MGBEKLEYEN (Wareneingang, Entnahme noch nicht moeglich), wird er trotzdem
  ganz normal mitgezaehlt und eingeplant (anders als OUT1) - nur zur Info
  wird "MGBEKLEYEN" in Spalte L "Lagerauftrag" der betroffenen Zeile(n) in
  Almanca/DHL UPS eingetragen.
- Blatt "Rueckstaende" artikelweise sortiert (Norm-Nr aufsteigend, je
  Artikel aeltestes Ladedatum zuerst), Leerzeile zwischen Artikeln.
- Eingeplante Mengen, die am Datenstand (Stichtag) bereits Rueckstand
  waren (Ladedatum davor, Ware jetzt physisch da): VW-Nr (F) rot und
  urspruengliches Ladedatum in L "Lagerauftrag" (als echtes Datum, damit der
  Auftragszaehler B2 es nicht als Lagerauftrag zaehlt; bei zusaetzlichem
  MGBEKLEYEN-Hinweis "MGBEKLEYEN · TT.MM.JJJJ").
- Rueckstaende, fuer die laut ZMM1000 bis spaetestens zum Planungsdatum
  eine NRI eintrifft (Ware noch nicht da): eigener Bereich ganz unten unter
  den geplanten Zeilen in "Almanca", A bis T gelb, Ladedatum in L, NRI-Info
  in M, Kennzeichnung "Erwartet – nicht in Summe" in Z. E2 (Paletten
  gesamt) und H2 (Gesamtgewicht) summieren per SUMMEWENNS alles ausser
  diesen Zeilen - Text in Z loeschen, sobald die Ware mitgenommen wird.
- Vorziehen: Rueckstaende mit jetzt vorhandener Ware koennen in eine bereits
  erstellte Planungsdatei nachgetragen werden (ergaenze_bestehende_planung).

WICHTIG (erster Testaufbau): die Mix-Paletten-Logik ist eine Heuristik
(groesste Reste zuerst kombinieren) - bei echten Tagesdaten bitte pruefen,
ob die Zusammenlegung so zustande kommt wie gewuenscht, und Rueckmeldung
geben, falls nicht.
"""
from __future__ import annotations

import io
import math
from copy import copy
from pathlib import Path

import openpyxl
import pandas as pd
import streamlit as st
from openpyxl.styles import Font, PatternFill

import bestand_logik
from dispo_dashboard import config

VORLAGE_DATEI = Path(__file__).resolve().parent / "dispo_dashboard" / "planung_vorlage.xlsx"

ERSTE_DATENZEILE = 5
ROT = "FFFF0000"
GRUEN_FUELLUNG = PatternFill(patternType="solid", fgColor="FF92D050")
GELB_FUELLUNG = PatternFill(patternType="solid", fgColor="FFFFFF00")
# Spalten (1-basiert) der Vorlage, die NICHT per Formel befuellt werden
# (Eingabe-/Notizspalten) - nur diese werden geschrieben/verschoben.
SPALTE_LAGERORT, SPALTE_VW_NR, SPALTE_NORM_NR, SPALTE_MENGE = 3, 6, 7, 9
SPALTE_LAGERAUFTRAG, SPALTE_LIEFERSCHEIN, SPALTE_HINWEIS = 12, 13, 26
EINGABE_SPALTEN = (SPALTE_LAGERORT, SPALTE_NORM_NR, SPALTE_MENGE,
                   SPALTE_LAGERAUFTRAG, SPALTE_LIEFERSCHEIN, SPALTE_HINWEIS)
GELB_BIS_SPALTE = 20  # A bis T
# Kennzeichnung in Spalte Z fuer den Bereich "Zugang erwartet". E2/H2 der
# Vorlage summieren per SUMMEWENNS alles AUSSER diesen Zeilen - wer die Ware
# nach Eintreffen doch mitnimmt, loescht einfach den Text in Spalte Z.
ERWARTET_MARKER = "Erwartet – nicht in Summe"
SUMME_PALETTEN = '=SUMIFS(Q5:Q624,Z5:Z624,"<>Erwartet*")'
SUMME_GEWICHT = '=SUMIFS(T5:T624,Z5:Z624,"<>Erwartet*")'
MINDEST_PACKEINHEITEN_FUER_PALETTE = 5  # darunter: einzeln nicht paletten-/versandfaehig -> DHL/UPS


# --- Referenzdaten aus der Vorlage (Füllmenge, Palettentyp) -----------------
# Füllmenge kommt aus bestand_logik (gemeinsame Quelle mit der Bestandsrechnung
# dort/im Dashboard Dispo) - hier nur noch die Palettenspezifikation (wird
# ausserhalb der Planung nicht gebraucht).

def _lade_palettenspezifikation() -> dict:
    """(Lagerort, Norm-Nr) -> {anzahl_pro_lage, anzahl_volle_palette, typ}
    aus dem Blatt "Stammdaten" (dieselbe Quelle, die auch die Live-Formel
    fuer Spalte N "Paletten" nutzt). "Lagerort" hier = der Abladestellen-
    Code aus dem Kundenauftrag (siehe Modul-Docstring)."""
    try:
        stamm = pd.read_excel(VORLAGE_DATEI, sheet_name="Stammdaten")
    except (FileNotFoundError, ValueError):
        return {}
    noetige_spalten = ["Lagerort", "Norm NR.", "Anzahl Pro Lage", "Anzahl ", "Paletten"]
    if not set(noetige_spalten) <= set(stamm.columns):
        return {}
    tabelle = stamm[noetige_spalten].dropna(subset=["Lagerort", "Norm NR."]).copy()
    tabelle["Norm NR."] = pd.to_numeric(tabelle["Norm NR."], errors="coerce")
    tabelle = tabelle.dropna(subset=["Norm NR."])
    tabelle["Norm NR."] = tabelle["Norm NR."].astype(int)
    tabelle["Lagerort"] = tabelle["Lagerort"].astype(str).str.strip()
    tabelle = tabelle.drop_duplicates(subset=["Lagerort", "Norm NR."], keep="first")

    spezifikation = {}
    for lagerort, norm_nr, pro_lage, voll, typ in zip(
        tabelle["Lagerort"], tabelle["Norm NR."], tabelle["Anzahl Pro Lage"],
        tabelle["Anzahl "], tabelle["Paletten"],
    ):
        spezifikation[(lagerort, norm_nr)] = {
            "anzahl_pro_lage": pro_lage if pd.notna(pro_lage) and pro_lage > 0 else 10,
            "anzahl_volle_palette": voll if pd.notna(voll) and voll > 0 else 10,
            "typ": typ if pd.notna(typ) else "",
        }
    return spezifikation


_PALETTENSPEZIFIKATION = _lade_palettenspezifikation()

# Standardwert, falls ein (Lagerort, Norm-Nr) nicht in Stammdaten vorkommt.
_STANDARD_PALETTE = {"anzahl_pro_lage": 10, "anzahl_volle_palette": 10, "typ": ""}


def _fuellmenge(norm_nr) -> float:
    return bestand_logik.fuellmenge(norm_nr)


def _palettenspezifikation(lagerort: str, norm_nr) -> dict:
    return _PALETTENSPEZIFIKATION.get((lagerort, norm_nr), _STANDARD_PALETTE)


# --- Kundenauftraege -> Rueckstaende / Planbar -------------------------------

def _splitte_auftraege(
    positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame, planungsdatum
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Kundenauftraege vom aeltesten Ladedatum bis zum Planungsdatum, dann
    per bestand_logik.teile_nach_bestand() in (rueckstand, planbar)
    aufgeteilt - dieselbe Funktion, die auch das Dashboard Dispo fuer
    "Rückstand mit Bestand" nutzt (siehe dortige Doku fuer die genaue Regel
    inkl. anteiliger Teilmengen).

    Nutzt bestand_logik.nutzbarer_bestand_je_artikel() (Charge-/Fuellmengen-
    genau, siehe dortige Doku) statt der einfachen Spalte "Bestand
    verfügbar" - eine Charge/Parti-Nr darf nicht mit einer anderen zu einer
    Fuellmenge gemischt werden."""
    fenster = positionen[positionen["Ladedatum"] <= pd.Timestamp(planungsdatum)]
    nutzbar = bestand_logik.nutzbarer_bestand_je_artikel(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    return bestand_logik.teile_nach_bestand(fenster, nutzbar)


def _gruppiere_je_abladestelle_artikel(df: pd.DataFrame) -> pd.DataFrame:
    """Mehrere Positionen derselben Abladestelle+Artikel im Zeitfenster zu
    einer Zeile zusammenfassen (fuer EINEN Kommissionier-/Palettenlauf)."""
    aggregation = {"Menge": ("Offene Menge", "sum"), "Ladedatum": ("Ladedatum", "min")}
    if "VW-Nr" in df.columns:
        # Nur fuer die Bildschirm-Vorschau mitgefuehrt (nicht in der Excel-
        # Vorlage genutzt) - je Norm-Nr immer derselbe Wert, "first" reicht.
        aggregation["VW-Nr"] = ("VW-Nr", "first")
    gruppiert = df.groupby(["Abladestelle", "Norm-Nr"], as_index=False).agg(**aggregation)
    return gruppiert.sort_values(["Abladestelle", "Norm-Nr"]).reset_index(drop=True)


# --- Mengen aufrunden auf volle Füllmenge-Einheiten -------------------------

def _runde_auf_fuellmenge(gruppiert: pd.DataFrame) -> pd.DataFrame:
    df = gruppiert.copy()
    df["Fuellmenge"] = df["Norm-Nr"].apply(_fuellmenge)
    df["Packeinheiten"] = (df["Menge"] / df["Fuellmenge"]).apply(math.ceil)
    df["Menge urspruenglich"] = df["Menge"]
    df["Menge"] = df["Packeinheiten"] * df["Fuellmenge"]
    df["Menge_gerundet"] = df["Menge"] != df["Menge urspruenglich"]
    return df


# --- Mix-Paletten je Abladestelle: Reste nach vollen Paletten kombinieren ---

def _teile_in_paletten_und_rest(zeile, lagerort: str) -> tuple[int, int, dict]:
    spezifikation = _palettenspezifikation(lagerort, zeile["Norm-Nr"])
    kapazitaet = int(spezifikation["anzahl_volle_palette"])
    packeinheiten = int(zeile["Packeinheiten"])
    volle_paletten = packeinheiten // kapazitaet if kapazitaet else 0
    rest = packeinheiten - volle_paletten * kapazitaet
    return volle_paletten, rest, spezifikation


def _plane_abladestelle(gruppe: pd.DataFrame, lagerort: str) -> tuple[list[dict], list[dict]]:
    """Gibt (planungszeilen, dhl_ups_zeilen) fuer eine Abladestelle zurueck.
    planungszeilen: Artikel mit ausreichend Packeinheiten fuer mind. eine
    volle Palette (Reste werden, wenn kombinierbar, einem Artikel der
    Gruppe als Mix-Palette zugeschlagen - sonst zu DHL/UPS).

    WICHTIG: Pro Artikel gibt es je Abladestelle hoechstens EINE Zeile in
    planungszeilen - nie zwei (z. B. "3 Paletten" + separat "6 KLT"
    desselben Artikels). Hat ein Artikel an dieser Abladestelle schon eine
    Zeile (volle Paletten oder ein zuvor zugeordneter Mix-Anteil), wird
    jeder weitere Rest - ob alleinstehend oder mit einem ANDEREN Artikel zu
    einer Mix-Palette kombiniert - dort draufgerechnet statt eine zweite
    Zeile zu erzeugen."""
    planungszeilen: list[dict] = []
    hauptzeile_je_artikel: dict = {}  # Norm-Nr -> deren Zeile in planungszeilen
    offene_reste: list[dict] = []  # Kandidaten fuer Mix-Palette

    for _, zeile in gruppe.iterrows():
        packeinheiten = int(zeile["Packeinheiten"])
        if packeinheiten < MINDEST_PACKEINHEITEN_FUER_PALETTE:
            offene_reste.append({
                "Norm-Nr": zeile["Norm-Nr"], "Menge": zeile["Menge"],
                "Packeinheiten": packeinheiten, "Menge_gerundet": zeile["Menge_gerundet"],
                "angehaengt": False,
            })
            continue

        volle_paletten, rest, spezifikation = _teile_in_paletten_und_rest(zeile, lagerort)
        if volle_paletten > 0:
            kapazitaet = int(spezifikation["anzahl_volle_palette"])
            eintrag = {
                "Norm-Nr": zeile["Norm-Nr"],
                "Menge": volle_paletten * kapazitaet * zeile["Fuellmenge"],
                "Menge_gerundet": zeile["Menge_gerundet"],
                "anzahl_pro_lage": spezifikation["anzahl_pro_lage"],
            }
            planungszeilen.append(eintrag)
            hauptzeile_je_artikel[zeile["Norm-Nr"]] = eintrag
        if rest > 0:
            # VWPAL: ein Rest von genau der Haelfte der Lagen-Kapazitaet
            # (z. B. 10 von 20) soll nicht alleine stehen - bevorzugt
            # auffuellen, daher mit hoeherer Prioritaet (groesster Rest
            # zuerst) in die Kombinationsliste.
            offene_reste.append({
                "Norm-Nr": zeile["Norm-Nr"], "Menge": rest * zeile["Fuellmenge"],
                "Packeinheiten": rest, "Menge_gerundet": True,
                "anzahl_pro_lage": spezifikation["anzahl_pro_lage"],
                "angehaengt": False,
            })

    # Reste absteigend nach Packeinheiten kombinieren (groesster Rest bildet
    # den Grundstock einer Mix-Palette, kleinere Reste werden - soweit die
    # Lagen-Kapazitaet reicht - dazugelegt).
    offene_reste.sort(key=lambda r: r["Packeinheiten"], reverse=True)
    dhl_ups_zeilen: list[dict] = []
    while offene_reste:
        grundstock = offene_reste.pop(0)
        kapazitaet = grundstock.get("anzahl_pro_lage", 10)
        summe = grundstock["Packeinheiten"]
        mix_artikel = [grundstock]
        rest_liste = []
        for kandidat in offene_reste:
            if summe + kandidat["Packeinheiten"] <= kapazitaet:
                summe += kandidat["Packeinheiten"]
                mix_artikel.append(kandidat)
            else:
                rest_liste.append(kandidat)
        offene_reste = rest_liste

        if summe < MINDEST_PACKEINHEITEN_FUER_PALETTE:
            for artikel in mix_artikel:
                dhl_ups_zeilen.append(artikel)
        else:
            # Egal ob der Rest alleine stand oder mit einem anderen Artikel
            # gemischt wurde: hat der Artikel an dieser Abladestelle schon
            # eine Zeile (volle Paletten oder ein frueherer Mix-Anteil),
            # wird hier draufgerechnet statt eine zweite Zeile fuer
            # denselben Artikel zu schreiben - nie zwei Zeilen je Artikel.
            for artikel in mix_artikel:
                hauptzeile = hauptzeile_je_artikel.get(artikel["Norm-Nr"])
                if hauptzeile is not None:
                    hauptzeile["Menge"] += artikel["Menge"]
                    hauptzeile["Menge_gerundet"] = True
                else:
                    eintrag = {
                        "Norm-Nr": artikel["Norm-Nr"], "Menge": artikel["Menge"],
                        "Menge_gerundet": artikel["Menge_gerundet"],
                        "anzahl_pro_lage": kapazitaet,
                    }
                    planungszeilen.append(eintrag)
                    hauptzeile_je_artikel[artikel["Norm-Nr"]] = eintrag

    return planungszeilen, dhl_ups_zeilen


def _teilmenge_kombis(rueckstand: pd.DataFrame, planbar: pd.DataFrame) -> set:
    """(Abladestelle, Norm-Nr)-Kombinationen, die durch die Mengen-Aufteilung
    SOWOHL eine planbare als auch eine Rueckstands-Teilmenge haben."""
    if rueckstand.empty or planbar.empty:
        return set()
    in_rueckstand = set(zip(rueckstand["Abladestelle"], rueckstand["Norm-Nr"]))
    in_planbar = set(zip(planbar["Abladestelle"], planbar["Norm-Nr"]))
    return in_rueckstand & in_planbar


def _baue_planung_und_versand(planbar: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Komplette Planbar-Menge -> (Almanca-Zeilen, DHL/UPS-Zeilen), je
    Abladestelle gruppiert und sortiert, mit Mix-Paletten-Logik."""
    if planbar.empty:
        return [], []
    gruppiert = _gruppiere_je_abladestelle_artikel(planbar)
    gerundet = _runde_auf_fuellmenge(gruppiert)

    alle_planungszeilen: list[dict] = []
    alle_dhl_ups_zeilen: list[dict] = []
    for abladestelle, gruppe in gerundet.groupby("Abladestelle", sort=True):
        planungszeilen, dhl_ups_zeilen = _plane_abladestelle(gruppe, abladestelle)
        for zeile in planungszeilen:
            zeile["Abladestelle"] = abladestelle
            alle_planungszeilen.append(zeile)
        for zeile in dhl_ups_zeilen:
            zeile["Abladestelle"] = abladestelle
            alle_dhl_ups_zeilen.append(zeile)
    return alle_planungszeilen, alle_dhl_ups_zeilen


# --- Rueckstand-Kennzeichnung / erwartete Zugaenge --------------------------

def _rueckstand_seit_je_kombi(planbar: pd.DataFrame, stichtag) -> dict:
    """(Abladestelle, Norm-Nr) -> aeltestes Ladedatum VOR dem Stichtag, fuer
    eingeplante Mengen, die am Stichtag bereits Rueckstand waren (Ladedatum
    vorbei, Ware erst jetzt physisch da). Diese Zeilen werden in der Planung
    markiert: VW-Nr rot, urspruengliches Ladedatum in "Lagerauftrag" (L)."""
    if stichtag is None or planbar.empty:
        return {}
    alt = planbar[planbar["Ladedatum"] < pd.Timestamp(stichtag)]
    if alt.empty:
        return {}
    return alt.groupby(["Abladestelle", "Norm-Nr"])["Ladedatum"].min().to_dict()


def _erwartete_zeilen(
    rueckstand: pd.DataFrame, zugang_vorbereitet: pd.DataFrame | None, planungsdatum
) -> list[dict]:
    """Rueckstaende (physisch nicht gedeckt), fuer die laut ZMM1000 bis
    spaetestens zum Planungsdatum ein Zugang (NRI) eintrifft. Je Artikel wird
    die eintreffende Menge nach Dringlichkeit (aeltestes Ladedatum zuerst) auf
    die Rueckstandszeilen verteilt; gedeckter Teil auf volle Fuellmenge
    aufgerundet. Diese Zeilen kommen als eigener, gelber Bereich unter die
    Planung - nur als Erinnerung, NICHT in Paletten-/Gewichtssumme (E2/H2)."""
    if rueckstand.empty or zugang_vorbereitet is None or zugang_vorbereitet.empty:
        return []
    zugaenge = zugang_vorbereitet[
        zugang_vorbereitet["Ankunft gerechnet"] <= pd.Timestamp(planungsdatum)
    ].sort_values("Ankunft gerechnet")
    if zugaenge.empty:
        return []
    gruppiert = _gruppiere_je_abladestelle_artikel(rueckstand)
    zeilen: list[dict] = []
    for norm_nr, zg in zugaenge.groupby("Norm-Nr"):
        # Warteschlange der eintreffenden NRIs (frueheste zuerst) mit Restmenge
        warteschlange = [dict(z, Rest=float(z["Menge"])) for z in zg.to_dict("records")]
        kandidaten = gruppiert[gruppiert["Norm-Nr"] == norm_nr].sort_values(["Ladedatum", "Abladestelle"])
        for _, r in kandidaten.iterrows():
            offen, genutzt = float(r["Menge"]), []
            while offen > 0 and warteschlange:
                z = warteschlange[0]
                nimm = min(offen, z["Rest"])
                z["Rest"] -= nimm
                offen -= nimm
                genutzt.append(z)
                if z["Rest"] <= 0:
                    warteschlange.pop(0)
            menge = float(r["Menge"]) - offen
            if menge <= 0:
                break
            info = "; ".join(_formatiere_zugang_info(z) for z in genutzt)
            f = _fuellmenge(norm_nr)
            gerundet = math.ceil(menge / f) * f
            zeilen.append({
                "Abladestelle": r["Abladestelle"], "Norm-Nr": norm_nr, "Menge": gerundet,
                "Menge_gerundet": gerundet != menge, "Ladedatum": r["Ladedatum"],
                "Zugang Info": info,
            })
    zeilen.sort(key=lambda z: (str(z["Abladestelle"]), z["Norm-Nr"]))
    return zeilen


# --- In die Vorlage schreiben -------------------------------------------

def _farbige_schrift(font, farbe: str) -> Font:
    return Font(name=font.name, size=font.size, bold=font.bold, italic=font.italic, color=farbe)


def _schreibe_ladedatum(zelle, ladedatum, zusatz: str | None = None) -> None:
    """Urspruengliches Ladedatum in "Lagerauftrag" (L). Als echtes Datum
    (nicht als Text "30.10.2026"), damit der Auftragszaehler B2 der Vorlage
    (zaehlt Eintraege, die mit "3" beginnen und 10 Zeichen lang sind) Daten
    nicht faelschlich als Lagerauftrag mitzaehlt."""
    if zusatz:
        zelle.value = f"{zusatz} · {pd.Timestamp(ladedatum):%d.%m.%Y}"
    else:
        zelle.value = pd.Timestamp(ladedatum).to_pydatetime()
        zelle.number_format = "DD.MM.YYYY"


def _benoetigte_zeilen(zeilen: list[dict]) -> int:
    """Zeilen inkl. Leerzeilen zwischen Abladestellen-Gruppen."""
    if not zeilen:
        return 0
    wechsel = sum(1 for a, b in zip(zeilen, zeilen[1:]) if a["Abladestelle"] != b["Abladestelle"])
    return len(zeilen) + wechsel


def _schreibe_zeilen(
    ws, zeilen: list[dict], *, rot_wenn_gerundet: bool, gruen_fuellung: bool,
    teilmenge_kombis: set = frozenset(), hinweis_artikel: set = frozenset(),
    rueckstand_seit: dict | None = None, erwartet: bool = False,
    start_zeile: int = ERSTE_DATENZEILE,
) -> int:
    """Schreibt die Zeilen ab start_zeile, gibt die naechste freie Zeile zurueck.

    rueckstand_seit: (Abladestelle, Norm-Nr) -> urspruengliches Ladedatum fuer
    eingeplante Rueckstaende (VW-Nr rot + Ladedatum in L).
    erwartet=True: Bereich "Zugang erwartet" - A bis T gelb, Ladedatum in L,
    NRI-Info in M, Kennzeichnung in Z (nicht in E2/H2-Summe)."""
    rueckstand_seit = rueckstand_seit or {}
    aktuelle_abladestelle = None
    zeile_nr = start_zeile
    for eintrag in zeilen:
        if aktuelle_abladestelle is not None and eintrag["Abladestelle"] != aktuelle_abladestelle:
            zeile_nr += 1  # Leerzeile zwischen Abladestellen-Gruppen
        aktuelle_abladestelle = eintrag["Abladestelle"]
        kombi = (eintrag["Abladestelle"], eintrag["Norm-Nr"])

        ws.cell(row=zeile_nr, column=SPALTE_LAGERORT, value=eintrag["Abladestelle"])
        ws.cell(row=zeile_nr, column=SPALTE_NORM_NR, value=int(eintrag["Norm-Nr"]))
        menge_zelle = ws.cell(row=zeile_nr, column=SPALTE_MENGE, value=eintrag["Menge"])

        if rot_wenn_gerundet and eintrag.get("Menge_gerundet"):
            menge_zelle.font = _farbige_schrift(menge_zelle.font, ROT)
        if gruen_fuellung:
            for spalte in (SPALTE_LAGERORT, SPALTE_NORM_NR, SPALTE_MENGE):
                ws.cell(row=zeile_nr, column=spalte).fill = GRUEN_FUELLUNG

        lagerauftrag = ws.cell(row=zeile_nr, column=SPALTE_LAGERAUFTRAG)
        mgbekleyen = eintrag["Norm-Nr"] in hinweis_artikel
        if erwartet:
            for spalte in range(1, GELB_BIS_SPALTE + 1):
                ws.cell(row=zeile_nr, column=spalte).fill = GELB_FUELLUNG
            _schreibe_ladedatum(lagerauftrag, eintrag["Ladedatum"])
            ws.cell(row=zeile_nr, column=SPALTE_LIEFERSCHEIN, value=eintrag.get("Zugang Info", ""))
            ws.cell(row=zeile_nr, column=SPALTE_HINWEIS, value=ERWARTET_MARKER)
            zeile_nr += 1
            continue

        if kombi in teilmenge_kombis:
            # Nur ein Teil der urspruenglich offenen Menge war durch Bestand
            # gedeckt - der Rest steht (mit derselben Abladestelle/Artikel)
            # zusaetzlich in den Rueckstaenden.
            ws.cell(row=zeile_nr, column=SPALTE_HINWEIS, value="Teilmenge, Prüfen")
        if kombi in rueckstand_seit:
            # War Rueckstand, Ware ist jetzt da: VW-Nr (Formelzelle F) rot,
            # urspruengliches Ladedatum in L.
            vw = ws.cell(row=zeile_nr, column=SPALTE_VW_NR)
            vw.font = _farbige_schrift(vw.font, ROT)
            _schreibe_ladedatum(lagerauftrag, rueckstand_seit[kombi], "MGBEKLEYEN" if mgbekleyen else None)
        elif mgbekleyen:
            # Nutzbarer Bestand liegt ausschliesslich am Lagerort MGBEKLEYEN
            # (Wareneingang) - normal eingeplant, nur als Hinweis in L.
            lagerauftrag.value = "MGBEKLEYEN"

        zeile_nr += 1
    return zeile_nr


def _setze_summenformeln(ws) -> None:
    """E2 (Paletten gesamt) und H2 (Gesamtgewicht) ohne die Zeilen des
    Bereichs "Zugang erwartet" (Kennzeichnung in Spalte Z)."""
    ws["E2"] = SUMME_PALETTEN
    ws["H2"] = SUMME_GEWICHT


def _zugang_warteschlangen_je_artikel(zugang_vorbereitet: pd.DataFrame | None) -> dict:
    """Norm-Nr -> Liste der noch nicht zugeordneten Zugaenge (Referenz/NRI,
    Ankunft gerechnet, Menge), sortiert nach Ankunft aufsteigend - fuer die
    Zuordnung "naechster Zugang" je Rueckstandszeile."""
    if zugang_vorbereitet is None or zugang_vorbereitet.empty:
        return {}
    warteschlangen: dict = {}
    for norm_nr, gruppe in zugang_vorbereitet.sort_values("Ankunft gerechnet").groupby("Norm-Nr"):
        warteschlangen[norm_nr] = gruppe[["Referenz", "Ankunft gerechnet", "Menge"]].to_dict("records")
    return warteschlangen


def _formatiere_zugang_info(zugang: dict) -> str:
    ankunft = pd.Timestamp(zugang["Ankunft gerechnet"])
    menge = f"{zugang['Menge']:,.0f}".replace(",", ".")
    referenz = zugang["Referenz"] or "(ohne Referenz)"
    return f"{referenz} – {ankunft:%d.%m.%Y} – {menge} Stk"


def _ordne_zugaenge_zu(gruppiert: pd.DataFrame, zugang_warteschlangen: dict) -> pd.DataFrame:
    """Je Artikel, nach Dringlichkeit (aeltestes Ladedatum zuerst), den
    naechsten noch freien Zugang zuordnen - auch wenn er erst nach dem
    Planungsdatum ankommt (nur als Information, zaehlt nicht als planbar)."""
    gruppiert = gruppiert.copy()
    gruppiert["Zugang Info"] = ""
    for norm_nr in gruppiert["Norm-Nr"].unique():
        warteschlange = list(zugang_warteschlangen.get(norm_nr, []))
        if not warteschlange:
            continue
        reihenfolge = gruppiert[gruppiert["Norm-Nr"] == norm_nr].sort_values("Ladedatum").index
        for idx in reihenfolge:
            if not warteschlange:
                break
            gruppiert.loc[idx, "Zugang Info"] = _formatiere_zugang_info(warteschlange.pop(0))
    return gruppiert


def _rueckstand_anzeige(rueckstand: pd.DataFrame, zugang_warteschlangen: dict) -> pd.DataFrame:
    """Rueckstaende gruppiert + Zugang-Info zugeordnet - EINE Berechnung,
    die sowohl ins Excel-Blatt "Rueckstaende" geschrieben als auch als
    Bildschirm-Vorschau im Tab angezeigt wird (siehe render_planung_tab)."""
    gruppiert = _gruppiere_je_abladestelle_artikel(rueckstand)
    mit_zugang = _ordne_zugaenge_zu(gruppiert, zugang_warteschlangen)
    # Artikelweise (Norm-Nr aufsteigend), je Artikel aeltestes Ladedatum zuerst.
    return mit_zugang.sort_values(["Norm-Nr", "Ladedatum", "Abladestelle"]).reset_index(drop=True)


def _schreibe_rueckstaende(ws, gruppiert: pd.DataFrame) -> int:
    """Schreibt die (bereits gruppierten, mit Zugang-Info versehenen)
    Rueckstaende artikelweise (Norm-Nr aufsteigend) in die Vorlage, gibt die Anzahl Zeilen mit zugeordnetem
    Zugang zurueck (fuer die Kennzahlen-Anzeige)."""
    zeile_nr = ERSTE_DATENZEILE
    aktueller_artikel = None
    rote_schrift = Font(size=15, color=ROT)
    mit_zugang = 0
    for _, eintrag in gruppiert.iterrows():
        if aktueller_artikel is not None and eintrag["Norm-Nr"] != aktueller_artikel:
            zeile_nr += 1  # Leerzeile zwischen Artikeln
        aktueller_artikel = eintrag["Norm-Nr"]

        ws.cell(row=zeile_nr, column=3, value=eintrag["Abladestelle"]).font = rote_schrift
        ws.cell(row=zeile_nr, column=7, value=int(eintrag["Norm-Nr"])).font = rote_schrift
        ws.cell(row=zeile_nr, column=9, value=eintrag["Menge"]).font = rote_schrift
        # Ladedatum (fuer Lageraufträge) in die Spalte "Lagerauftrag" (L).
        ws.cell(row=zeile_nr, column=12, value=eintrag["Ladedatum"].strftime("%d.%m.%Y")).font = rote_schrift
        # Naechster noch nicht verplanter Zugang (NRI/Datum/Menge) in "Lieferschein" (M).
        if eintrag["Zugang Info"]:
            ws.cell(row=zeile_nr, column=13, value=eintrag["Zugang Info"]).font = rote_schrift
            mit_zugang += 1
        zeile_nr += 1
    return mit_zugang


def _palettenspezifikation_abdeckung(planbar: pd.DataFrame) -> tuple[int, int]:
    """(gefunden, gesamt) (Abladestelle, Norm-Nr)-Kombinationen mit echter
    Palettenspezifikation in Stammdaten vs. Standard-Fallback (10/10)."""
    if planbar.empty:
        return 0, 0
    kombinationen = planbar[["Abladestelle", "Norm-Nr"]].drop_duplicates()
    gefunden = sum(
        1 for _, r in kombinationen.iterrows()
        if (r["Abladestelle"], r["Norm-Nr"]) in _PALETTENSPEZIFIKATION
    )
    return gefunden, len(kombinationen)


def erstelle_planungsdatei(
    positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame,
    zugang_vorbereitet: pd.DataFrame, planungsdatum, stichtag=None,
) -> tuple[bytes, dict, pd.DataFrame]:
    """stichtag: Datum der SAP-Daten. Eingeplante Mengen mit Ladedatum davor
    waren Rueckstand und werden markiert (VW-Nr rot, Ladedatum in L)."""
    rueckstand, planbar = _splitte_auftraege(positionen, bestand_je_charge, planungsdatum)
    planungszeilen, dhl_ups_zeilen = _baue_planung_und_versand(planbar)
    palette_gefunden, palette_gesamt = _palettenspezifikation_abdeckung(planbar)
    zugang_warteschlangen = _zugang_warteschlangen_je_artikel(zugang_vorbereitet)
    teilmengen = _teilmenge_kombis(rueckstand, planbar)
    rueckstand_anzeige = _rueckstand_anzeige(rueckstand, zugang_warteschlangen)
    hinweis_artikel = bestand_logik.artikel_mit_lagerort_hinweis(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    rueckstand_seit = _rueckstand_seit_je_kombi(planbar, stichtag)
    erwartet = _erwartete_zeilen(rueckstand, zugang_vorbereitet, planungsdatum)

    wb = openpyxl.load_workbook(VORLAGE_DATEI)
    naechste = _schreibe_zeilen(
        wb["Almanca"], planungszeilen, rot_wenn_gerundet=True, gruen_fuellung=False,
        teilmenge_kombis=teilmengen, hinweis_artikel=hinweis_artikel,
        rueckstand_seit=rueckstand_seit,
    )
    if erwartet:
        # Eigener Bereich ganz unten unter den geplanten Zeilen.
        start = naechste + 1 if planungszeilen else ERSTE_DATENZEILE
        _schreibe_zeilen(
            wb["Almanca"], erwartet, rot_wenn_gerundet=True, gruen_fuellung=False,
            erwartet=True, start_zeile=start,
        )
    _setze_summenformeln(wb["Almanca"])
    _schreibe_zeilen(
        wb["DHL UPS"], dhl_ups_zeilen, rot_wenn_gerundet=False, gruen_fuellung=True,
        teilmenge_kombis=teilmengen, hinweis_artikel=hinweis_artikel,
        rueckstand_seit=rueckstand_seit,
    )
    rueckstand_mit_zugang = _schreibe_rueckstaende(wb["Rückstände"], rueckstand_anzeige)
    wb["Almanca"]["M2"] = pd.Timestamp(planungsdatum).strftime("%d.%m. VW")

    puffer = io.BytesIO()
    wb.save(puffer)
    puffer.seek(0)

    kennzahlen = {
        "rueckstand_artikel": rueckstand["Norm-Nr"].nunique(),
        "rueckstand_zeilen": len(rueckstand_anzeige),
        "rueckstand_mit_zugang": rueckstand_mit_zugang,
        "planung_zeilen": len(planungszeilen),
        "dhl_ups_zeilen": len(dhl_ups_zeilen),
        "rueckstand_eingeplant": sum(
            1 for z in planungszeilen + dhl_ups_zeilen
            if (z["Abladestelle"], z["Norm-Nr"]) in rueckstand_seit
        ),
        "erwartet_zeilen": len(erwartet),
        "palette_spezifikation_gefunden": palette_gefunden,
        "palette_spezifikation_gesamt": palette_gesamt,
    }
    return puffer.getvalue(), kennzahlen, rueckstand_anzeige


# --- Rueckstaende in eine bestehende Planung vorziehen ------------------------

def _normiere_lagerort(wert) -> str:
    if wert is None:
        return ""
    if isinstance(wert, float) and wert.is_integer():
        wert = int(wert)
    return str(wert).strip()


def _normiere_norm_nr(wert):
    try:
        return int(float(wert))
    except (TypeError, ValueError):
        return None


def _ist_erwartet(wert) -> bool:
    return isinstance(wert, str) and wert.startswith("Erwartet")


def _belegte_zeilen(ws) -> list[int]:
    """Datenzeilen (ab Zeile 5) mit Eintrag in Lagerort, Norm-Nr oder Menge."""
    return [
        r for r in range(ERSTE_DATENZEILE, ws.max_row + 1)
        if any(ws.cell(row=r, column=c).value not in (None, "")
               for c in (SPALTE_LAGERORT, SPALTE_NORM_NR, SPALTE_MENGE))
    ]


def vorhandene_kombinationen(datei: bytes) -> set:
    """(Lagerort, Norm-Nr), die in einer bestehenden Planungsdatei bereits in
    "Almanca" oder "DHL UPS" stehen (egal welche Menge)."""
    wb = openpyxl.load_workbook(io.BytesIO(datei))
    kombis = set()
    for blatt in ("Almanca", "DHL UPS"):
        if blatt not in wb.sheetnames:
            continue
        ws = wb[blatt]
        for r in _belegte_zeilen(ws):
            norm_nr = _normiere_norm_nr(ws.cell(row=r, column=SPALTE_NORM_NR).value)
            if norm_nr is not None:
                kombis.add((_normiere_lagerort(ws.cell(row=r, column=SPALTE_LAGERORT).value), norm_nr))
    return kombis


def vorzieh_kandidaten(
    positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame, stichtag,
    bestehende_datei: bytes | None = None,
) -> pd.DataFrame:
    """Rueckstaende (Ladedatum vor dem Stichtag), fuer die JETZT physischer
    Bestand da ist (z. B. neu eingetroffene Ware) - Kandidaten, um sie in eine
    bereits erstellte Planung vorzuziehen. Dieselbe Bestandsregel wie in der
    Planung (Charge/Fuellmenge, ohne OUT1, aelteste Ladedaten zuerst).
    Kombinationen, die schon in der bestehenden Datei stehen, entfallen."""
    _rueckstand, planbar = _splitte_auftraege(positionen, bestand_je_charge, stichtag)
    planbar = planbar[planbar["Ladedatum"] < pd.Timestamp(stichtag)]
    spalten = ["Abladestelle", "Norm-Nr", "VW-Nr", "Menge", "Packeinheiten", "Ladedatum", "Ziel", "Menge_gerundet"]
    if planbar.empty:
        return pd.DataFrame(columns=spalten)
    kandidaten = _runde_auf_fuellmenge(_gruppiere_je_abladestelle_artikel(planbar))
    if bestehende_datei:
        vorhanden = vorhandene_kombinationen(bestehende_datei)
        schon_drin = [
            (_normiere_lagerort(a), int(n)) in vorhanden
            for a, n in zip(kandidaten["Abladestelle"], kandidaten["Norm-Nr"])
        ]
        kandidaten = kandidaten[[not x for x in schon_drin]]
    kandidaten = kandidaten.copy()
    if "VW-Nr" not in kandidaten.columns:
        kandidaten["VW-Nr"] = ""
    kandidaten["Ziel"] = [
        "Almanca" if pe >= MINDEST_PACKEINHEITEN_FUER_PALETTE else "DHL UPS"
        for pe in kandidaten["Packeinheiten"]
    ]
    return kandidaten.sort_values(["Abladestelle", "Norm-Nr"])[spalten].reset_index(drop=True)


def _kopiere_stil(quelle, ziel) -> None:
    ziel.font = copy(quelle.font)
    ziel.fill = copy(quelle.fill)
    ziel.number_format = quelle.number_format


def _verschiebe_bereich(ws, von: int, bis: int, versatz: int) -> None:
    """Zeilen von..bis (nur Eingabespalten + Fuellfarbe A-T/Z) um versatz
    Zeilen nach unten verschieben - die Formelspalten der Vorlage stehen in
    jeder Zeile gleich und bleiben unberuehrt. Die frei werdenden Zellen
    bekommen den Stil einer leeren Vorlagenzeile."""
    leer = bis + versatz + 5
    spalten = sorted(set(EINGABE_SPALTEN) | set(range(1, GELB_BIS_SPALTE + 1)))
    for r in range(bis, von - 1, -1):
        for c in spalten:
            alt = ws.cell(row=r, column=c)
            neu = ws.cell(row=r + versatz, column=c)
            if c in EINGABE_SPALTEN:
                neu.value = alt.value
                alt.value = None
            _kopiere_stil(alt, neu)
            _kopiere_stil(ws.cell(row=leer, column=c), alt)


def ergaenze_bestehende_planung(datei: bytes, auswahl: pd.DataFrame) -> bytes:
    """Ausgewaehlte Kandidaten (Spalten wie vorzieh_kandidaten(), "Ziel" =
    Almanca/DHL UPS) in eine bestehende Planungsdatei schreiben:
    Almanca direkt unter die letzte geplante Zeile (ein evtl. vorhandener
    gelber Bereich "Zugang erwartet" rueckt nach unten), DHL UPS ans Ende.
    Markierung wie in der Planung: VW-Nr rot, urspruengliches Ladedatum in L.
    Alles andere in der Datei (manuelle Eintraege, Lagerauftraege) bleibt."""
    wb = openpyxl.load_workbook(io.BytesIO(datei))
    for blatt in ("Almanca", "DHL UPS"):
        teil = auswahl[auswahl["Ziel"] == blatt].sort_values(["Abladestelle", "Norm-Nr"])
        if teil.empty or blatt not in wb.sheetnames:
            continue
        ws = wb[blatt]
        zeilen = teil.to_dict("records")
        seit = {(z["Abladestelle"], z["Norm-Nr"]): z["Ladedatum"] for z in zeilen}
        belegt = _belegte_zeilen(ws)
        geplant = [r for r in belegt if not _ist_erwartet(ws.cell(row=r, column=SPALTE_HINWEIS).value)]
        erwartet = [r for r in belegt if r not in geplant]
        start = max(geplant) + 2 if geplant else ERSTE_DATENZEILE
        if erwartet and blatt == "Almanca":
            ende_neu = start + _benoetigte_zeilen(zeilen)  # erste Zeile nach dem neuen Block
            versatz = (ende_neu + 1) - min(erwartet)  # eine Leerzeile Abstand
            if versatz > 0:
                _verschiebe_bereich(ws, min(erwartet), max(erwartet), versatz)
        _schreibe_zeilen(
            ws, zeilen, rot_wenn_gerundet=(blatt == "Almanca"), gruen_fuellung=(blatt == "DHL UPS"),
            rueckstand_seit=seit, start_zeile=start,
        )
        if blatt == "Almanca":
            _setze_summenformeln(ws)
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


# --- Streamlit-Oberflaeche ---------------------------------------------------

def render_planung_tab() -> None:
    st.title("Planung Erstellung")
    st.markdown(
        '<span class="vwai-badge">✨ Kommissionier-/Palettenplanung</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Erster Testaufbau. Nutzt dieselben Daten wie Dashboard Dispo "
        "(Bedarf + Bestand + Zugänge) - dort bitte zuerst die SAP-Exporte "
        "hochladen. Planbar ist nur, was der aktuell PHYSISCH vorhandene "
        "Bestand deckt - je Charge/Parti-Nr einzeln auf volle Füllmengen "
        "abgerundet (keine Mischung verschiedener Chargen in einer "
        "Füllmenge), ohne Lagerort OUT1 (bereits für Versand bereitgestellt)."
        " Bestand am Lagerort MGBEKLEYEN (Wareneingang, Entnahme noch nicht "
        "möglich) wird normal mitgezählt/eingeplant, aber zur Info mit "
        "\"MGBEKLEYEN\" in Spalte L markiert."
        " Unterwegs befindliche Zugänge zählen hier nicht als verfügbar "
        "(anders als die Fehlmenge im Dashboard Dispo) und werden "
        "stattdessen als Info (Referenz/NRI, Ankunftsdatum, Menge) in die "
        "jeweilige Rückstandszeile geschrieben. Die Mix-Paletten-"
        "Zusammenlegung ist eine Heuristik (größte Reste zuerst kombinieren)"
        " - bitte mit echten Tagesdaten prüfen."
    )
    st.caption(
        "Markierungen in \"Almanca\"/\"DHL UPS\": eingeplante Mengen, die "
        "bereits Rückstand waren (Ladedatum vor dem Datenstand, Ware jetzt da) "
        "→ VW-Nr rot, ursprüngliches Ladedatum in Spalte L. Rückstände, für die "
        "bis zum Planungsdatum eine NRI eintrifft → eigener gelber Bereich (A–T) "
        "unter der Planung, NICHT in Paletten gesamt (E2) / Gesamtgewicht (H2). "
        "Trifft die Ware ein und wird mitgenommen: Text in Spalte Z löschen, "
        "dann zählt die Zeile mit."
    )

    daten = st.session_state.get("dispo_daten")
    if not daten:
        st.info("Bitte zuerst im Dashboard Dispo SAP-Exporte hochladen.")
        return

    planungsdatum = st.date_input(
        "Planungsdatum (Kundenauftraege vom aeltesten Ladedatum bis hierhin)",
        value=daten["stichtag"],
        key="planung_datum",
    )

    if st.button("📋 Planung erstellen", key="planung_erstellen"):
        with st.spinner("Planung wird erstellt..."):
            inhalt, kennzahlen, rueckstand_anzeige = erstelle_planungsdatei(
                daten["positionen"], daten.get("bestand_je_charge"),
                daten.get("zugang"), planungsdatum, stichtag=daten["stichtag"],
            )
        st.session_state["planung_datei"] = inhalt
        st.session_state["planung_kennzahlen"] = kennzahlen
        st.session_state["planung_rueckstand_anzeige"] = rueckstand_anzeige
        st.session_state["planung_erstellt_fuer"] = planungsdatum

    kennzahlen = st.session_state.get("planung_kennzahlen")
    if not kennzahlen or st.session_state.get("planung_erstellt_fuer") != planungsdatum:
        st.divider()
        _render_vorziehen(daten)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artikel im Rückstand", kennzahlen["rueckstand_artikel"])
    c2.metric("Planungszeilen (Almanca)", kennzahlen["planung_zeilen"])
    palette_gefunden = kennzahlen["palette_spezifikation_gefunden"]
    palette_gesamt = kennzahlen["palette_spezifikation_gesamt"]
    c4.metric(
        "Palettentyp bekannt (Stammdaten)",
        f"{palette_gefunden} von {palette_gesamt}" if palette_gesamt else "–",
    )
    if palette_gesamt and palette_gefunden < palette_gesamt:
        st.caption(
            f"⚠️ Für {palette_gesamt - palette_gefunden} von {palette_gesamt} "
            "Abladestelle/Artikel-Kombinationen steht keine Palettenspezifikation "
            "in Stammdaten - dort wurde der Standard (10 Stück/Lage, 10 Stück/"
            "volle Palette) angenommen. Bei echten VWPAL-Kombinationen (20/Lage) "
            "kann die Mix-Paletten-Zusammenlegung dadurch zu frueh in DHL/UPS "
            "ausweichen, statt die hoehere Kapazitaet zu nutzen."
        )
    c3.metric("Zeilen DHL/UPS", kennzahlen["dhl_ups_zeilen"])

    eingeplant = kennzahlen.get("rueckstand_eingeplant", 0)
    erwartet_zeilen = kennzahlen.get("erwartet_zeilen", 0)
    if eingeplant or erwartet_zeilen:
        st.caption(
            f"🔴 {eingeplant} eingeplante Zeile(n) waren Rückstand und sind jetzt "
            f"durch Bestand gedeckt (VW-Nr rot, Ladedatum in L). "
            f"🟡 {erwartet_zeilen} Zeile(n) im gelben Bereich \"Zugang erwartet\" "
            "(NRI trifft bis zum Planungsdatum ein, nicht in E2/H2)."
        )

    rueckstand_zeilen = kennzahlen.get("rueckstand_zeilen", 0)
    rueckstand_mit_zugang = kennzahlen.get("rueckstand_mit_zugang", 0)
    if rueckstand_zeilen:
        st.caption(
            f"ℹ️ {rueckstand_mit_zugang} von {rueckstand_zeilen} Rückstandszeilen "
            "haben einen zugeordneten nächsten Zugang (Spalte \"Lieferschein\": "
            "Referenz/NRI, Ankunftsdatum, Menge) - auch wenn dieser erst nach "
            "dem Planungsdatum ankommt. Die übrigen Zeilen haben aktuell keinen "
            "bekannten Zugang in ZMM1000."
        )

    st.download_button(
        "📥 Planungsdatei herunterladen",
        data=st.session_state["planung_datei"],
        file_name=f"Planung_{pd.Timestamp(planungsdatum):%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="planung_download",
    )

    st.divider()
    _render_rueckstand_vorschau(st.session_state.get("planung_rueckstand_anzeige"), planungsdatum)
    st.divider()
    _render_vorziehen(daten)


def _render_vorziehen(daten: dict) -> None:
    """Rueckstaende mit jetzt vorhandener Ware in eine BEREITS erstellte
    Planungsdatei vorziehen (frueher einplanen)."""
    with st.expander("⏩ Rückstände mit neu eingetroffener Ware in bestehende Planung vorziehen"):
        st.caption(
            "Für Rückstände (Ladedatum vor dem Datenstand), für die jetzt Bestand "
            "da ist. Bestehende Planungsdatei hochladen, Zeilen auswählen - sie "
            "werden unter die geplanten Zeilen geschrieben (VW-Nr rot, Ladedatum "
            "in L), ein gelber Bereich rückt nach unten. Alles andere in der Datei "
            "bleibt unverändert. Artikel/Lagerort, die schon in der Datei stehen, "
            "werden nicht angeboten."
        )
        datei = st.file_uploader(
            "Bestehende Planungsdatei (.xlsx)", type=["xlsx"], key="planung_vorziehen_datei"
        )
        if not datei:
            return
        inhalt = datei.getvalue()
        try:
            kandidaten = vorzieh_kandidaten(
                daten["positionen"], daten.get("bestand_je_charge"), daten["stichtag"], inhalt
            )
        except Exception as fehler:  # defekte/fremde Datei
            st.error(f"Datei konnte nicht gelesen werden: {fehler}")
            return
        if kandidaten.empty:
            st.success("Keine Rückstände mit jetzt vorhandener Ware, die noch nicht in dieser Planung stehen.")
            return
        tabelle = kandidaten.copy()
        tabelle.insert(0, "Vorziehen", True)
        tabelle["Ladedatum"] = tabelle["Ladedatum"].dt.date
        bearbeitet = st.data_editor(
            tabelle.drop(columns=["Menge_gerundet"]),
            hide_index=True,
            use_container_width=True,
            disabled=["Abladestelle", "Norm-Nr", "VW-Nr", "Menge", "Packeinheiten", "Ladedatum"],
            column_config={
                "Ziel": st.column_config.SelectboxColumn(options=["Almanca", "DHL UPS"], required=True),
                "Ladedatum": st.column_config.DateColumn("Urspr. Ladedatum", format="DD.MM.YYYY"),
                "Menge": st.column_config.NumberColumn(format="%d"),
            },
            key="planung_vorziehen_editor",
        )
        gewaehlt = bearbeitet["Vorziehen"].astype(bool).to_numpy()
        auswahl = kandidaten[gewaehlt].copy()
        auswahl["Ziel"] = bearbeitet.loc[gewaehlt, "Ziel"].to_numpy()
        if auswahl.empty:
            return
        neu = ergaenze_bestehende_planung(inhalt, auswahl)
        name = Path(datei.name).stem
        st.download_button(
            f"📥 Planung mit {len(auswahl)} vorgezogenen Zeile(n) herunterladen",
            data=neu,
            file_name=f"{name}_ergaenzt.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="planung_vorziehen_download",
        )


def _tabellenhoehe(anzahl_zeilen: int) -> int:
    return 35 * max(anzahl_zeilen, 1) + 40


def _render_rueckstand_vorschau(rueckstand_anzeige: pd.DataFrame | None, planungsdatum) -> None:
    """Direkte Vorschau der Rückstände fuer das gewaehlte Planungsdatum -
    ohne die Excel-Datei oeffnen zu muessen. Damit nichts "durchrutscht":
    auch Artikel, die am heutigen Stichtag noch kein Rückstand sind, aber
    bis zum Planungsdatum faellig werden, erscheinen hier (anders als
    "Rückstand mit Bestand" im Dashboard Dispo, das auf den heutigen
    Stichtag begrenzt ist)."""
    st.markdown(f"**Rückstände bis {pd.Timestamp(planungsdatum):%d.%m.%Y}**")
    if rueckstand_anzeige is None or rueckstand_anzeige.empty:
        st.success(
            "Keine Rückstände bis zu diesem Planungsdatum - alles ist durch "
            "Bestand gedeckt."
        )
        return

    anzeige = rueckstand_anzeige.copy()
    suche = st.text_input(
        "🔍 Suche (Norm-Nr / VW-Nr / Abladestelle)", key="planung_rueckstand_suche"
    )
    if suche:
        treffer = pd.Series(False, index=anzeige.index)
        for spalte in ["Norm-Nr", "VW-Nr", "Abladestelle"]:
            if spalte in anzeige.columns:
                treffer |= anzeige[spalte].astype(str).str.contains(suche, case=False, na=False)
        anzeige = anzeige[treffer]

    spalten = [s for s in ["Norm-Nr", "VW-Nr", "Abladestelle", "Menge", "Ladedatum", "Zugang Info"]
               if s in anzeige.columns]
    anzeige = anzeige[spalten].copy()
    anzeige["Ladedatum"] = anzeige["Ladedatum"].dt.strftime("%d.%m.%Y")
    anzeige["Menge"] = anzeige["Menge"].apply(lambda v: f"{v:,.0f}".replace(",", "."))
    st.dataframe(
        anzeige,
        hide_index=True,
        use_container_width=True,
        height=_tabellenhoehe(len(anzeige)),
        column_config={"VW-Nr": st.column_config.TextColumn(width=110)},
        key="planung_rueckstand_tabelle",
    )
