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
  (ganze KLT/Packeinheiten), angepasste Menge in roter Schrift - aber je
  Artikel nie ueber die nutzbaren KLT hinaus (sonst je Abladestelle bis zu
  einer KLT zu viel). Reicht der Bestand nicht, wird die juengste Zeile
  gekuerzt ("Bestand reicht nur fuer X KLT" in Z), der Rest wird Rueckstand.
- Packeinheiten < 5 je Artikel -> komplette Zeile zu "DHL UPS" (A bis T
  gruen ausgefuellt), da zu wenig fuer eine eigene Palette.
- Artikel mit < 5 KLT werden je Abladestelle
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
  eine NRI eintrifft (Ware noch nicht da): im Blatt "Rückstände" A bis T
  gelb, in M genau die NRI(s), die die Zeile decken; deckt die NRI nur einen
  Teil, steht das in Z. Die Planung ("Almanca", E2/H2) bleibt unberuehrt.
- Paletten (Stand 04.11.): Reste werden je LAGE bestimmt - liegen auf der
  angefangenen obersten Lage weniger als 5 KLT, kommen sie von der Palette
  und gehen zu DHL UPS.
  Geplante Mix-Paletten stehen sichtbar in der Datei (N Palettentyp, Q
  Anzahl in der Zeile mit dem groessten Anteil, Erklaerung in Z), weil die
  Excel-Formeln je Zeile rechnen und Mix-Paletten nicht kennen.
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
SPALTE_LAGERAUFTRAG, SPALTE_LIEFERSCHEIN = 12, 13
SPALTE_PALETTEN_TYP, SPALTE_PALETTEN_ANZAHL, SPALTE_HINWEIS = 14, 17, 26
GELB_BIS_SPALTE = 20  # A bis T
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


def _lade_klt_art() -> tuple[dict, dict]:
    """KLT-Art je (Lagerort, Norm-Nr) - dieselbe Reihenfolge wie Formel R der
    Vorlage: zuerst Stammdaten Spalte "KLT Art", sonst "SAP Format Neu"
    (Lagerort -> SAP-Nr ueber "Maliteslimalan", Ambalajlama Cesidi 3:
    K810 = 003147 klein, K811 = 004147 gross). Rueckgabe (stammdaten, sap)."""
    def code(wert) -> str:
        try:
            return f"{int(float(wert)):06d}"
        except (TypeError, ValueError):
            return ""
    stamm_art, sap_art = {}, {}
    try:
        stamm = pd.read_excel(VORLAGE_DATEI, sheet_name="Stammdaten")
        for lagerort, norm_nr, art in zip(stamm["Lagerort"], stamm["Norm NR."], stamm["KLT Art"]):
            norm_nr = pd.to_numeric(norm_nr, errors="coerce")  # z. B. "B1017" ueberspringen
            if pd.notna(lagerort) and pd.notna(norm_nr) and code(art):
                stamm_art.setdefault((str(lagerort).strip(), int(norm_nr)), code(art))
        mali = pd.read_excel(VORLAGE_DATEI, sheet_name="Maliteslimalan")
        sap_nr = {str(a).strip(): int(b) for a, b in zip(mali.iloc[:, 0], mali.iloc[:, 1]) if pd.notna(a) and pd.notna(b)}
        sap = pd.read_excel(VORLAGE_DATEI, sheet_name="SAP Format Neu (Endtabelle)")
        sap = sap[sap.iloc[:, 2] == 3]
        codes = {"K810": "003147", "K811": "004147"}
        je_sap = {}
        for a, b, c in zip(sap.iloc[:, 0], sap.iloc[:, 1], sap.iloc[:, 4]):
            nr, norm_nr = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
            if pd.notna(nr) and pd.notna(norm_nr):  # Materialnummern mit Buchstaben ueberspringen
                je_sap.setdefault((int(nr), int(norm_nr)), codes.get(str(c).strip(), ""))
        for lagerort, nr in sap_nr.items():
            for (s_nr, norm_nr), art in je_sap.items():
                if s_nr == nr and art:
                    sap_art.setdefault((lagerort, norm_nr), art)
    except (FileNotFoundError, ValueError, KeyError):
        pass
    return stamm_art, sap_art


_KLT_ART_STAMM, _KLT_ART_SAP = _lade_klt_art()


def _klt_art(lagerort, norm_nr) -> str:
    """"003147" (klein), "004147" (gross) oder "" (unbekannt)."""
    schluessel = (str(lagerort).strip(), int(norm_nr))
    return _KLT_ART_STAMM.get(schluessel) or _KLT_ART_SAP.get(schluessel, "")

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

def _begrenze_auf_bestand(gerundet: pd.DataFrame, nutzbar: dict | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aufrunden auf volle KLT darf nie mehr KLT verplanen, als physisch
    nutzbar sind (Anfrage 04.11.: 940315000 - je Abladestelle aufgerundet,
    in Summe mehr eingeplant als Bestand). Je Artikel werden die nutzbaren KLT
    nach Dringlichkeit (aeltestes Ladedatum zuerst) verteilt; reicht es fuer
    eine Zeile nicht, wird sie gekuerzt (Hinweis in Z) und der fehlende Teil
    geht als Rueckstand zurueck. Rueckgabe (gekuerzt, zusaetzliche_rueckstaende)."""
    leer = pd.DataFrame(columns=["Abladestelle", "Norm-Nr", "Offene Menge", "Ladedatum", "VW-Nr"])
    if nutzbar is None or gerundet.empty:
        return gerundet, leer
    df = gerundet.sort_values(["Ladedatum", "Abladestelle"]).copy()
    df["Bestandshinweis"] = None
    frei_klt: dict = {}
    zusatz = []
    for idx, r in df.iterrows():
        norm_nr, f = r["Norm-Nr"], r["Fuellmenge"]
        if norm_nr not in frei_klt:
            frei_klt[norm_nr] = int(nutzbar.get(norm_nr, 0) // f) if f else 0
        klt = min(int(r["Packeinheiten"]), frei_klt[norm_nr])
        frei_klt[norm_nr] -= klt
        if klt == int(r["Packeinheiten"]):
            continue
        df.loc[idx, "Packeinheiten"] = klt
        df.loc[idx, "Menge"] = klt * f
        df.loc[idx, "Menge_gerundet"] = klt * f != r["Menge urspruenglich"]
        df.loc[idx, "Bestandshinweis"] = f"Bestand reicht nur für {klt} KLT"
        fehlt = r["Menge urspruenglich"] - klt * f
        if fehlt > 0:
            zusatz.append({
                "Abladestelle": r["Abladestelle"], "Norm-Nr": norm_nr, "Offene Menge": fehlt,
                "Ladedatum": r["Ladedatum"], "VW-Nr": r.get("VW-Nr", ""),
            })
    df = df[df["Packeinheiten"] > 0].sort_values(["Abladestelle", "Norm-Nr"]).reset_index(drop=True)
    return df, (pd.DataFrame(zusatz) if zusatz else leer)


def _runde_auf_fuellmenge(gruppiert: pd.DataFrame) -> pd.DataFrame:
    df = gruppiert.copy()
    df["Fuellmenge"] = df["Norm-Nr"].apply(_fuellmenge)
    df["Packeinheiten"] = (df["Menge"] / df["Fuellmenge"]).apply(math.ceil)
    df["Menge urspruenglich"] = df["Menge"]
    df["Menge"] = df["Packeinheiten"] * df["Fuellmenge"]
    df["Menge_gerundet"] = df["Menge"] != df["Menge urspruenglich"]
    return df


# --- Paletten je Abladestelle: volle Lagen, Reste, Mix-Paletten -------------
#
# Regel (Anfrage 04.11.):
# - Je Artikel: KLT auf Paletten (Kapazitaet "Anzahl" lt. Stammdaten, Lagen zu
#   "Anzahl Pro Lage"). Liegen auf der obersten, angefangenen Lage weniger als
#   5 KLT (MINDEST_PACKEINHEITEN_FUER_PALETTE), werden diese KLT von der
#   Palette genommen (Beispiel 307M7: 11 KLT bei 10/Lage -> 10 bleiben, 1 raus).
#   Diese KLT gehen zu "DHL UPS".
# - Artikel mit insgesamt < 5 KLT haben keine eigene Palette. Sie werden je
#   Abladestelle zu Mix-Paletten (eine Lage, groesster Artikel zuerst)
#   zusammengelegt. Kommen >= 5 KLT zusammen, wird die Mix-Palette geplant und
#   in der Datei sichtbar gemacht (Spalte N Palettentyp + Q = 1 in der Zeile
#   mit dem groessten Anteil, Erklaerung in Z) - Beispiel 307K2: 3 + 2 + 1 KLT
#   -> 1 x 111444. Sonst gehen sie zu "DHL UPS".
# - Abgetrennte Lagen-Reste grosser Artikel kommen bewusst NICHT auf
#   Mix-Paletten: sonst stuende ihre Menge (nur eine Zeile je Artikel) in der
#   Zeile mit der eigenen Palette, und die Excel-Formel Q wuerde sie dort
#   mitzaehlen. So bleiben N/Q in allen Zeilen mit eigener Palette Formeln.
# - Mix-Paletten nur aus KLT GLEICHER Art: 003147 (klein) und 004147 (gross)
#   werden nie gemischt (Anfrage 04.11.). KLT-Art wie Formel R der Vorlage
#   (Stammdaten, sonst SAP Format). Unbekannte KLT-Art mischt nur mit
#   ebenfalls unbekannter.
# - Pro Artikel/Abladestelle hoechstens eine Zeile je Blatt.

STANDARD_MIX_PALETTE = "111444"


def _hinweis_text(zeile):
    wert = zeile.get("Bestandshinweis")
    return wert if isinstance(wert, str) and wert else None

BEKANNTE_PALETTEN = {"111444", "VWPAL", "99C159"}


def _teile_artikel(zeile, lagerort: str) -> dict:
    """KLT eines Artikels in (bleibt auf eigener Palette, Rest fuer Mix/DHL)."""
    spez = _palettenspezifikation(lagerort, zeile["Norm-Nr"])
    pro_lage = int(spez["anzahl_pro_lage"]) or 10
    pro_palette = int(spez["anzahl_volle_palette"]) or pro_lage
    klt = int(zeile["Packeinheiten"])
    if klt < MINDEST_PACKEINHEITEN_FUER_PALETTE:
        bleibt, rest = 0, klt
    else:
        angefangene_lage = (klt % pro_palette) % pro_lage
        if angefangene_lage and angefangene_lage < MINDEST_PACKEINHEITEN_FUER_PALETTE:
            bleibt, rest = klt - angefangene_lage, angefangene_lage
        else:
            bleibt, rest = klt, 0
    return {"bleibt": bleibt, "rest": rest, "pro_lage": pro_lage, "typ": str(spez.get("typ") or "").strip()}


def _plane_abladestelle(gruppe: pd.DataFrame, lagerort: str) -> tuple[list[dict], list[dict]]:
    """Gibt (planungszeilen, dhl_ups_zeilen) fuer eine Abladestelle zurueck
    (Regel siehe Abschnittskommentar oben).

    Zeilen-Felder: Norm-Nr, Menge, Menge_gerundet; optional "Paletten Typ" /
    "Paletten Anzahl" (werden dann statt der Formeln N/Q geschrieben, weil die
    Excel-Formeln Mix-Paletten nicht kennen) und "Hinweis" (Spalte Z)."""
    planung: dict = {}  # Norm-Nr -> Zeile
    reste: list[dict] = []
    dhl_ups: list[dict] = []
    for _, zeile in gruppe.iterrows():
        teil = _teile_artikel(zeile, lagerort)
        fm = zeile["Fuellmenge"]
        if teil["bleibt"]:
            planung[zeile["Norm-Nr"]] = {
                "Norm-Nr": zeile["Norm-Nr"], "Menge": teil["bleibt"] * fm,
                # Aufrundung steckt in der letzten KLT - die gehoert zum Rest,
                # falls einer abgetrennt wurde.
                "Menge_gerundet": bool(zeile["Menge_gerundet"]) and not teil["rest"],
                "Hinweis": _hinweis_text(zeile),
            }
        if teil["rest"] and teil["bleibt"]:
            # Angefangene Lage eines grossen Artikels -> DHL UPS.
            dhl_ups.append({
                "Norm-Nr": zeile["Norm-Nr"], "Menge": teil["rest"] * fm,
                "Menge_gerundet": bool(zeile["Menge_gerundet"]),
                "Hinweis": _hinweis_text(zeile),
            })
        elif teil["rest"]:
            reste.append({
                "Norm-Nr": zeile["Norm-Nr"], "KLT": teil["rest"], "Fuellmenge": fm,
                "Menge_gerundet": bool(zeile["Menge_gerundet"]),
                "pro_lage": teil["pro_lage"], "typ": teil["typ"],
                "klt_art": _klt_art(lagerort, zeile["Norm-Nr"]),
                "Hinweis": _hinweis_text(zeile),
            })

    # Mix-Paletten: groesster Rest zuerst als Grundstock, auffuellen bis eine Lage voll.
    reste.sort(key=lambda r: r["KLT"], reverse=True)
    while reste:
        grundstock = reste.pop(0)
        kapazitaet = grundstock["pro_lage"]
        mix, summe, uebrig = [grundstock], grundstock["KLT"], []
        for kandidat in reste:
            if kandidat["klt_art"] == grundstock["klt_art"] and summe + kandidat["KLT"] <= kapazitaet:
                mix.append(kandidat)
                summe += kandidat["KLT"]
            else:
                uebrig.append(kandidat)
        reste = uebrig

        if summe < MINDEST_PACKEINHEITEN_FUER_PALETTE:
            for r in mix:
                dhl_ups.append({
                    "Norm-Nr": r["Norm-Nr"], "Menge": r["KLT"] * r["Fuellmenge"],
                    "Menge_gerundet": r["Menge_gerundet"], "Hinweis": r["Hinweis"],
                })
            continue

        typ = grundstock["typ"] if grundstock["typ"] in BEKANNTE_PALETTEN else STANDARD_MIX_PALETTE
        art = f" ({grundstock['klt_art']})" if grundstock["klt_art"] else ""
        beschreibung = f"Mix-Palette{art} " + " + ".join(f"{r['KLT']}" for r in mix) + f" = {summe} KLT"
        for i, r in enumerate(mix):
            eintrag = {
                "Norm-Nr": r["Norm-Nr"], "Menge": r["KLT"] * r["Fuellmenge"],
                "Menge_gerundet": r["Menge_gerundet"],
            }
            if i == 0:
                # Zeile mit dem groessten Anteil traegt die Mix-Palette (die
                # Formeln N/Q ergaeben hier "-"/0, weil < 5 KLT je Zeile).
                eintrag["Paletten Typ"] = typ
                eintrag["Paletten Anzahl"] = 1
                text = f"{beschreibung} (1 x {typ} in dieser Zeile)"
            else:
                text = f"{r['KLT']} KLT auf Mix-Palette bei {int(grundstock['Norm-Nr'])}"
            eintrag["Hinweis"] = " · ".join(t for t in (text, r["Hinweis"]) if t)
            planung[r["Norm-Nr"]] = eintrag

    planungszeilen = [planung[n] for n in gruppe["Norm-Nr"] if n in planung]
    return planungszeilen, dhl_ups


def _teilmenge_kombis(rueckstand: pd.DataFrame, planbar: pd.DataFrame) -> set:
    """(Abladestelle, Norm-Nr)-Kombinationen, die durch die Mengen-Aufteilung
    SOWOHL eine planbare als auch eine Rueckstands-Teilmenge haben."""
    if rueckstand.empty or planbar.empty:
        return set()
    in_rueckstand = set(zip(rueckstand["Abladestelle"], rueckstand["Norm-Nr"]))
    in_planbar = set(zip(planbar["Abladestelle"], planbar["Norm-Nr"]))
    return in_rueckstand & in_planbar


def _baue_planung_und_versand(
    planbar: pd.DataFrame, nutzbar: dict | None = None
) -> tuple[list[dict], list[dict], pd.DataFrame]:
    """Komplette Planbar-Menge -> (Almanca-Zeilen, DHL/UPS-Zeilen,
    zusaetzliche Rueckstaende durch Bestandsbegrenzung), je Abladestelle
    gruppiert und sortiert, mit Mix-Paletten-Logik."""
    if planbar.empty:
        return [], [], _begrenze_auf_bestand(planbar, None)[1]
    gruppiert = _gruppiere_je_abladestelle_artikel(planbar)
    gerundet, zusatz_rueckstand = _begrenze_auf_bestand(_runde_auf_fuellmenge(gruppiert), nutzbar)

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
    return alle_planungszeilen, alle_dhl_ups_zeilen, zusatz_rueckstand


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


def _markiere_eintreffende(
    rueckstand_anzeige: pd.DataFrame, zugang_vorbereitet: pd.DataFrame | None, planungsdatum
) -> pd.DataFrame:
    """Rueckstaende (physisch nicht gedeckt), fuer die laut ZMM1000 bis
    spaetestens zum Planungsdatum eine NRI eintrifft. Je Artikel wird die
    eintreffende Menge nach Dringlichkeit (aeltestes Ladedatum zuerst) auf die
    Rueckstandszeilen verteilt. Ergebnis: Spalte "Eintreffend bis Planung"
    (gedeckte Menge, 0 = nichts) und - fuer diese Zeilen - "Zugang Info" mit
    genau den NRIs, die die Zeile decken. Diese Zeilen werden im Blatt
    "Rückstände" gelb markiert, damit sie nicht vergessen werden."""
    df = rueckstand_anzeige.copy()
    df["Eintreffend bis Planung"] = 0.0
    if df.empty or zugang_vorbereitet is None or zugang_vorbereitet.empty:
        return df
    zugaenge = zugang_vorbereitet[
        zugang_vorbereitet["Ankunft gerechnet"] <= pd.Timestamp(planungsdatum)
    ].sort_values("Ankunft gerechnet")
    for norm_nr, zg in zugaenge.groupby("Norm-Nr"):
        warteschlange = [dict(z, Rest=float(z["Menge"])) for z in zg.to_dict("records")]
        zeilen = df[df["Norm-Nr"] == norm_nr].sort_values(["Ladedatum", "Abladestelle"])
        for idx, r in zeilen.iterrows():
            offen, genutzt = float(r["Menge"]), []
            while offen > 0 and warteschlange:
                z = warteschlange[0]
                nimm = min(offen, z["Rest"])
                z["Rest"] -= nimm
                offen -= nimm
                genutzt.append(z)
                if z["Rest"] <= 0:
                    warteschlange.pop(0)
            if not genutzt:
                break
            df.loc[idx, "Eintreffend bis Planung"] = float(r["Menge"]) - offen
            df.loc[idx, "Zugang Info"] = "; ".join(_formatiere_zugang_info(z) for z in genutzt)
    return df


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


def _schreibe_zeilen(
    ws, zeilen: list[dict], *, rot_wenn_gerundet: bool, gruen_fuellung: bool,
    teilmenge_kombis: set = frozenset(), hinweis_artikel: set = frozenset(),
    rueckstand_seit: dict | None = None, start_zeile: int = ERSTE_DATENZEILE,
) -> int:
    """Schreibt die Zeilen ab start_zeile, gibt die naechste freie Zeile zurueck.

    rueckstand_seit: (Abladestelle, Norm-Nr) -> urspruengliches Ladedatum fuer
    eingeplante Rueckstaende (VW-Nr rot + Ladedatum in L).
    Optionale Zeilen-Felder "Paletten Typ"/"Paletten Anzahl" ueberschreiben die
    Formeln in N/Q (Mix-Paletten), "Hinweis" kommt nach Spalte Z."""
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
            for spalte in range(1, GELB_BIS_SPALTE + 1):  # A bis T
                ws.cell(row=zeile_nr, column=spalte).fill = GRUEN_FUELLUNG
        if eintrag.get("Paletten Typ"):
            ws.cell(row=zeile_nr, column=SPALTE_PALETTEN_TYP, value=eintrag["Paletten Typ"])
        if eintrag.get("Paletten Anzahl") is not None:
            ws.cell(row=zeile_nr, column=SPALTE_PALETTEN_ANZAHL, value=int(eintrag["Paletten Anzahl"]))

        hinweise = []
        if kombi in teilmenge_kombis:
            # Nur ein Teil der offenen Menge war durch Bestand gedeckt - der
            # Rest steht zusaetzlich in den Rueckstaenden.
            hinweise.append("Teilmenge, Prüfen")
        if eintrag.get("Hinweis"):
            hinweise.append(eintrag["Hinweis"])
        if hinweise:
            ws.cell(row=zeile_nr, column=SPALTE_HINWEIS, value=" · ".join(hinweise))

        lagerauftrag = ws.cell(row=zeile_nr, column=SPALTE_LAGERAUFTRAG)
        mgbekleyen = eintrag["Norm-Nr"] in hinweis_artikel
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
        eintreffend = float(eintrag.get("Eintreffend bis Planung", 0) or 0)
        if eintreffend > 0:
            # NRI trifft bis zum Planungsdatum ein -> gelb (A bis T), nicht vergessen.
            for spalte in range(1, GELB_BIS_SPALTE + 1):
                ws.cell(row=zeile_nr, column=spalte).fill = GELB_FUELLUNG
            if eintreffend < float(eintrag["Menge"]):
                teil = f"{eintreffend:,.0f}".replace(",", ".")
                ws.cell(row=zeile_nr, column=SPALTE_HINWEIS, value=f"NRI deckt nur {teil} Stk")
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
    nutzbar = bestand_logik.nutzbarer_bestand_je_artikel(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    planungszeilen, dhl_ups_zeilen, zusatz_rueckstand = _baue_planung_und_versand(planbar, nutzbar)
    if not zusatz_rueckstand.empty:
        rueckstand = pd.concat([rueckstand, zusatz_rueckstand], ignore_index=True)
    palette_gefunden, palette_gesamt = _palettenspezifikation_abdeckung(planbar)
    zugang_warteschlangen = _zugang_warteschlangen_je_artikel(zugang_vorbereitet)
    teilmengen = _teilmenge_kombis(rueckstand, planbar)
    rueckstand_anzeige = _rueckstand_anzeige(rueckstand, zugang_warteschlangen)
    hinweis_artikel = bestand_logik.artikel_mit_lagerort_hinweis(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    rueckstand_seit = _rueckstand_seit_je_kombi(planbar, stichtag)
    rueckstand_anzeige = _markiere_eintreffende(rueckstand_anzeige, zugang_vorbereitet, planungsdatum)

    wb = openpyxl.load_workbook(VORLAGE_DATEI)
    _schreibe_zeilen(
        wb["Almanca"], planungszeilen, rot_wenn_gerundet=True, gruen_fuellung=False,
        teilmenge_kombis=teilmengen, hinweis_artikel=hinweis_artikel,
        rueckstand_seit=rueckstand_seit,
    )
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
        "erwartet_zeilen": int((rueckstand_anzeige["Eintreffend bis Planung"] > 0).sum()),
        "mix_paletten": sum(1 for z in planungszeilen if str(z.get("Hinweis", "")).startswith("Mix-Palette")),
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
    nutzbar = bestand_logik.nutzbarer_bestand_je_artikel(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    kandidaten, _ = _begrenze_auf_bestand(
        _runde_auf_fuellmenge(_gruppiere_je_abladestelle_artikel(planbar)), nutzbar
    )
    if bestehende_datei:
        vorhanden = vorhandene_kombinationen(bestehende_datei)
        schon_drin = [
            (_normiere_lagerort(a), int(n)) in vorhanden
            for a, n in zip(kandidaten["Abladestelle"], kandidaten["Norm-Nr"])
        ]
        kandidaten = kandidaten[[not x for x in schon_drin]]
    if "VW-Nr" not in kandidaten.columns:
        kandidaten = kandidaten.assign(**{"VW-Nr": ""})
    # Gleiche Palettenregel wie in der Planung: angefangene Lage < 5 KLT bzw.
    # Artikel < 5 KLT -> "DHL UPS", der Rest auf die eigene Palette (Almanca).
    zeilen = []
    for _, k in kandidaten.iterrows():
        teil = _teile_artikel(k, _normiere_lagerort(k["Abladestelle"]))
        for klt, ziel in ((teil["bleibt"], "Almanca"), (teil["rest"], "DHL UPS")):
            if klt:
                zeilen.append({
                    "Abladestelle": k["Abladestelle"], "Norm-Nr": k["Norm-Nr"], "VW-Nr": k["VW-Nr"],
                    "Menge": klt * k["Fuellmenge"], "Packeinheiten": klt, "Ladedatum": k["Ladedatum"],
                    "Ziel": ziel,
                    "Menge_gerundet": bool(k["Menge_gerundet"]) and (ziel == "DHL UPS" or not teil["rest"]),
                })
    if not zeilen:
        return pd.DataFrame(columns=spalten)
    return pd.DataFrame(zeilen).sort_values(["Abladestelle", "Norm-Nr", "Ziel"])[spalten].reset_index(drop=True)


def _kopiere_stil(quelle, ziel) -> None:
    ziel.font = copy(quelle.font)
    ziel.fill = copy(quelle.fill)
    ziel.number_format = quelle.number_format


def ergaenze_bestehende_planung(datei: bytes, auswahl: pd.DataFrame) -> bytes:
    """Ausgewaehlte Kandidaten (Spalten wie vorzieh_kandidaten(), "Ziel" =
    Almanca/DHL UPS) in eine bestehende Planungsdatei schreiben:
    jeweils unter die letzte belegte Zeile (mit einer Leerzeile Abstand).
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
        start = max(belegt) + 2 if belegt else ERSTE_DATENZEILE
        _schreibe_zeilen(
            ws, zeilen, rot_wenn_gerundet=(blatt == "Almanca"), gruen_fuellung=(blatt == "DHL UPS"),
            rueckstand_seit=seit, start_zeile=start,
        )
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


# --- Artikel pruefen: warum (nicht) eingeplant? -------------------------------

def _stk(wert) -> str:
    return f"{float(wert):,.0f}".replace(",", ".")


def artikel_diagnose(
    positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame,
    zugang_vorbereitet: pd.DataFrame | None, planungsdatum, norm_nr: int,
) -> dict:
    """Erklaert Schritt fuer Schritt mit denselben Regeln wie die Planung,
    warum ein Artikel (nicht) eingeplant wird. Rueckgabe: {"meldungen": [...],
    "positionen": DataFrame, "bestand": DataFrame}."""
    meldungen: list[str] = []
    bis = pd.Timestamp(planungsdatum)
    fm = _fuellmenge(norm_nr)
    if norm_nr not in bestand_logik.FUELLMENGE_JE_ARTIKEL:
        meldungen.append("⚠️ Keine Füllmenge in \"Almanca Hilfsdaten\" – es wird mit 1 Stk/KLT gerechnet.")
    else:
        meldungen.append(f"Füllmenge: {_stk(fm)} Stk/KLT.")

    alle = positionen[positionen["Norm-Nr"] == norm_nr]
    offen = alle[alle["Offene Menge"] > 0]
    if offen.empty:
        meldungen.append("❌ Kein offener Bedarf im Lieferplan-Export – nichts einzuplanen.")
        return {"meldungen": meldungen, "positionen": pd.DataFrame(), "bestand": pd.DataFrame()}
    fenster = offen[offen["Ladedatum"] <= bis]
    if fenster.empty:
        erstes = offen["Ladedatum"].min()
        meldungen.append(
            f"❌ Erste offene Position erst am {erstes:%d.%m.%Y} – nach dem Planungsdatum "
            f"{bis:%d.%m.%Y}. Planungsdatum auf mindestens {erstes:%d.%m.%Y} setzen."
        )
    else:
        meldungen.append(
            f"Offener Bedarf bis {bis:%d.%m.%Y}: {_stk(fenster['Offene Menge'].sum())} Stk "
            f"in {len(fenster)} Position(en)."
        )

    # Bestand je Charge mit Bewertung
    zeilen = []
    b = bestand_je_charge[bestand_je_charge["Norm-Nr"] == norm_nr] if bestand_je_charge is not None else pd.DataFrame()
    if not b.empty:
        b = b[b["Bestandsart"].notna() & (b["Bestandsart"].astype(str).str.strip() != "")]
        for (charge, lagerort, art), menge in b.groupby(["Charge", "Lagerort", "Bestandsart"], dropna=False)["Menge"].sum().items():
            if art not in config.BESTAND_VERFUEGBAR:
                grund = f"zählt nicht (Bestandsart {art})"
            elif lagerort in bestand_logik.AUSGESCHLOSSENE_LAGERORTE:
                grund = f"zählt nicht (Lagerort {lagerort}, schon für Versand bereitgestellt)"
            else:
                grund = "zählt"
            zeilen.append({"Charge": charge, "Lagerort": lagerort, "Bestandsart": art, "Menge": menge, "Bewertung": grund})
    bestand = pd.DataFrame(zeilen)
    nutzbar_alle = bestand_logik.nutzbarer_bestand_je_artikel(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    nutzbar = nutzbar_alle.get(norm_nr, 0)
    if not bestand.empty:
        zaehlt = bestand[bestand["Bewertung"] == "zählt"]
        je_charge = zaehlt.groupby("Charge")["Menge"].sum()
        unter_fm = je_charge[je_charge < fm]
        meldungen.append(
            f"Bestand gesamt {_stk(bestand['Menge'].sum())} Stk, davon frei (F1/F2, ohne OUT1) "
            f"{_stk(zaehlt['Menge'].sum())} Stk in {len(je_charge)} Charge(n)."
        )
        if len(unter_fm):
            meldungen.append(
                f"{len(unter_fm)} Charge(n) haben weniger als eine volle KLT ({_stk(unter_fm.sum())} Stk) – "
                "Chargen dürfen nicht gemischt werden, zählen also nicht."
            )
    meldungen.append(f"➡️ Nutzbar für die Planung: {_stk(nutzbar)} Stk ({_stk(nutzbar // fm if fm else 0)} KLT).")
    if nutzbar <= 0:
        meldungen.append("❌ Kein nutzbarer Bestand – der Bedarf steht im Blatt \"Rückstände\".")

    # Verteilung wie in der Planung (aelteste Ladedaten zuerst, ueber alle Abladestellen)
    rueckstand, planbar = _splitte_auftraege(positionen, bestand_je_charge, planungsdatum)
    p = planbar[planbar["Norm-Nr"] == norm_nr]
    r = rueckstand[rueckstand["Norm-Nr"] == norm_nr]
    tabelle = fenster[["Abladestelle", "Ladedatum", "Offene Menge"]].copy() if not fenster.empty else pd.DataFrame()
    if not tabelle.empty:
        tabelle["aus Bestand gedeckt"] = p["Offene Menge"].reindex(tabelle.index).fillna(0)
        tabelle["Rückstand"] = r["Offene Menge"].reindex(tabelle.index).fillna(0)
        tabelle = tabelle.sort_values("Ladedatum")
        gedeckt = tabelle["aus Bestand gedeckt"].sum()
        if nutzbar > 0 and gedeckt < tabelle["Offene Menge"].sum():
            meldungen.append(
                f"Der Bestand reicht für {_stk(gedeckt)} von {_stk(tabelle['Offene Menge'].sum())} Stk – "
                "er wird nach Ladedatum verteilt (älteste zuerst, über alle Abladestellen)."
            )

        # Ergebnis der Planung fuer diesen Artikel
        planungszeilen, dhl_zeilen, _ = _baue_planung_und_versand(planbar, nutzbar_alle)
        for blatt, liste in (("Almanca", planungszeilen), ("DHL UPS", dhl_zeilen)):
            for z in liste:
                if z["Norm-Nr"] == norm_nr:
                    zusatz = f" – {z['Hinweis']}" if z.get("Hinweis") else ""
                    meldungen.append(f"✅ Eingeplant in \"{blatt}\": {z['Abladestelle']} {_stk(z['Menge'])} Stk{zusatz}")
        if not any(z["Norm-Nr"] == norm_nr for z in planungszeilen + dhl_zeilen) and gedeckt > 0:
            meldungen.append("⚠️ Gedeckte Menge vorhanden, aber nicht eingeplant – bitte melden (Logikfehler).")
    zugaenge = (zugang_vorbereitet[zugang_vorbereitet["Norm-Nr"] == norm_nr]
                if zugang_vorbereitet is not None and not zugang_vorbereitet.empty else pd.DataFrame())
    if not zugaenge.empty:
        naechster = zugaenge.sort_values("Ankunft gerechnet").iloc[0]
        meldungen.append(
            f"Nächster Zugang: {naechster['Referenz']} am {pd.Timestamp(naechster['Ankunft gerechnet']):%d.%m.%Y} "
            f"({_stk(naechster['Menge'])} Stk) – zählt erst nach Eintreffen als Bestand."
        )
    return {"meldungen": meldungen, "positionen": tabelle, "bestand": bestand}


def _render_artikel_pruefen(daten: dict, planungsdatum) -> None:
    with st.expander("🔎 Artikel prüfen: warum (nicht) eingeplant?"):
        eingabe = st.text_input("Norm-Nr", key="planung_artikel_pruefen").strip()
        if not eingabe:
            return
        norm_nr = _normiere_norm_nr(eingabe)
        if norm_nr is None:
            st.warning("Bitte eine Norm-Nr (nur Ziffern) eingeben.")
            return
        ergebnis = artikel_diagnose(
            daten["positionen"], daten.get("bestand_je_charge"), daten.get("zugang"), planungsdatum, norm_nr
        )
        st.markdown(f"**{norm_nr} – Planungsdatum {pd.Timestamp(planungsdatum):%d.%m.%Y}**")
        for m in ergebnis["meldungen"]:
            st.markdown(f"- {m}")
        if not ergebnis["positionen"].empty:
            pos = ergebnis["positionen"].copy()
            pos["Ladedatum"] = pos["Ladedatum"].dt.strftime("%d.%m.%Y")
            st.dataframe(pos, hide_index=True, use_container_width=True)
        if not ergebnis["bestand"].empty:
            st.dataframe(ergebnis["bestand"], hide_index=True, use_container_width=True)


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
        "Markierungen: eingeplante Mengen, die bereits Rückstand waren (Ladedatum "
        "vor dem Datenstand, Ware jetzt da) → VW-Nr rot, ursprüngliches Ladedatum "
        "in Spalte L. Im Blatt \"Rückstände\" sind Zeilen gelb (A–T), für die bis "
        "zum Planungsdatum eine NRI eintrifft. Paletten: angefangene Lagen mit "
        "weniger als 5 KLT kommen von der Palette (→ DHL UPS); Artikel unter 5 KLT "
        "werden je Abladestelle zu Mix-Paletten zusammengelegt; "
        "Mix-Paletten stehen mit Typ (N), Anzahl (Q) und Erklärung (Z) in der Datei."
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
        _render_artikel_pruefen(daten, planungsdatum)
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
            f"🟡 {erwartet_zeilen} Rückstandszeile(n) gelb: NRI trifft bis zum "
            "Planungsdatum ein (Blatt \"Rückstände\")."
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
    _render_artikel_pruefen(daten, planungsdatum)
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

    spalten = [s for s in ["Norm-Nr", "VW-Nr", "Abladestelle", "Menge", "Ladedatum",
                           "Eintreffend bis Planung", "Zugang Info"]
               if s in anzeige.columns]
    anzeige = anzeige[spalten].copy()
    anzeige["Ladedatum"] = anzeige["Ladedatum"].dt.strftime("%d.%m.%Y")
    anzeige["Menge"] = anzeige["Menge"].apply(lambda v: f"{v:,.0f}".replace(",", "."))
    if "Eintreffend bis Planung" in anzeige.columns:
        anzeige["Eintreffend bis Planung"] = anzeige["Eintreffend bis Planung"].apply(
            lambda v: f"🟡 {v:,.0f}".replace(",", ".") if v and v > 0 else ""
        )
    st.dataframe(
        anzeige,
        hide_index=True,
        use_container_width=True,
        height=_tabellenhoehe(len(anzeige)),
        column_config={"VW-Nr": st.column_config.TextColumn(width=110)},
        key="planung_rueckstand_tabelle",
    )
