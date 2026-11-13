"""Bericht fuer die Produktion (Reiter "Ausgabedatei" im Dashboard Dispo).

Excel-Datei, die die Dispo der Produktion in der Tuerkei schickt. Sie zeigt,
was fehlt, was schon unterwegs ist und was in den naechsten Wochen gebraucht
wird - je Artikel nach Dringlichkeit sortiert. Beide Seiten schreiben ihre
Notizen hinein; beim naechsten Bericht werden sie uebernommen (letzten Bericht
hochladen).

Blaetter:
  Uebersicht  schlank: oben fuenf Kacheln (Handlungsbedarf, Fehlt gesamt,
              Rueckstand + Reaktionszeit, Unterwegs, gedeckt), darunter je
              Artikel drei Zeilen: Nr., 👁 Details (Link), Norm-Nr, VW-Nr,
              nutzbarer Bestand (volle KLT je Charge, ohne OUT1), Bedarf
              Rueckstand + Reaktionszeit, Unterwegs mit NRI-Liste (NRI ·
              Ankunft · Menge), EIN Status "gedeckt bis Horizont? Ja/Nein",
              aeltester Abruf (Liefertermin) und die Notizspalten.
  Details     je Artikel eine Karte: Kennzahlen, ① Bestandsprognose je Woche
              (Bestand faellt mit dem Bedarf, steigt mit jedem Zugang; unter
              null = Fehlmenge - wie MD04), daneben Bestand + NRI und die
              Abrufe der naechsten 4 Wochen mit Rest (rot ab der Zeile, ab der
              es nicht mehr reicht; Summe gruen = gedeckt, rot = fehlt),
              ② Vorschlag: dieselbe Prognose plus vorgeschlagener
              Wareneingang - Datum/Menge in gelben Feldern, das Diagramm
              rechnet ueber Formeln sofort neu (ohne Makro), Bedarf je Kunde.
  Wochen      Bedarf / Zulauf / Fehlt je Kalenderwoche bis zum Horizont.
  Unterwegs   alle Zugaenge zu uns (ZMM1000) mit NRI.
  Notizen-Archiv  Notizen von Artikeln, die gerade nicht im Bericht stehen.
  Diagrammdaten   (ausgeblendet) Zahlen und Formeln hinter den Diagrammen.

Rechnet nur mit den Spalten, die logic.berechne bereits liefert (Offene Menge,
Kum. Bedarf Artikel, Bestand verfuegbar) und den vorbereiteten Zugaengen -
die Dispositionslogik selbst wird nicht veraendert. Je Einteilung wird die
offene Menge in der Reihenfolge des Ladedatums verteilt (wie logic.py):
zuerst Bestand bei uns, dann die Zugaenge in Reihenfolge der Ankunft.
  rechtzeitig  durch Bestand oder einen Zugang, der bis zum Ladedatum da ist
  spaet        durch einen Zugang, der erst nach dem Ladedatum ankommt
  fehlt        weder bei uns noch unterwegs -> muss aus der Tuerkei kommen
(spaet + fehlt = Fehlmenge aus logic.py)

Vorgeschlagener Wareneingang: die Fehlmengen ("fehlt") je Ladedatum, in
Fenstern von 14 Tagen gebuendelt; Datum = erster Bedarfstag im Fenster
(Rueckstand = sofort), Menge aufgerundet. Ware, die schon unterwegs ist, aber
zu spaet kommt, wird nicht noch einmal vorgeschlagen (sie ist ja unterwegs).

Durchschnittsbedarf: offene Mengen im Bedarfsexport (bis zum Horizont) geteilt
durch die Wochen, die der Export abdeckt (vom aeltesten Ladedatum bis zum
letzten Ladedatum im Export, hoechstens bis zum Horizont). Reicht der Export
nur wenige Tage, ist der Durchschnitt entsprechend grob - die Basis steht im
Bericht dabei.
"""
from __future__ import annotations

import io
import math
import re

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.chart import AreaChart, BarChart, Reference
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.text import RichText
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, TwoCellAnchor
from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.pagebreak import Break

import bestand_logik
from dispo_dashboard import config
from dispo_dashboard.loaders import materialnr

BLATT_UEBERSICHT = "Übersicht - Özet"
BLATT_DETAILS = "Details - Detay"
BLATT_WOCHEN = "Wochen - Haftalık"
BLATT_UNTERWEGS = "Unterwegs - Yolda"
BLATT_ARCHIV = "Notizen-Archiv - Not arşivi"
BLATT_DATEN = "Diagrammdaten"

KOPFZEILE = 4            # Wochen, Unterwegs, Archiv (Details: Karten ab ERSTE_ZEILE)
ERSTE_ZEILE = 5
UEBERSICHT_KOPFZEILE = 9    # Uebersicht: darueber Titel + Kacheln
UEBERSICHT_ERSTE_ZEILE = UEBERSICHT_KOPFZEILE + 1

STANDARD_REAKTION_TAGE = 14
STANDARD_WOCHEN = 22
DIAGRAMM_ZEILEN = 18       # Hoehe eines Diagramms in der Detailkarte (Zeilen)
MAX_KUNDEN_IM_BLOCK = 5
MAX_VORSCHLAEGE = 6        # Eingabezeilen "vorgeschlagener Wareneingang" je Artikel
VORSCHLAG_FENSTER_TAGE = 14
ZEILEN_JE_ARTIKEL = 3      # Uebersicht: jeder Artikel bekommt 3 Zeilen (Platz fuer die NRI-Liste)
ABRUF_TAGE = 28            # Detailkarte: Abrufe der naechsten 4 Wochen neben der Prognose
VORLAGE_DATEI = bestand_logik.VORLAGE_DATEI

# Dringlichkeitsstufen je Artikel (Sortierung: Stufe, dann erster Engpass)
# fill/font = Etikett (hell/dunkel), balken = Akzentfarbe
STUFEN = {
    1: {"de": "Rückstand – fehlt", "tr": "Gecikme – eksik", "fill": "FEE2E2", "font": "991B1B", "balken": "DC2626"},
    2: {"de": "Rückstand – unterwegs", "tr": "Gecikme – yolda", "fill": "FFEDD5", "font": "9A3412", "balken": "EA580C"},
    3: {"de": "Engpass ≤ {tage} Tage", "tr": "Darboğaz ≤ {tage} gün", "fill": "FEF3C7", "font": "92400E", "balken": "D97706"},
    4: {"de": "Später ≤ {wochen} Wochen", "tr": "İleride ≤ {wochen} hafta", "fill": "DBEAFE", "font": "1E40AF", "balken": "2563EB"},
    5: {"de": "Gedeckt", "tr": "Karşılandı", "fill": "DCFCE7", "font": "166534", "balken": "16A34A"},
}

TRANSPORT_TR = {"Luftfracht": "Hava kargo", "Minivan": "Minivan", "Express LKW": "Ekspres kamyon", "LKW": "Kamyon"}

TEXTE = {
    "DE": {
        "bestand": "Bestand {m}",
        "spaet": "{t} T. zu spät",
        "fehlt": "fehlt {m}",
        "dispo": "Ware bei uns – Versand durch Dispo",
        "ueberfaellig": "überfällig – schnellstmöglich",
        "puenktlich": "für pünktlich: {art}",
        "ankunft_ueberfaellig": "Ankunft überfällig (geplant {datum})",
        "einteilungen": "{n} Einteilung(en)",
        "transport": "Transport {nr}",
    },
    "TR": {
        "bestand": "Stok {m}",
        "spaet": "{t} gün geç",
        "fehlt": "eksik {m}",
        "dispo": "Mal depoda – sevkiyatı Dispo yapacak",
        "ueberfaellig": "gecikmiş – en kısa sürede",
        "puenktlich": "zamanında yetişmesi için: {art}",
        "ankunft_ueberfaellig": "Varış gecikti (planlanan {datum})",
        "einteilungen": "{n} termin satırı",
        "transport": "Sevkiyat {nr}",
    },
}


# --- Hilfen ------------------------------------------------------------------

def _menge_text(wert) -> str:
    return f"{float(wert):,.0f}".replace(",", ".")


def _datum_kurz(wert) -> str:
    return pd.Timestamp(wert).strftime("%d.%m.") if pd.notna(wert) else ""


def _montag(datum: pd.Timestamp) -> pd.Timestamp:
    datum = pd.Timestamp(datum).normalize()
    return datum - pd.Timedelta(days=datum.weekday())


def _stufe_text(stufe: int, reaktion_tage: int, wochen: int, sprache: str) -> str:
    return STUFEN[stufe][sprache].format(tage=reaktion_tage, wochen=wochen)


def _stufe_zweisprachig(stufe: int, reaktion_tage: int, wochen: int) -> str:
    return f"{_stufe_text(stufe, reaktion_tage, wochen, 'de')}\n{_stufe_text(stufe, reaktion_tage, wochen, 'tr')}"


def _wochen_text(wert) -> str:
    return "–" if wert is None or pd.isna(wert) else f"{float(wert):.1f}".replace(".", ",")


def vw_nr_schreibweise(wert) -> str:
    """VW-Teilenummer in der ueblichen Schreibweise: Vornummer auf 3 Stellen,
    dann 3-3-2 (Normteile) bzw. 3-3 + Index: "N91196801" / "N 911 968 01" /
    "-N---911-968-01" -> "N   911 968 01", "-WHT-009-642" -> "WHT 009 642",
    "1Z0860091J" -> "1Z0 860 091 J". Unbekannte Formate bleiben, wie sie sind."""
    if wert is None or (isinstance(wert, float) and pd.isna(wert)):
        return ""
    text = str(wert).strip()
    kompakt = re.sub(r"[\s.\-]", "", text).upper()
    m = re.fullmatch(r"N(\d{3})(\d{3})(\d{2})", kompakt)
    if m:
        return f"N   {m.group(1)} {m.group(2)} {m.group(3)}"
    m = re.fullmatch(r"([A-Z0-9]{3})(\d{3})(\d{3})([A-Z]{0,3})", kompakt)
    if m and re.search(r"[A-Z]", m.group(1)):
        return f"{m.group(1)} {m.group(2)} {m.group(3)}" + (f" {m.group(4)}" if m.group(4) else "")
    return text


def _lade_vw_nummern() -> dict:
    """Norm-Nr -> VW-Nr aus der Planungsvorlage, Blatt "Almanca Hilfsdaten"
    (Spalte A Norm, B VW-Nr - die Artikelliste, die auch die Planung nutzt)."""
    try:
        hilfsdaten = pd.read_excel(VORLAGE_DATEI, sheet_name="Almanca Hilfsdaten")
    except (FileNotFoundError, ValueError):
        return {}
    ergebnis = {}
    for norm, vw in zip(hilfsdaten.iloc[:, 0], hilfsdaten.iloc[:, 1]):
        norm = materialnr(norm)
        if norm is not None and pd.notna(vw) and str(vw).strip():
            ergebnis.setdefault(norm, vw_nr_schreibweise(vw))
    return ergebnis


VW_NUMMERN = _lade_vw_nummern()


def vw_nr(norm_nr, vorhanden="", kundenmaterial="") -> str:
    """VW-Nr fuer den Bericht: Artikelliste der Vorlage, sonst Kundenmaterial
    aus dem Bedarfsexport, sonst die schon vorhandene - immer einheitlich
    geschrieben."""
    for quelle in (VW_NUMMERN.get(norm_nr), kundenmaterial, vorhanden):
        text = vw_nr_schreibweise(quelle)
        if text:
            return text
    return ""


# --- Berechnung --------------------------------------------------------------

def _segmente(bestand: float, zugaenge: pd.DataFrame) -> list[tuple]:
    """Versorgung als kumulierte Abschnitte: (von, bis, art, ankunft, referenz, transport)."""
    segmente = []
    position = 0.0
    if bestand > 0:
        segmente.append((0.0, bestand, "B", None, "", ""))
        position = bestand
    for _, z in zugaenge.iterrows():
        menge = float(z["Menge"])
        if menge <= 0:
            continue
        segmente.append((position, position + menge, "Z", z["Ankunft gerechnet"],
                         str(z.get("Referenz", "") or ""), str(z.get("Transport", "") or "")))
        position += menge
    return segmente


def _bestandsverlauf(bestand: float, zeilen: pd.DataFrame, zugaenge: pd.DataFrame, st, horizont) -> dict:
    """Bestandsprognose je Tag (wie die laufende verfuegbare Menge in MD04):
    Kategorie 0 = Bestand heute, 1 = nach Abzug des Rueckstands (Ladedatum bis
    Stichtag, inkl. Zugaenge mit Ankunft bis Stichtag), danach je Kalendertag
    bis zum Horizont. Rueckgabe: labels, tage, bedarf, zulauf, bestand,
    bestand_plus (>= 0), fehl_minus (<= 0), erster_fehltag (Label oder None)."""
    tage = list(pd.date_range(st + pd.Timedelta(days=1), horizont, freq="D"))
    n = len(tage) + 2
    bedarf, zulauf = [0.0] * n, [0.0] * n
    for _, z in zeilen.iterrows():
        d = pd.Timestamp(z["Ladedatum"]).normalize()
        i = 1 if d <= st else (d - st).days + 1
        if i < n:
            bedarf[i] += float(z["Offen"])
    for _, z in zugaenge.iterrows():
        d = pd.Timestamp(z["Ankunft gerechnet"]).normalize()
        i = 1 if d <= st else (d - st).days + 1
        if i < n:
            zulauf[i] += float(z["Menge"])
    verlauf, stand = [], float(bestand)
    for i in range(n):
        stand = stand + zulauf[i] - bedarf[i]
        verlauf.append(stand)
    labels = ["Bestand / Stok", f"bis / {st:%d.%m.} dahil"] + [f"{d:%d.%m.}" for d in tage]
    alle_tage = [None, st] + tage
    return {
        "labels": labels,
        "tage": alle_tage,
        "bedarf": bedarf,
        "zulauf": zulauf,
        "bestand": verlauf,
        "bestand_plus": [max(v, 0.0) for v in verlauf],
        "fehl_minus": [min(v, 0.0) for v in verlauf],
        "erster_fehltag": _erster_fehltag(verlauf, alle_tage),
    }


def _erster_fehltag(verlauf: list, tage: list):
    """None = nie unter null, "sofort" = schon nach dem Rueckstand, sonst Datum."""
    erster = next((i for i, v in enumerate(verlauf) if v < -1e-9), None)
    if erster is None:
        return None
    return "sofort" if erster <= 1 else tage[erster]


def _runden(menge: float) -> float:
    """Vorschlagsmenge aufrunden: unter 1.000 auf 10, sonst auf 100 Stueck."""
    schritt = 10 if menge < 1000 else 100
    return float(math.ceil(menge / schritt - 1e-9) * schritt)


def vorschlag_zugaenge(zeilen_artikel: pd.DataFrame, stichtag, max_zeilen: int = MAX_VORSCHLAEGE,
                       fenster_tage: int = VORSCHLAG_FENSTER_TAGE) -> list[dict]:
    """Vorgeschlagener Wareneingang fuer einen Artikel: die Fehlmengen ("fehlt" =
    weder bei uns noch unterwegs) je Ladedatum, gebuendelt in Fenstern von
    fenster_tage. Datum = erster Bedarfstag im Fenster (Rueckstand -> Stichtag =
    sofort), Menge aufgerundet. Hoechstens max_zeilen Vorschlaege - die letzte
    Zeile nimmt den Rest bis zum Horizont auf.
    Rueckgabe: [{"Datum", "Menge", "Fehlt", "Bedarf bis", "Sofort"}]."""
    st = pd.Timestamp(stichtag).normalize()
    if zeilen_artikel is None or zeilen_artikel.empty:
        return []
    fehlt = zeilen_artikel[zeilen_artikel["Fehlt"] > 1e-9]
    if fehlt.empty:
        return []
    je_tag = (fehlt.assign(_tag=fehlt["Ladedatum"].map(lambda d: max(pd.Timestamp(d).normalize(), st)))
              .groupby("_tag")["Fehlt"].sum().sort_index())
    tage = list(je_tag.items())
    vorschlaege, k = [], 0
    while k < len(tage):
        start = tage[k][0]
        ende = None if len(vorschlaege) == max_zeilen - 1 else start + pd.Timedelta(days=fenster_tage)
        menge, bis = 0.0, start
        while k < len(tage) and (ende is None or tage[k][0] < ende):
            menge += float(tage[k][1])
            bis = tage[k][0]
            k += 1
        vorschlaege.append({"Datum": start, "Menge": _runden(menge), "Fehlt": menge,
                            "Bedarf bis": bis, "Sofort": start <= st})
    return vorschlaege


def verlauf_mit_vorschlag(verlauf: dict, eingaben, stichtag) -> dict:
    """Bestandsprognose plus zusaetzlicher Wareneingang (wie das Vorschlags-
    Diagramm in Excel). eingaben: Paare (Datum, Menge); Datum bis Stichtag
    zaehlt zum Rueckstand, Daten nach dem Horizont fallen weg.
    Rueckgabe: verlauf mit "vorschlag", neuem "bestand" / plus / minus,
    "erster_fehltag", "tiefster" und "ende"."""
    st = pd.Timestamp(stichtag).normalize()
    n = len(verlauf["bestand"])
    vorschlag = [0.0] * n
    for datum, menge in eingaben:
        if datum is None or menge is None or pd.isna(datum) or pd.isna(menge):
            continue
        d = pd.Timestamp(datum).normalize()
        i = 1 if d <= st else (d - st).days + 1
        if i < n:
            vorschlag[i] += float(menge)
    stand = float(verlauf["bestand"][0])
    bestand = [stand]
    for i in range(1, n):
        stand = stand + verlauf["zulauf"][i] + vorschlag[i] - verlauf["bedarf"][i]
        bestand.append(stand)
    return {
        **verlauf,
        "vorschlag": vorschlag,
        "bestand": bestand,
        "bestand_plus": [max(v, 0.0) for v in bestand],
        "fehl_minus": [min(v, 0.0) for v in bestand],
        "erster_fehltag": _erster_fehltag(bestand, verlauf["tage"]),
        "tiefster": min(bestand),
        "ende": bestand[-1],
    }


def berechne_bericht(
    positionen: pd.DataFrame,
    zugang: pd.DataFrame | None,
    stichtag,
    reaktion_tage: int = STANDARD_REAKTION_TAGE,
    wochen: int = STANDARD_WOCHEN,
    gedeckte_aufnehmen: bool = False,
    bestand_je_charge: pd.DataFrame | None = None,
) -> dict:
    """Rechnet alles fuer den Bericht. Rueckgabe-dict:
    artikel   DataFrame je Artikel (sortiert, mit Stufe/Rang, Ø-Bedarf, Reichweite)
    zeilen    DataFrame je offener Einteilung im Horizont (mit Deckungsherkunft)
    unterwegs DataFrame der Zugaenge (nur Artikel im Bericht), alle_zugaenge alle
    wochen    Liste der Wochenanfaenge (Montag) der Spalten nach "bis heute"
    matrix    {Norm-Nr: {"bedarf": [...], "zulauf": [...], "fehlt": [...]}}
              Index 0 = bis einschliesslich Stichtag, dann je Woche
    verlauf   {Norm-Nr: Bestandsprognose je Tag} (siehe _bestandsverlauf)
    vorschlag {Norm-Nr: vorgeschlagener Wareneingang} (siehe vorschlag_zugaenge)
    kunden    {Norm-Nr: DataFrame Kunde / Bedarf / Ø Woche / Ø Monat / Anteil}
    dashboard Kennzahlen fuer das Dashboard (je Stufe, Wochensummen, Unterwegs)
    sowie stichtag, reaktion_tage, wochen_horizont, horizont, basis (Ø-Basis).

    bestand_je_charge (optional, Charge-Ebene aus loaders.lade_bestand): dann
    zaehlt als Bestand nur, was wirklich verwendbar ist - je Charge auf volle
    Fuellmengen abgerundet, ohne OUT1 (wie in der Planung). Ohne: der Bestand
    aus logic.berechne."""
    st = pd.Timestamp(stichtag).normalize()
    grenze_kurz = st + pd.Timedelta(days=int(reaktion_tage))
    horizont = st + pd.Timedelta(days=7 * int(wochen))

    if zugang is None or zugang.empty:
        zugang = pd.DataFrame(columns=["Norm-Nr", "Ankunft gerechnet", "Geplante Ankunft", "Menge",
                                       "Referenz", "Transport", "Spediteur", "Hinweis"])
    zugang = zugang.copy()
    zugang["_reihe"] = range(len(zugang))
    zugang = zugang.sort_values(["Norm-Nr", "Ankunft gerechnet", "_reihe"], kind="stable")
    zugang_je_artikel = {n: g for n, g in zugang.groupby("Norm-Nr", sort=False)}

    nutzbar = None
    if bestand_je_charge is not None:
        nutzbar = bestand_logik.nutzbarer_bestand_je_artikel(bestand_je_charge, config.BESTAND_VERFUEGBAR)

    def _bestand_von(norm_nr, gruppe) -> float:
        if nutzbar is not None:
            return float(nutzbar.get(norm_nr, 0.0))
        return float(pd.to_numeric(gruppe["Bestand verfügbar"], errors="coerce").fillna(0).iloc[0])

    zeilen = []
    for norm_nr, gruppe in positionen.groupby("Norm-Nr", sort=False):
        bestand = _bestand_von(norm_nr, gruppe)
        zg = zugang_je_artikel.get(norm_nr, zugang.iloc[0:0])
        segmente = _segmente(bestand, zg)
        for index, r in gruppe.iterrows():
            offen = float(r["Offene Menge"])
            if offen <= 0 or pd.isna(r["Ladedatum"]) or r["Ladedatum"] > horizont:
                continue
            ladedatum = pd.Timestamp(r["Ladedatum"]).normalize()
            hoch = float(r["Kum. Bedarf Artikel"])
            tief = hoch - offen
            aus_bestand = rechtzeitig = spaet = 0.0
            quellen_rechtzeitig, quellen_spaet = [], []
            for von, bis, art, ankunft, referenz, transport in segmente:
                menge = min(hoch, bis) - max(tief, von)
                if menge <= 1e-9:
                    continue
                if art == "B":
                    aus_bestand += menge
                elif pd.Timestamp(ankunft) <= ladedatum:
                    rechtzeitig += menge
                    quellen_rechtzeitig.append((referenz, ankunft, menge))
                else:
                    spaet += menge
                    quellen_spaet.append((referenz, ankunft, menge))
            fehlt = max(0.0, offen - aus_bestand - rechtzeitig - spaet)
            if ladedatum <= st:
                bereich = "rueckstand"
            elif ladedatum <= grenze_kurz:
                bereich = "kurz"
            else:
                bereich = "lang"
            werk = str(r.get("Werk", "") or "").strip()
            ablade = str(r.get("Abladestelle", "") or "").strip()
            zeilen.append({
                "Position": index,
                "Norm-Nr": norm_nr,
                "Bereich": bereich,
                "Ladedatum": ladedatum,
                "Werk": werk,
                "Abladestelle": ablade,
                "Kunde": str(r.get("Kunde", "") or ""),
                "Wunschtermin": pd.Timestamp(r["Wunschtermin"]).normalize() if pd.notna(r.get("Wunschtermin")) else pd.NaT,
                "Offen": offen,
                "Aus Bestand": aus_bestand,
                "Rechtzeitig unterwegs": rechtzeitig,
                "Rechtzeitig": aus_bestand + rechtzeitig,
                "Spaet": spaet,
                "Fehlt": fehlt,
                "Quellen rechtzeitig": quellen_rechtzeitig,
                "Quellen spaet": quellen_spaet,
                "Tage bis Ladedatum": (ladedatum - st).days,
                "Transportart": str(r.get("Transportart", "") or ""),
            })
    zeilen_df = pd.DataFrame(zeilen)
    if zeilen_df.empty:
        zeilen_df = pd.DataFrame(columns=["Position", "Norm-Nr", "Bereich", "Ladedatum", "Kunde", "Offen", "Fehlt",
                                          "Spaet", "Rechtzeitig", "Aus Bestand", "Rechtzeitig unterwegs"])

    erste = positionen.drop_duplicates("Norm-Nr").set_index("Norm-Nr")
    vorhanden = erste["VW-Nr"] if "VW-Nr" in erste.columns else pd.Series("", index=erste.index)
    kundenmaterial = erste["Kundenmaterial"] if "Kundenmaterial" in erste.columns else pd.Series("", index=erste.index)
    stammdaten = pd.DataFrame({
        "VW-Nr": [vw_nr(n, v, k) for n, v, k in zip(erste.index, vorhanden, kundenmaterial)],
        "Kurztext": erste["Kurztext"].fillna("").astype(str),
        "Bestand": [_bestand_von(n, positionen.loc[positionen["Norm-Nr"] == n]) for n in erste.index],
    }, index=erste.index)

    # Basis fuer den Durchschnittsbedarf: Zeitraum, den der Bedarfsexport abdeckt
    if zeilen_df.empty:
        basis_von, basis_bis = st, st
    else:
        basis_von = min(st, zeilen_df["Ladedatum"].min())
        basis_bis = min(horizont, zeilen_df["Ladedatum"].max())
    wochen_basis = max(1.0, ((basis_bis - basis_von).days + 1) / 7.0)
    basis = {"von": basis_von, "bis": basis_bis, "wochen": wochen_basis}

    artikel = []
    for norm_nr, z in zeilen_df.groupby("Norm-Nr", sort=False):
        problem = z[(z["Fehlt"] > 0) | (z["Spaet"] > 0)]
        rueck = z[z["Bereich"] == "rueckstand"]
        kurz = z[z["Bereich"] == "kurz"]
        lang = z[z["Bereich"] == "lang"]
        erster = problem["Ladedatum"].min() if not problem.empty else pd.NaT
        if rueck["Fehlt"].sum() > 0:
            stufe = 1
        elif rueck["Spaet"].sum() > 0:
            stufe = 2
        elif pd.notna(erster) and erster <= grenze_kurz:
            stufe = 3
        elif pd.notna(erster):
            stufe = 4
        else:
            stufe = 5
        zg = zugang_je_artikel.get(norm_nr, zugang.iloc[0:0])
        kunden = sorted({k for k in z["Kunde"] if k})
        bestand = float(stammdaten.at[norm_nr, "Bestand"])
        unterwegs_menge = float(zg["Menge"].sum()) if not zg.empty else 0.0
        bedarf_gesamt = float(z["Offen"].sum())
        je_woche = bedarf_gesamt / wochen_basis
        artikel.append({
            "Norm-Nr": norm_nr,
            "VW-Nr": stammdaten.at[norm_nr, "VW-Nr"],
            "Kurztext": stammdaten.at[norm_nr, "Kurztext"],
            "Kunden": ", ".join(kunden),
            "Bestand": bestand,
            "Unterwegs": unterwegs_menge,
            "Anzahl NRI": int(zg["Referenz"].replace("", pd.NA).dropna().nunique()) if not zg.empty else 0,
            "Nächste Ankunft": zg["Ankunft gerechnet"].min() if not zg.empty else pd.NaT,
            "Rückstand fehlt": float(rueck["Fehlt"].sum()),
            "Rückstand später": float(rueck["Spaet"].sum()),
            "Kurz fehlt": float(kurz["Fehlt"].sum()),
            "Kurz später": float(kurz["Spaet"].sum()),
            "Später fehlt": float(lang["Fehlt"].sum()),
            "Fehlt gesamt": float(z["Fehlt"].sum()),
            "Erster Engpass": erster,
            "Bedarf Horizont": bedarf_gesamt,
            "Bedarf bis Reaktionszeit": float(z.loc[z["Ladedatum"] <= grenze_kurz, "Offen"].sum()),
            "Ältester Liefertermin": z["Wunschtermin"].min() if "Wunschtermin" in z.columns else pd.NaT,
            "Gedeckt": float(z["Fehlt"].sum()) <= 1e-9,
            "Ø Woche": je_woche,
            "Ø Monat": je_woche * 52.0 / 12.0,
            "Reichweite Wochen": ((bestand + unterwegs_menge) / je_woche) if je_woche > 0 else None,
            "Stufe": stufe,
        })
    artikel_df = pd.DataFrame(artikel)
    if artikel_df.empty:
        artikel_df = pd.DataFrame(columns=["Norm-Nr", "Stufe", "Erster Engpass", "Fehlt gesamt", "Rang"])
    else:
        if not gedeckte_aufnehmen:
            artikel_df = artikel_df[artikel_df["Stufe"] <= 4]
        # Zuerst alle Artikel, bei denen wirklich etwas fehlt (Handlungsbedarf
        # fuer die Produktion: nicht gedeckt bis zum Horizont), dann die, deren
        # Ware schon unterwegs ist; darin nach Stufe, erstem Engpass, Menge.
        artikel_df = artikel_df.assign(
            _ohne_fehlt=(artikel_df["Fehlt gesamt"] <= 0).astype(int),
            _menge=artikel_df["Fehlt gesamt"] + artikel_df["Rückstand später"] + artikel_df["Kurz später"],
        ).sort_values(["_ohne_fehlt", "Stufe", "Erster Engpass", "_menge", "Norm-Nr"],
                      ascending=[True, True, True, False, True], na_position="last", kind="stable")
        artikel_df = artikel_df.drop(columns=["_ohne_fehlt", "_menge"]).reset_index(drop=True)
        artikel_df["Rang"] = range(1, len(artikel_df) + 1)

    im_bericht = set(artikel_df["Norm-Nr"])
    zeilen_df = zeilen_df[zeilen_df["Norm-Nr"].isin(im_bericht)].reset_index(drop=True)
    unterwegs = zugang[zugang["Norm-Nr"].isin(im_bericht)].drop(columns="_reihe").reset_index(drop=True)
    alle_zugaenge = zugang.drop(columns="_reihe").reset_index(drop=True)

    # Wochenraster: Index 0 = bis einschliesslich Stichtag, danach Kalenderwochen
    erste_woche = _montag(st)
    anzahl = (_montag(horizont) - erste_woche).days // 7 + 1
    wochen_liste = [erste_woche + pd.Timedelta(days=7 * i) for i in range(anzahl)]

    def _spalte(datum) -> int | None:
        datum = pd.Timestamp(datum).normalize()
        if datum <= st:
            return 0
        if datum > horizont:
            return None
        return (_montag(datum) - erste_woche).days // 7 + 1

    matrix, verlauf, kunden_je_artikel, vorschlag = {}, {}, {}, {}
    for norm_nr in artikel_df["Norm-Nr"]:
        az = zeilen_df[zeilen_df["Norm-Nr"] == norm_nr]
        zg = unterwegs[unterwegs["Norm-Nr"] == norm_nr]
        werte = {k: [0.0] * (anzahl + 1) for k in ("bedarf", "zulauf", "fehlt")}
        for _, z in az.iterrows():
            i = _spalte(z["Ladedatum"])
            if i is not None:
                werte["bedarf"][i] += z["Offen"]
                werte["fehlt"][i] += z["Fehlt"]
        for _, z in zg.iterrows():
            i = _spalte(z["Ankunft gerechnet"])
            if i is not None:
                werte["zulauf"][i] += float(z["Menge"])
        matrix[norm_nr] = werte
        verlauf[norm_nr] = _bestandsverlauf(float(stammdaten.at[norm_nr, "Bestand"]), az, zg, st, horizont)
        vorschlag[norm_nr] = vorschlag_zugaenge(az, st)
        je_kunde = az.groupby("Kunde")["Offen"].sum().sort_values(ascending=False)
        gesamt = float(je_kunde.sum()) or 1.0
        kunden_je_artikel[norm_nr] = pd.DataFrame({
            "Kunde": [k or "–" for k in je_kunde.index],
            "Bedarf": je_kunde.values,
            "Ø Woche": je_kunde.values / wochen_basis,
            "Ø Monat": je_kunde.values / wochen_basis * 52.0 / 12.0,
            "Anteil": je_kunde.values / gesamt,
        })

    # Dashboard-Kennzahlen
    if artikel_df.empty:
        je_stufe = {s: {"anzahl": 0, "menge": 0.0} for s in STUFEN}
        wochen_summen = {k: [0.0] * (anzahl + 1) for k in ("bedarf", "zulauf", "fehlt")}
    else:
        mengen_spalte = {1: "Rückstand fehlt", 2: "Rückstand später", 3: "Kurz fehlt", 4: "Später fehlt", 5: "Bedarf Horizont"}
        je_stufe = {
            s: {"anzahl": int((artikel_df["Stufe"] == s).sum()),
                "menge": float(artikel_df.loc[artikel_df["Stufe"] == s, mengen_spalte[s]].sum())}
            for s in STUFEN
        }
        wochen_summen = {
            k: [sum(matrix[n][k][i] for n in matrix) for i in range(anzahl + 1)]
            for k in ("bedarf", "zulauf", "fehlt")
        }
    dashboard = {
        "artikel": int(len(artikel_df)),
        "je_stufe": je_stufe,
        "fehlt_gesamt": float(artikel_df["Fehlt gesamt"].sum()) if not artikel_df.empty else 0.0,
        "rueckstand_spaeter": float(artikel_df["Rückstand später"].sum()) if not artikel_df.empty else 0.0,
        "nri": int(alle_zugaenge["Referenz"].replace("", pd.NA).dropna().nunique()) if not alle_zugaenge.empty else 0,
        "nri_bericht": int(unterwegs["Referenz"].replace("", pd.NA).dropna().nunique()) if not unterwegs.empty else 0,
        "unterwegs_menge": float(unterwegs["Menge"].sum()) if not unterwegs.empty else 0.0,
        "naechste_ankunft": unterwegs["Ankunft gerechnet"].min() if not unterwegs.empty else pd.NaT,
        "wochen_summen": wochen_summen,
    }

    return {
        "artikel": artikel_df,
        "zeilen": zeilen_df,
        "unterwegs": unterwegs,
        "alle_zugaenge": alle_zugaenge,
        "stammdaten": stammdaten,
        "wochen": wochen_liste,
        "matrix": matrix,
        "verlauf": verlauf,
        "vorschlag": vorschlag,
        "kunden": kunden_je_artikel,
        "dashboard": dashboard,
        "basis": basis,
        "stichtag": st,
        "reaktion_tage": int(reaktion_tage),
        "wochen_horizont": int(wochen),
        "horizont": horizont,
    }


# --- Notizen aus einem frueheren Bericht -------------------------------------

def _finde_kopfzeile(ws, max_zeile: int = 60) -> int | None:
    """Zeile, in der die Tabellenueberschrift steht (Spalte A beginnt mit 'Nr.'
    bzw. 'Norm-Nr' im Archiv) - unabhaengig von der Hoehe des Dashboards."""
    for r in range(1, min(ws.max_row, max_zeile) + 1):
        text = str(ws.cell(r, 1).value or "")
        if text.startswith("Nr.") or text.startswith("Norm-Nr"):
            return r
    return None


def _kopf_spalten(ws, zeile: int) -> dict:
    spalten = {}
    for zelle in ws[zeile]:
        text = str(zelle.value or "").split("\n")[0].strip()
        if text:
            spalten[text] = zelle.column
    return spalten


def _notiz_wert(wert) -> str:
    if wert is None:
        return ""
    text = str(wert).strip()
    return "" if text.startswith("=") else text


def lese_notizen(inhalt: bytes) -> dict:
    """Norm-Nr -> {"dispo": ..., "produktion": ...} aus einem frueheren Bericht
    (Uebersicht, ggf. direkt in Details getippte Notizen, Notizen-Archiv)."""
    wb = load_workbook(io.BytesIO(inhalt))
    notizen: dict = {}

    def _merken(norm, dispo, produktion):
        norm = materialnr(norm)
        if norm is None:
            return
        eintrag = notizen.setdefault(norm, {"dispo": "", "produktion": ""})
        for schluessel, text in (("dispo", dispo), ("produktion", produktion)):
            if text and text not in eintrag[schluessel]:
                eintrag[schluessel] = f"{eintrag[schluessel]} | {text}" if eintrag[schluessel] else text

    for blatt in (BLATT_UEBERSICHT, BLATT_ARCHIV):
        if blatt not in wb.sheetnames:
            continue
        ws = wb[blatt]
        kopf = _finde_kopfzeile(ws)
        if kopf is None:
            continue
        spalten = _kopf_spalten(ws, kopf)
        s_norm, s_dispo, s_prod = spalten.get("Norm-Nr"), spalten.get("Notiz Dispo"), spalten.get("Notiz Produktion")
        if not (s_norm and (s_dispo or s_prod)):
            continue
        for r in range(kopf + 1, ws.max_row + 1):
            _merken(ws.cell(r, s_norm).value,
                    _notiz_wert(ws.cell(r, s_dispo).value) if s_dispo else "",
                    _notiz_wert(ws.cell(r, s_prod).value) if s_prod else "")

    if BLATT_DETAILS in wb.sheetnames:
        ws = wb[BLATT_DETAILS]
        for r in range(ERSTE_ZEILE, ws.max_row + 1):
            norm = ws.cell(r, DETAIL_NORM_SPALTE).value
            if norm is not None:
                _merken(norm, _notiz_wert(ws.cell(r, DETAIL_NOTIZ_DISPO).value),
                        _notiz_wert(ws.cell(r, DETAIL_NOTIZ_PROD).value))
    return {n: e for n, e in notizen.items() if e["dispo"] or e["produktion"]}


# --- Excel -------------------------------------------------------------------

# Ruhige, moderne Optik: Grautoene (Slate) fuer Text und Linien, Farbe nur als
# Akzent (Dringlichkeit, Fehlmengen, Eingabefelder). Keine Gitternetzlinien.
_TEXT = "1E293B"
_TEXT_MITTEL = "475569"
_TEXT_HELL = "94A3B8"
_LINIE = "E2E8F0"
_FLAECHE = "F8FAFC"
_KOPF_HG = "F1F5F9"
_LINK = "2563EB"
_ROT = "DC2626"
_ORANGE = "C2410C"
_BLAU = "1D4ED8"
_GRUEN = "15803D"
_EINGABE_HG, _EINGABE_RAND = "FEF9C3", "EAB308"
_DISPO_HG, _DISPO_RAND, _DISPO_TEXT = "EFF6FF", "BFDBFE", "1E40AF"
_PROD_HG, _PROD_RAND, _PROD_TEXT = "FFF7ED", "FED7AA", "9A3412"
# Diagrammfarben
_D_BESTAND, _D_BESTAND_RAND = "D1FAE5", "10B981"
_D_FEHL, _D_FEHL_RAND = "FEE2E2", "EF4444"
_D_BEDARF, _D_ZULAUF, _D_VORSCHLAG_FARBE = "94A3B8", "3B82F6", "F59E0B"

_DUENN = Side(style="thin", color="CBD5E1")
_DICK = Side(style="medium", color="94A3B8")
_LINIE_DUENN = Side(style="thin", color=_LINIE)
_WEISS_DICK = Side(style="thick", color="FFFFFF")
_UNTEN = Border(bottom=_LINIE_DUENN)
_RAHMEN = Border(left=_DUENN, right=_DUENN, top=_DUENN, bottom=_DUENN)
_DISPO_FUELLUNG = PatternFill("solid", fgColor=_DISPO_HG)
_PROD_FUELLUNG = PatternFill("solid", fgColor=_PROD_HG)
_MENGE = '#,##0;-#,##0;""'
_MENGE_NULL = "#,##0"
_MENGE_VORZEICHEN = '#,##0;[Red]-#,##0;0'
_DATUM = "DD.MM.YYYY"


def _fuellung(farbe: str) -> PatternFill:
    return PatternFill("solid", fgColor=farbe)


def _schrift(groesse: float = 10, farbe: str = _TEXT, fett: bool = False, **kw) -> Font:
    return Font(name="Calibri", size=groesse, color=farbe, bold=fett, **kw)


def _rahmen(farbe: str, stil: str = "thin") -> Border:
    seite = Side(style=stil, color=farbe)
    return Border(left=seite, right=seite, top=seite, bottom=seite)


def _zusammen(ws, zeile: int, von: int, bis: int, wert=None, bis_zeile: int | None = None):
    """Zellen verbinden (falls mehr als eine) und Wert in die erste schreiben."""
    bis_zeile = bis_zeile or zeile
    if bis > von or bis_zeile > zeile:
        ws.merge_cells(start_row=zeile, start_column=von, end_row=bis_zeile, end_column=bis)
    zelle = ws.cell(zeile, von)
    if wert is not None:
        zelle.value = wert
    return zelle


def _stil_bereich(ws, zeile: int, von: int, bis: int, fuellung=None, rahmen=None, bis_zeile: int | None = None) -> None:
    for r in range(zeile, (bis_zeile or zeile) + 1):
        for s in range(von, bis + 1):
            if fuellung is not None:
                ws.cell(r, s).fill = fuellung
            if rahmen is not None:
                ws.cell(r, s).border = rahmen


def _reich(*teile):
    """Text mit mehreren Schriften in einer Zelle: _reich((text, InlineFont), ...)."""
    return CellRichText(*[TextBlock(font, text) for text, font in teile if text])


def _inline(groesse: float = 10, farbe: str = _TEXT, fett: bool = False) -> InlineFont:
    return InlineFont(rFont="Calibri", sz=groesse, color=farbe, b=fett)


UEBERSICHT_SPALTEN = [
    # (Kopf DE, Kopf TR, Breite)
    ("Nr.", "No", 5),
    ("Details", "Detay", 11),
    ("Norm-Nr", "Parça No", 13),
    ("VW-Nr", "VW No", 17),
    ("Bestand (nutzbar)", "Kullanılabilir stok", 13),
    ("Rückstand + {tage} Tage", "Gecikme + {tage} gün", 14),
    ("Unterwegs", "Yolda", 12),
    ("NRI · Ankunft · Menge", "NRI · Varış · Miktar", 38),
    ("Gedeckt bis {wochen} Wo.?", "{wochen} hf. karşılanıyor mu?", 15),
    ("Ältester Abruf (Liefertermin)", "En eski çağrı (teslim tarihi)", 16),
    ("Notiz Dispo", "Dispo notu", 38),
    ("Notiz Produktion", "Üretim notu (Türkiye)", 38),
]
U_DETAILS, U_NORM, U_NRI, U_NOTIZ_DISPO, U_NOTIZ_PROD = 2, 3, 8, 11, 12
_U_SPALTE = {name: i for i, (name, _, _) in enumerate(UEBERSICHT_SPALTEN, start=1)}
# Kacheln oben in der Uebersicht: (von, bis) Spalten
_U_KACHELN = [(1, 3), (4, 5), (6, 7), (8, 8), (9, 10)]
_U_ZEILENHOEHE = 18

# Details: ein Raster aus gleich breiten Spalten, damit Kacheln, Diagramme und
# Tabellen in jeder Karte sauber untereinander stehen.
DETAIL_BREITEN = [3, 14, 11, 12, 12, 12, 12, 11, 12, 12, 18, 13, 12, 12, 12, 2]   # A..P
DETAIL_NOTIZ_DISPO, DETAIL_NOTIZ_PROD, DETAIL_NORM_SPALTE = 3, 10, 16
_D_ERSTE, _D_LETZTE = 2, 15          # Karte: Spalten B..O
_D_DIAGRAMM_BIS = 10                 # Diagramme: B..J
_D_PANEL = 11                        # rechts daneben: K..O
_EINGABE_DATUM, _EINGABE_MENGE = 11, 12   # K, L: gelbe Eingabefelder
DIAGRAMM_ZEILENHOEHE = 18            # feste Zeilenhoehe neben den Diagrammen (nichts verschiebt sich)

UNTERWEGS_SPALTEN = [
    ("NRI", "NRI", 19),
    ("Transport", "Sevkiyat", 11),
    ("Spediteur", "Nakliyeci", 30),
    ("Geplante Ankunft", "Planlanan varış", 13),
    ("Hinweis", "Açıklama", 30),
    ("Norm-Nr", "Parça No", 12),
    ("VW-Nr", "VW No", 16),
    ("Bezeichnung", "Tanım", 28),
    ("Menge", "Miktar", 11),
    ("Nr. im Bericht", "Rapordaki No", 10),
]

# Diagrammdaten je Artikel (Spalten im ausgeblendeten Blatt), je Woche
_DATEN_KOPF = ("Zeitpunkt / Zaman", "Bedarf / İhtiyaç", "Unterwegs (NRI) / Yolda", "Bestand / Stok",
               "Fehlmenge / Eksik", "von", "bis (ohne)", "Vorschlag / Öneri", "Stand mit Vorschlag",
               "Bestand mit Vorschlag / Öneri ile stok", "Fehlmenge / Eksik", "Index Fehltag")
_D_VON, _D_BIS, _D_VORSCHLAG, _D_STAND, _D_PLUS, _D_MINUS, _D_INDEX = 6, 7, 8, 9, 10, 11, 12


def _kopf_stil(zelle) -> None:
    zelle.fill = _fuellung(_KOPF_HG)
    zelle.font = _schrift(9, _TEXT_MITTEL, True)
    zelle.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    zelle.border = Border(bottom=_DICK)


def _kopf(ws, spalten, reaktion_tage: int = STANDARD_REAKTION_TAGE, wochen: int = STANDARD_WOCHEN,
          zeile: int = KOPFZEILE) -> None:
    for i, (de, tr, breite) in enumerate(spalten, start=1):
        text = f"{de.format(tage=reaktion_tage, wochen=wochen)}\n{tr.format(tage=reaktion_tage, wochen=wochen)}".strip()
        zelle = ws.cell(zeile, i, value=text)
        _kopf_stil(zelle)
        ws.column_dimensions[get_column_letter(i)].width = breite
    ws.row_dimensions[zeile].height = 34


def _titel(ws, titel_de: str, titel_tr: str, stand: pd.Timestamp, zeilen: list[str]) -> None:
    ws.sheet_view.showGridLines = False
    ws.cell(1, 1, value=_reich((f"{titel_de}  ·  {titel_tr}", _inline(16, _TEXT, True)),
                               (f"     Stand / Tarih {stand:%d.%m.%Y}", _inline(10, _TEXT_HELL))))
    ws.row_dimensions[1].height = 26
    for i, text in enumerate(zeilen[:2], start=2):
        ws.cell(i, 1, value=text).font = _schrift(9, _TEXT_MITTEL)


def _druck(ws, kopfzeile: int | None = KOPFZEILE, hochformat: bool = False) -> None:
    ws.page_setup.orientation = "portrait" if hochformat else "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    if kopfzeile:
        ws.print_title_rows = f"{kopfzeile}:{kopfzeile}"
    ws.print_options.gridLines = False


def _status_etikett(zelle, gedeckt: bool, groesse: float = 10, text: str | None = None) -> None:
    """Der eine Status: bis zum Horizont gedeckt? Ja = gruen, Nein = rot."""
    zelle.value = text or ("Ja / Evet" if gedeckt else "Nein / Hayır")
    zelle.fill = _fuellung(STUFEN[5]["fill"] if gedeckt else STUFEN[1]["fill"])
    zelle.font = _schrift(groesse, STUFEN[5]["font"] if gedeckt else STUFEN[1]["font"], True)
    zelle.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _datum_wert(wert):
    return pd.Timestamp(wert).to_pydatetime() if wert is not None and pd.notna(wert) else None


def _text_eigenschaften(groesse: int = 800, farbe: str = _TEXT_MITTEL) -> RichText:
    cp = CharacterProperties(sz=groesse, solidFill=farbe)
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])


def _diagramm_stil(chart) -> None:
    """Flach und ruhig: kein Rahmen, keine runden Ecken, helle Hilfslinien,
    kleine graue Achsenbeschriftung, Legende unten."""
    chart.x_axis.delete = False          # openpyxl 3.1 laesst Achsen sonst in Excel weg
    chart.y_axis.delete = False
    chart.roundedCorners = False
    chart.graphical_properties = GraphicalProperties(ln=LineProperties(noFill=True))
    chart.y_axis.majorGridlines = ChartLines(spPr=GraphicalProperties(ln=LineProperties(solidFill=_LINIE)))
    chart.y_axis.spPr = GraphicalProperties(ln=LineProperties(noFill=True))
    chart.x_axis.spPr = GraphicalProperties(ln=LineProperties(solidFill="CBD5E1"))
    chart.x_axis.txPr = _text_eigenschaften(900)
    chart.y_axis.txPr = _text_eigenschaften(900)
    if chart.legend is not None:
        chart.legend.position = "b"
        chart.legend.txPr = _text_eigenschaften(900, _TEXT_MITTEL)


def _anker(chart, von_spalte: int, von_zeile: int, bis_spalte: int, bis_zeile: int) -> None:
    """Diagramm genau in einen Zellbereich legen (Zwei-Zellen-Anker): es kann
    weder in die Tabelle daneben noch in die Zeilen darunter ragen."""
    anker = TwoCellAnchor(editAs="twoCell")
    anker._from = AnchorMarker(col=von_spalte - 1, row=von_zeile - 1, colOff=38100, rowOff=38100)
    anker.to = AnchorMarker(col=bis_spalte, row=bis_zeile, colOff=0, rowOff=0)
    chart.anchor = anker


# --- Diagrammdaten (ausgeblendetes Blatt) ------------------------------------

def wochen_verlauf(verlauf: dict, stichtag, sprache: str = "TR") -> dict:
    """Tagesprognose auf Wochen verdichtet (lesbarer im Diagramm): Punkt 0 =
    Bestand heute, 1 = nach Rueckstand (bis Stichtag), dann je Kalenderwoche.
    Bedarf/Zulauf je Woche summiert, Bestand = Stand am letzten Tag der Woche.
    von/bis = Datumsgrenzen je Punkt (bis ohne) fuer die Vorschlags-Formeln."""
    st = pd.Timestamp(stichtag).normalize()
    labels = ["Bestand", "Rückst."] if sprache == "DE" else ["Stok", "Gecikme"]
    von, bis = [None, None], [None, st + pd.Timedelta(days=1)]
    bedarf, zulauf, bestand = [verlauf["bedarf"][0], verlauf["bedarf"][1]], \
        [verlauf["zulauf"][0], verlauf["zulauf"][1]], [verlauf["bestand"][0], verlauf["bestand"][1]]
    vorschlag = verlauf.get("vorschlag")
    vorsch = [vorschlag[0], vorschlag[1]] if vorschlag else None
    aktuell = None
    for i in range(2, len(verlauf["tage"])):
        tag = pd.Timestamp(verlauf["tage"][i])
        woche = _montag(tag)
        if woche != aktuell:
            aktuell = woche
            kw = woche.isocalendar()[1]
            labels.append(f"KW {kw}" if sprache == "DE" else f"{kw}. hf.")
            von.append(tag)
            bis.append(tag + pd.Timedelta(days=1))
            bedarf.append(0.0)
            zulauf.append(0.0)
            bestand.append(0.0)
            if vorsch is not None:
                vorsch.append(0.0)
        bis[-1] = tag + pd.Timedelta(days=1)
        bedarf[-1] += verlauf["bedarf"][i]
        zulauf[-1] += verlauf["zulauf"][i]
        bestand[-1] = verlauf["bestand"][i]
        if vorsch is not None:
            vorsch[-1] += vorschlag[i]
    ergebnis = {"labels": labels, "von": von, "bis": bis, "bedarf": bedarf, "zulauf": zulauf, "bestand": bestand,
                "bestand_plus": [max(v, 0.0) for v in bestand], "fehl_minus": [min(v, 0.0) for v in bestand]}
    if vorsch is not None:
        ergebnis["vorschlag"] = vorsch
    return ergebnis


def _schreibe_diagrammdaten(ws, bericht: dict, sprache: str = "TR") -> dict:
    """Zahlen hinter den Prognose-Diagrammen, je Woche. Spalten je Artikel:
    1 Zeitpunkt, 2 Bedarf, 3 Unterwegs (NRI), 4 Bestand >= 0, 5 Fehlmenge <= 0,
    6/7 Datum von/bis; 8..12 (Vorschlag) schreibt _schreibe_vorschlag_formeln.
    Rueckgabe: {"artikel": {Norm-Nr: (kopfzeile, anzahl_punkte)}}."""
    ws.sheet_state = "hidden"
    ws.cell(1, 1, value="Zahlen und Formeln hinter den Diagrammen - bitte nicht ändern / "
                        "Grafiklerin verileri - lütfen değiştirmeyin")
    positionen = {"artikel": {}}
    zeile = 3
    for norm, v in bericht["verlauf"].items():
        w = wochen_verlauf(v, bericht["stichtag"], sprache)
        ws.cell(zeile, 1, value=f"Artikel {norm}")
        kopf = zeile + 1
        for s, text in enumerate(_DATEN_KOPF, start=1):
            ws.cell(kopf, s, value=text)
        n = len(w["labels"])
        for i in range(n):
            r = kopf + 1 + i
            ws.cell(r, 1, value=w["labels"][i])
            ws.cell(r, 2, value=w["bedarf"][i])
            ws.cell(r, 3, value=w["zulauf"][i])
            ws.cell(r, 4, value=w["bestand_plus"][i])
            ws.cell(r, 5, value=w["fehl_minus"][i])
            for s, wert in ((_D_VON, w["von"][i]), (_D_BIS, w["bis"][i])):
                if wert is not None:
                    ws.cell(r, s, value=_datum_wert(wert)).number_format = _DATUM
        positionen["artikel"][norm] = (kopf, n)
        zeile = kopf + n + 2
    return positionen


def _schreibe_vorschlag_formeln(ws_daten, kopf: int, n: int, start_bestand: float,
                                eingabe_von: int, eingabe_bis: int) -> None:
    """Formeln fuer das Vorschlags-Diagramm: Zugang je Woche aus den gelben
    Eingabefeldern (SUMIFS ueber von/bis), laufender Bestand = Vorwoche +
    Unterwegs + Vorschlag - Bedarf. Excel rechnet bei jeder Aenderung neu - das
    Diagramm folgt live."""
    blatt = f"'{BLATT_DETAILS}'"
    d = get_column_letter(_EINGABE_DATUM)
    m = get_column_letter(_EINGABE_MENGE)
    datum = f"{blatt}!${d}${eingabe_von}:${d}${eingabe_bis}"
    menge = f"{blatt}!${m}${eingabe_von}:${m}${eingabe_bis}"
    von, bis = get_column_letter(_D_VON), get_column_letter(_D_BIS)
    vorschlag, stand = get_column_letter(_D_VORSCHLAG), get_column_letter(_D_STAND)
    for i in range(n):
        r = kopf + 1 + i
        if i == 0:
            ws_daten.cell(r, _D_VORSCHLAG, value=0)
            ws_daten.cell(r, _D_STAND, value=float(start_bestand))
        else:
            if i == 1:   # Rueckstand: alles mit Datum bis einschliesslich Stichtag
                formel = f'=SUMIFS({menge},{datum},"<"&{bis}{r})'
            else:
                formel = f'=SUMIFS({menge},{datum},">="&{von}{r},{datum},"<"&{bis}{r})'
            ws_daten.cell(r, _D_VORSCHLAG, value=formel)
            ws_daten.cell(r, _D_STAND, value=f"={stand}{r - 1}+C{r}+{vorschlag}{r}-B{r}")
        ws_daten.cell(r, _D_PLUS, value=f"=MAX({stand}{r},0)")
        ws_daten.cell(r, _D_MINUS, value=f"=MIN({stand}{r},0)")
        ws_daten.cell(r, _D_INDEX, value=f'=IF({stand}{r}<-0.000001,{i},"")')


def _prognose_diagramm(ws_daten, kopf: int, n: int, mit_vorschlag: bool = False):
    """Bestandsprognose je Woche: gruene Flaeche = Bestand, rote Flaeche =
    Fehlmenge (unter null), Balken = Bedarf (grau), Unterwegs/NRI (blau) und -
    im Vorschlags-Diagramm - vorgeschlagener Wareneingang (orange)."""
    erste, letzte = kopf + 1, kopf + n
    area = AreaChart()
    area.grouping = "standard"
    flaeche = (_D_PLUS, _D_MINUS) if mit_vorschlag else (4, 5)
    area.add_data(Reference(ws_daten, min_col=flaeche[0], max_col=flaeche[1], min_row=kopf, max_row=letzte),
                  titles_from_data=True)
    area.set_categories(Reference(ws_daten, min_col=1, min_row=erste, max_row=letzte))
    for s, fuellung, rand in zip(area.series, (_D_BESTAND, _D_FEHL), (_D_BESTAND_RAND, _D_FEHL_RAND)):
        s.graphicalProperties.solidFill = fuellung
        s.graphicalProperties.line.solidFill = rand
        s.graphicalProperties.line.width = 31750     # 2,5 pt - gut sichtbar
    bar = BarChart()
    bar.type = "col"
    bar.grouping = "clustered"
    bar.overlap = 0
    bar.gapWidth = 60
    bar.add_data(Reference(ws_daten, min_col=2, max_col=3, min_row=kopf, max_row=letzte), titles_from_data=True)
    if mit_vorschlag:
        bar.add_data(Reference(ws_daten, min_col=_D_VORSCHLAG, max_col=_D_VORSCHLAG, min_row=kopf, max_row=letzte),
                     titles_from_data=True)
    for s, farbe in zip(bar.series, (_D_BEDARF, _D_ZULAUF, _D_VORSCHLAG_FARBE)):
        s.graphicalProperties.solidFill = farbe
        s.graphicalProperties.line.noFill = True
    area += bar   # Kombi-Diagramm: Flaechen + Balken auf denselben Achsen
    area.x_axis.tickLblSkip = 1 if n <= 14 else 2   # jede 2. Woche beschriften - sonst kippt Excel die Texte
    area.x_axis.tickLblPos = "low"     # Wochen unten, auch wenn der Bestand unter null faellt
    area.y_axis.number_format = "#,##0"
    _diagramm_stil(area)
    return area


# --- Uebersicht ---------------------------------------------------------------

def _kachel(ws, zeile: int, von: int, bis: int, titel: str, wert, untertitel: str, akzent: str,
            wertfarbe: str, dunkel: bool = False, zahlenformat: str | None = None) -> None:
    """Kennzahl-Kachel ueber drei Zeilen: Titel, grosse Zahl, Untertitel.
    Farbiger Strich oben, weisser Rand links/rechts = Abstand zur Nachbarkachel."""
    hg = _TEXT if dunkel else _FLAECHE
    for r, text, font in (
        (zeile, titel, _schrift(8, "CBD5E1" if dunkel else _TEXT_MITTEL, True)),
        (zeile + 1, wert, _schrift(20, "FFFFFF" if dunkel else wertfarbe, True)),
        (zeile + 2, untertitel, _schrift(8, "CBD5E1" if dunkel else _TEXT_HELL)),
    ):
        zelle = _zusammen(ws, r, von, bis, text)
        zelle.font = font
        zelle.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1)
        if r == zeile + 1 and zahlenformat:
            zelle.number_format = zahlenformat
        for s in range(von, bis + 1):
            ws.cell(r, s).fill = _fuellung(hg)
            ws.cell(r, s).border = Border(
                left=_WEISS_DICK if s == von else None, right=_WEISS_DICK if s == bis else None,
                top=Side(style="thick", color=akzent) if r == zeile else None,
            )


def _schreibe_kacheln(ws, bericht: dict, zeile: int = 4) -> None:
    d, rt, wo, st = bericht["dashboard"], bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    a = bericht["artikel"]
    offen = int((~a["Gedeckt"].astype(bool)).sum()) if not a.empty else 0
    gedeckt = len(a) - offen
    kurz = float(a["Bedarf bis Reaktionszeit"].sum()) if not a.empty else 0.0
    ankunft = d["naechste_ankunft"]
    kacheln = [
        (f"Handlungsbedarf (nicht gedeckt bis {wo} Wo.)  /  Aksiyon gerekli", offen,
         f"von {len(a)} Artikeln / parçadan", _ROT, "FFFFFF", True, "0"),
        ("Fehlt gesamt  /  Toplam eksik", d["fehlt_gesamt"], "Stück aus der Türkei / Türkiye'den adet",
         _ROT, _ROT if d["fehlt_gesamt"] else _TEXT_HELL, False, _MENGE_NULL),
        (f"Rückstand + {rt} Tage  /  Gecikme + {rt} gün", kurz,
         f"Stück Bedarf bis {st + pd.Timedelta(days=rt):%d.%m.} / adet ihtiyaç", STUFEN[3]["balken"],
         STUFEN[3]["font"] if kurz else _TEXT_HELL, False, _MENGE_NULL),
        ("Unterwegs zu uns (NRI)  /  Bize doğru yolda", d["unterwegs_menge"],
         f"Stück · {d['nri_bericht']} NRI" + (f" · ab / ilk {_datum_kurz(ankunft)}" if pd.notna(ankunft) else ""),
         _LINK, _BLAU if d["unterwegs_menge"] else _TEXT_HELL, False, _MENGE_NULL),
        (f"Gedeckt bis {wo} Wo.  /  Karşılanıyor", gedeckt, "kein Handlungsbedarf / aksiyon gerekmez",
         STUFEN[5]["balken"], STUFEN[5]["font"] if gedeckt else _TEXT_HELL, False, "0"),
    ]
    for (titel, wert, unter, akzent, farbe, dunkel, fmt), (von, bis) in zip(kacheln, _U_KACHELN):
        _kachel(ws, zeile, von, bis, titel, wert, unter, akzent, farbe, dunkel, fmt)
    ws.row_dimensions[zeile].height = 26
    ws.row_dimensions[zeile + 1].height = 34
    ws.row_dimensions[zeile + 2].height = 24


def _nri_zeilen(unterwegs: pd.DataFrame, plaetze: int = ZEILEN_JE_ARTIKEL) -> list[str]:
    """NRI-Liste fuer die Uebersicht: je NRI "NRI · Ankunft · Menge", nach
    Ankunft. Passen nicht alle in die Zeilen, steht in der letzten "+ n weitere"."""
    if unterwegs is None or unterwegs.empty:
        return []
    je_nri = (unterwegs.assign(Referenz=unterwegs["Referenz"].fillna("").astype(str).replace("", "NRI ?"))
              .groupby("Referenz", sort=False)
              .agg(Ankunft=("Ankunft gerechnet", "min"), Menge=("Menge", "sum"))
              .sort_values("Ankunft"))
    zeilen = [f"{nri}  ·  {_datum_kurz(z['Ankunft'])}  ·  {_menge_text(z['Menge'])}" for nri, z in je_nri.iterrows()]
    if len(zeilen) > plaetze:
        rest = len(zeilen) - (plaetze - 1)
        zeilen = zeilen[:plaetze - 1] + [f"+ {rest} weitere / diğer → Details"]
    return zeilen


def _schreibe_uebersicht(ws, bericht: dict, notizen: dict) -> dict:
    a, unterwegs = bericht["artikel"], bericht["unterwegs"]
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    ws.sheet_view.showGridLines = False
    ws.cell(1, 1, value=_reich(("Lieferübersicht für die Produktion", _inline(18, _TEXT, True)),
                               ("   ·   Üretim için teslimat özeti", _inline(14, _TEXT_HELL, True))))
    ws.cell(2, 1, value=f"Stand / Tarih {st:%d.%m.%Y}   ·   {len(a)} Artikel / parça   ·   Reaktionszeit / "
                        f"Reaksiyon süresi {rt} Tage / gün   ·   Vorschau / Önizleme {wo} Wochen / hafta"
                        ).font = _schrift(9, _TEXT_MITTEL)
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 16
    ws.row_dimensions[3].height = 8
    _schreibe_kacheln(ws, bericht, 4)
    ws.row_dimensions[7].height = 10
    ws.cell(8, 1, value=_reich(
        ("👁 Details anklicken → Prognose, NRI und Abrufe je Artikel", _inline(9, _LINK, True)),
        ("  ·  👁 Detay'a tıklayın → tahmin, NRI ve çağrılar", _inline(9, _LINK)),
        ("     Bestand = nur nutzbare Menge (volle KLT je Charge) · „Gedeckt“ = Bestand + unterwegs reichen bis "
         f"{wo} Wochen / Stok = sadece kullanılabilir miktar · „Karşılanıyor“ = stok + yolda {wo} haftaya yetiyor",
         _inline(9, _TEXT_HELL)),
    ))
    ws.row_dimensions[8].height = 18
    _kopf(ws, UEBERSICHT_SPALTEN, rt, wo, zeile=UEBERSICHT_KOPFZEILE)
    ws.row_dimensions[UEBERSICHT_KOPFZEILE].height = 46
    if a.empty:
        ws.cell(UEBERSICHT_ERSTE_ZEILE, 1,
                value="Nichts zu melden: kein Rückstand und keine Fehlmenge im Vorschauzeitraum. / "
                      "Bildirilecek bir şey yok.").font = _schrift(10, _GRUEN, italic=True)
    zeilen_je_artikel = {}
    letzte_spalte = len(UEBERSICHT_SPALTEN)
    for k, r in enumerate(a.itertuples(index=False)):
        werte = {c: r[a.columns.get_loc(c)] for c in a.columns}
        norm = werte["Norm-Nr"]
        i = UEBERSICHT_ERSTE_ZEILE + k * ZEILEN_JE_ARTIKEL
        unten = i + ZEILEN_JE_ARTIKEL - 1
        zeilen_je_artikel[norm] = i
        n = notizen.get(norm, {})
        aeltester = werte.get("Ältester Liefertermin")
        inhalt = [
            ("Nr.", werte["Rang"], None, _schrift(9, _TEXT_HELL), "center"),
            ("Details", "👁 Details", None, _schrift(9, _LINK, True), "center"),
            ("Norm-Nr", norm, None, _schrift(11, _TEXT, True), "left"),
            ("VW-Nr", werte["VW-Nr"] or None, None, _schrift(10, _TEXT_MITTEL), "left"),
            ("Bestand (nutzbar)", werte["Bestand"], _MENGE_NULL, _schrift(11, _TEXT), "right"),
            ("Rückstand + {tage} Tage", werte["Bedarf bis Reaktionszeit"], _MENGE, _schrift(11, _TEXT, True), "right"),
            ("Unterwegs", werte["Unterwegs"], _MENGE, _schrift(11, _BLAU, True), "right"),
            ("Ältester Abruf (Liefertermin)", _datum_wert(aeltester), _DATUM,
             _schrift(10, _ROT if pd.notna(aeltester) and aeltester < st else _TEXT,
                      bool(pd.notna(aeltester) and aeltester < st)), "center"),
            ("Notiz Dispo", n.get("dispo") or None, None, _schrift(9, _DISPO_TEXT), "left"),
            ("Notiz Produktion", n.get("produktion") or None, None, _schrift(9, _PROD_TEXT), "left"),
        ]
        for name, wert, fmt, font, ausrichtung in inhalt:
            s = _U_SPALTE[name]
            zelle = _zusammen(ws, i, s, s, wert, bis_zeile=unten)
            zelle.font = font
            notiz = name.startswith("Notiz")
            zelle.alignment = Alignment(horizontal=ausrichtung, vertical="top" if notiz else "center",
                                        wrap_text=notiz, indent=1 if ausrichtung == "left" else 0)
            if fmt:
                zelle.number_format = fmt
            if notiz:
                dispo = name == "Notiz Dispo"
                _stil_bereich(ws, i, s, s, _fuellung(_DISPO_HG if dispo else _PROD_HG),
                              _rahmen(_DISPO_RAND if dispo else _PROD_RAND), bis_zeile=unten)
        # Details als "Knopf"
        knopf = ws.cell(i, U_DETAILS)
        _stil_bereich(ws, i, U_DETAILS, U_DETAILS, _fuellung(_DISPO_HG),
                      Border(left=_WEISS_DICK, right=_WEISS_DICK, top=_WEISS_DICK, bottom=_WEISS_DICK), bis_zeile=unten)
        knopf.font = _schrift(9, _LINK, True)
        # Status (Ja/Nein) als Etikett ueber die drei Zeilen
        status = _zusammen(ws, i, _U_SPALTE["Gedeckt bis {wochen} Wo.?"], _U_SPALTE["Gedeckt bis {wochen} Wo.?"],
                           None, bis_zeile=unten)
        _status_etikett(status, bool(werte["Gedeckt"]))
        _stil_bereich(ws, i, status.column, status.column,
                      _fuellung(STUFEN[5]["fill"] if werte["Gedeckt"] else STUFEN[1]["fill"]),
                      Border(left=_WEISS_DICK, right=_WEISS_DICK, top=_WEISS_DICK, bottom=_WEISS_DICK), bis_zeile=unten)
        # NRI-Liste untereinander
        for j, text in enumerate(_nri_zeilen(unterwegs[unterwegs["Norm-Nr"] == norm])):
            c = ws.cell(i + j, U_NRI, value=text)
            c.font = _schrift(9, _TEXT_HELL if text.startswith("+") else _BLAU)
            c.alignment = Alignment(vertical="center", indent=1)
        # Trennlinie unter dem Artikel, feste Zeilenhoehe
        for zeile in range(i, unten + 1):
            ws.row_dimensions[zeile].height = _U_ZEILENHOEHE
        for s in range(1, letzte_spalte + 1):
            if s not in (U_DETAILS, status.column, U_NOTIZ_DISPO, U_NOTIZ_PROD):
                ws.cell(unten, s).border = _UNTEN
    ws.freeze_panes = f"D{UEBERSICHT_ERSTE_ZEILE}"   # Kopf + Nr./Details/Norm-Nr bleiben stehen
    _druck(ws, UEBERSICHT_KOPFZEILE)
    return zeilen_je_artikel


# --- Details: eine Karte je Artikel ---------------------------------------------

def _abschnitt(ws, zeile: int, links, rechts) -> None:
    """Abschnittszeile ueber Diagramm (B..J) und Seitenleiste (K..O)."""
    for von, bis, wert in ((_D_ERSTE, _D_DIAGRAMM_BIS, links), (_D_PANEL, _D_LETZTE, rechts)):
        if wert is None:
            continue
        zelle = _zusammen(ws, zeile, von, bis, wert)
        zelle.alignment = Alignment(vertical="bottom")
        zelle.font = _schrift(11, _TEXT, True)
        for s in range(von, bis + 1):
            ws.cell(zeile, s).border = Border(bottom=_LINIE_DUENN)
    ws.row_dimensions[zeile].height = 24


def _karten_kacheln(ws, zeile: int, werte: dict, bericht: dict) -> None:
    basis, rt = bericht["basis"], bericht["reaktion_tage"]
    erster = bericht["verlauf"].get(werte["Norm-Nr"], {}).get("erster_fehltag")
    if erster is None:
        erster_wert, erster_fmt, erster_farbe = "keiner / yok", None, _GRUEN
    elif erster == "sofort":
        erster_wert, erster_fmt, erster_farbe = "sofort / hemen", None, _ROT
    else:
        erster_wert, erster_fmt, erster_farbe = _datum_wert(erster), _DATUM, _ROT
    kacheln = [
        ("Bestand (nutzbar)", "Kullanılabilir stok", werte["Bestand"], _MENGE_NULL, "volle KLT je Charge", _TEXT),
        ("Unterwegs (NRI)", "Yolda (NRI)", werte["Unterwegs"], _MENGE_NULL,
         f"{werte['Anzahl NRI']} NRI · ab / ilk {_datum_kurz(werte['Nächste Ankunft'])}" if werte["Unterwegs"] > 0 else "",
         _BLAU if werte["Unterwegs"] > 0 else _TEXT_HELL),
        (f"Rückstand + {rt} Tage", f"Gecikme + {rt} gün", werte["Bedarf bis Reaktionszeit"], _MENGE_NULL,
         "Bedarf / ihtiyaç", _TEXT),
        ("Fehlt gesamt", "Toplam eksik", werte["Fehlt gesamt"], _MENGE_NULL, "aus der Türkei / Türkiye'den",
         _ROT if werte["Fehlt gesamt"] > 0 else _GRUEN),
        ("Ø Bedarf je Woche", "Haftalık ort.", werte["Ø Woche"], _MENGE_NULL,
         f"Basis {basis['von']:%d.%m.}–{basis['bis']:%d.%m.} ({_wochen_text(basis['wochen'])} Wo.)", _TEXT),
        ("Ø Bedarf je Monat", "Aylık ort.", werte["Ø Monat"], _MENGE_NULL, "", _TEXT),
        ("Erster Fehltag", "İlk eksik günü", erster_wert, erster_fmt, "", erster_farbe),
    ]
    for k, (de, tr, wert, fmt, unter, farbe) in enumerate(kacheln):
        von = _D_ERSTE + 2 * k
        for r, text, font in ((zeile, f"{de} / {tr}", _schrift(8, _TEXT_MITTEL)),
                              (zeile + 1, wert, _schrift(15, farbe, True)),
                              (zeile + 2, unter or None, _schrift(8, _TEXT_HELL))):
            zelle = _zusammen(ws, r, von, von + 1, text)
            zelle.font = font
            zelle.alignment = Alignment(horizontal="left", vertical="center", indent=1)
            if r == zeile + 1 and fmt:
                zelle.number_format = fmt
            for s in (von, von + 1):
                ws.cell(r, s).fill = _fuellung(_FLAECHE)
                ws.cell(r, s).border = Border(left=_WEISS_DICK if s == von else None,
                                              right=_WEISS_DICK if s == von + 1 else None)
    ws.row_dimensions[zeile].height = 16
    ws.row_dimensions[zeile + 1].height = 26
    ws.row_dimensions[zeile + 2].height = 15


def abrufe_tabelle(bericht: dict, norm) -> dict:
    """Unterwegs & Abrufe der naechsten ABRUF_TAGE fuer die Detailkarte:
    verfuegbar = nutzbarer Bestand + alles Unterwegs; je Abruf (Ladedatum,
    Abladestelle) kumuliert und "Rest" = verfuegbar - kumuliert. Ab der ersten
    Zeile mit negativem Rest reicht es nicht mehr."""
    st = bericht["stichtag"]
    a = bericht["artikel"].set_index("Norm-Nr").loc[norm]
    u = bericht["unterwegs"]
    u = u[u["Norm-Nr"] == norm].sort_values("Ankunft gerechnet")
    nri = [(str(z.get("Referenz", "") or "NRI ?"), z["Ankunft gerechnet"], float(z["Menge"])) for _, z in u.iterrows()]
    verfuegbar = float(a["Bestand"]) + sum(m for _, _, m in nri)
    z = bericht["zeilen"]
    z = z[(z["Norm-Nr"] == norm) & (z["Ladedatum"] <= st + pd.Timedelta(days=ABRUF_TAGE))]
    ort = (z["Abladestelle"].astype(str) + (" (" + z["Werk"].astype(str) + ")").where(z["Werk"].astype(str) != "", ""))
    abrufe = (z.assign(_ort=ort).groupby(["Ladedatum", "_ort"], sort=True)
              .agg(Menge=("Offen", "sum"), Liefertermin=("Wunschtermin", "min")).reset_index())
    abrufe["Kumuliert"] = abrufe["Menge"].cumsum()
    abrufe["Rest"] = verfuegbar - abrufe["Kumuliert"]
    summe = float(abrufe["Menge"].sum())
    return {"bestand": float(a["Bestand"]), "nri": nri, "verfuegbar": verfuegbar,
            "abrufe": abrufe.rename(columns={"_ort": "Abladestelle"}), "summe": summe,
            "gedeckt": verfuegbar >= summe - 1e-9, "rest": verfuegbar - summe}


def _abrufe_panel(ws, zeile: int, daten: dict, st: pd.Timestamp) -> int:
    """Rechts neben der Prognose: Bestand + NRI (Mengen, Ankunft), darunter die
    Abrufe der naechsten 4 Wochen. Schrift rot ab der Zeile, ab der Bestand +
    Unterwegs nicht mehr reichen; Summenzeile gruen (gedeckt) bzw. rot.
    Rueckgabe: Anzahl belegter Zeilen."""
    k, l, m, n, o = range(_D_PANEL, _D_PANEL + 5)
    r = zeile

    def _kopfzeile(texte):
        nonlocal r
        for s, text, rechts in texte:
            c = ws.cell(r, s, value=text)
            c.font = _schrift(8, _TEXT_MITTEL, True)
            c.alignment = Alignment(horizontal="right" if rechts else "left", vertical="center", indent=0 if rechts else 1)
            c.fill = _fuellung(_KOPF_HG)
            c.border = Border(bottom=_DUENN)
        r += 1

    def _wert(s, wert, fmt=None, font=None, rechts=True):
        c = ws.cell(r, s, value=wert)
        if fmt:
            c.number_format = fmt
        c.font = font or _schrift(9)
        c.alignment = Alignment(horizontal="right" if rechts else "left", vertical="center", indent=0 if rechts else 1)
        return c

    _kopfzeile([(k, "Bestand & Unterwegs / Stok & yolda", False), (l, "", False), (m, "Ankunft / Varış", True),
                (n, "Menge / Miktar", True), (o, "", True)])
    _wert(k, "Bestand (nutzbar) / Stok", rechts=False)
    _wert(n, daten["bestand"], _MENGE_NULL, _schrift(9, _TEXT, True))
    _stil_bereich(ws, r, k, o, rahmen=_UNTEN)
    r += 1
    for nri, ankunft, menge in daten["nri"]:
        _wert(k, nri, font=_schrift(9, _BLAU), rechts=False)
        _wert(m, _datum_wert(ankunft), _DATUM, _schrift(9, _BLAU))
        _wert(n, menge, _MENGE_NULL, _schrift(9, _BLAU, True))
        _stil_bereich(ws, r, k, o, rahmen=_UNTEN)
        r += 1
    _wert(k, "Verfügbar gesamt / Toplam", font=_schrift(9, _TEXT, True), rechts=False)
    _wert(n, daten["verfuegbar"], _MENGE_NULL, _schrift(10, _TEXT, True))
    _stil_bereich(ws, r, k, o, rahmen=Border(top=_DUENN))
    r += 2
    _kopfzeile([(k, "Ladedatum / Yükleme", False), (l, "Abladestelle", False),
                (m, "Liefertermin", True), (n, "Menge / Miktar", True), (o, "Rest / Kalan", True)])
    abrufe = daten["abrufe"]
    if abrufe.empty:
        _wert(k, "keine Abrufe / çağrı yok", font=_schrift(9, _TEXT_HELL), rechts=False)
        r += 1
    rot = False
    for z in abrufe.itertuples(index=False):
        rot = rot or z.Rest < -1e-9
        farbe = _ROT if rot else _TEXT
        _wert(k, "sofort / hemen" if z.Ladedatum <= st else _datum_wert(z.Ladedatum),
              None if z.Ladedatum <= st else _DATUM, _schrift(9, farbe), rechts=False)
        _wert(l, z.Abladestelle, font=_schrift(9, farbe), rechts=False)
        _wert(m, _datum_wert(z.Liefertermin), _DATUM, _schrift(9, farbe))
        _wert(n, z.Menge, _MENGE_NULL, _schrift(9, farbe, True))
        _wert(o, z.Rest, '#,##0;-#,##0;0', _schrift(9, farbe))
        _stil_bereich(ws, r, k, o, rahmen=_UNTEN)
        r += 1
    farbe = _GRUEN if daten["gedeckt"] else _ROT
    status = ("✓ gedeckt / karşılanıyor" if daten["gedeckt"]
              else f"✗ fehlt / eksik {_menge_text(-daten['rest'])}")
    _wert(k, f"Summe {ABRUF_TAGE // 7} Wo. / Toplam", font=_schrift(9, farbe, True), rechts=False)
    _wert(l, status, font=_schrift(9, farbe, True), rechts=False)
    _wert(n, daten["summe"], _MENGE_NULL, _schrift(10, farbe, True))
    _wert(o, daten["rest"], '#,##0;-#,##0;0', _schrift(10, farbe, True))
    _stil_bereich(ws, r, k, o, rahmen=Border(top=Side(style="medium", color=farbe)))
    return r - zeile + 1


def _kunden_tabelle(ws, zeile: int, kunden: pd.DataFrame, bericht: dict, werte: dict) -> int:
    """Bedarf je Kunde (B..I) unter den Diagrammen. Rueckgabe: belegte Zeilen."""
    spalten = [(2, 4, "Kunde / Müşteri", False), (5, 5, "Anteil / Pay", True), (6, 6, "Ø Woche / Hafta", True),
               (7, 7, "Ø Monat / Ay", True), (8, 9, "Bedarf bis Vorschauende", True)]
    for von, bis, text, rechts in spalten:
        zelle = _zusammen(ws, zeile, von, bis, text)
        zelle.font = _schrift(8, _TEXT_MITTEL, True)
        zelle.alignment = Alignment(horizontal="right" if rechts else "left", vertical="center", indent=0 if rechts else 1)
        _stil_bereich(ws, zeile, von, bis, _fuellung(_KOPF_HG), Border(bottom=_DUENN))
    r = zeile + 1
    if kunden is None or kunden.empty:
        ws.cell(r, 2, value="–").font = _schrift(9, _TEXT_HELL)
        return 2
    sichtbar = kunden.head(MAX_KUNDEN_IM_BLOCK)
    rest = kunden.iloc[MAX_KUNDEN_IM_BLOCK:]
    eintraege = [(k["Kunde"], k["Anteil"], k["Ø Woche"], k["Ø Monat"], k["Bedarf"], False) for _, k in sichtbar.iterrows()]
    if not rest.empty:
        eintraege.append((f"weitere {len(rest)} Kunden / diğer", rest["Anteil"].sum(), rest["Ø Woche"].sum(),
                          rest["Ø Monat"].sum(), rest["Bedarf"].sum(), True))
    eintraege.append(("Summe / Toplam", 1.0, werte["Ø Woche"], werte["Ø Monat"], werte["Bedarf Horizont"], None))
    for name, anteil, woche, monat, bedarf, kursiv in eintraege:
        fett = kursiv is None
        zelle = _zusammen(ws, r, 2, 4, name)
        zelle.font = _schrift(9, _TEXT, fett, italic=bool(kursiv))
        zelle.alignment = Alignment(indent=1, vertical="center")
        for s, wert, fmt in ((5, anteil, "0%"), (6, woche, _MENGE_NULL), (7, monat, _MENGE_NULL)):
            c = ws.cell(r, s, value=wert)
            c.number_format = fmt
            c.font = _schrift(9, _TEXT_MITTEL if s == 5 else _TEXT, fett or s != 5, italic=bool(kursiv))
        c = _zusammen(ws, r, 8, 9, bedarf)
        c.number_format = _MENGE_NULL
        c.font = _schrift(9, _TEXT, fett)
        _stil_bereich(ws, r, 2, 9, rahmen=Border(top=_DUENN) if fett else _UNTEN)
        ws.row_dimensions[r].height = 16
        r += 1
    return r - zeile


def _vorschlag_info(v: dict) -> str:
    """Kurzer Text, wofuer ein Vorschlag gedacht ist (Spalte "Vorschlag Dispo")."""
    menge = _menge_text(v["Menge"])
    if v["Sofort"]:
        return f"{menge} sofort / hemen · Bedarf bis {v['Bedarf bis']:%d.%m.}"
    if v["Bedarf bis"] > v["Datum"]:
        return f"{menge} · Bedarf / ihtiyaç {v['Datum']:%d.%m.}–{v['Bedarf bis']:%d.%m.}"
    return f"{menge} · Bedarf / ihtiyaç {v['Datum']:%d.%m.}"


def _vorschlag_panel(ws, zeile: int, vorschlaege: list[dict], daten: tuple | None, st: pd.Timestamp) -> tuple:
    """Gelbe Eingabefelder (Datum + Menge) fuer den vorgeschlagenen
    Wareneingang plus Ergebnis-Formeln. Rueckgabe: (erste, letzte) Eingabezeile."""
    for von, bis, text in ((_EINGABE_DATUM, _EINGABE_DATUM, "Datum / Tarih"), (_EINGABE_MENGE, _EINGABE_MENGE, "Menge / Miktar"),
                           (13, 15, "Vorschlag Dispo / Dispo önerisi")):
        zelle = _zusammen(ws, zeile, von, bis, text)
        zelle.font = _schrift(8, _TEXT_MITTEL, True)
        zelle.alignment = Alignment(horizontal="center" if von < 13 else "left", vertical="center", indent=0 if von < 13 else 1)
        _stil_bereich(ws, zeile, von, bis, _fuellung(_KOPF_HG), Border(bottom=_DUENN))
    erste = zeile + 1
    letzte = zeile + MAX_VORSCHLAEGE
    eingabe_rand = _rahmen(_EINGABE_RAND)
    for k in range(MAX_VORSCHLAEGE):
        r = erste + k
        v = vorschlaege[k] if k < len(vorschlaege) else None
        datum = ws.cell(r, _EINGABE_DATUM, value=_datum_wert(v["Datum"]) if v else None)
        datum.number_format = _DATUM
        menge = ws.cell(r, _EINGABE_MENGE, value=v["Menge"] if v else None)
        menge.number_format = _MENGE_NULL
        for c in (datum, menge):
            c.fill = _fuellung(_EINGABE_HG)
            c.border = eingabe_rand
            c.font = _schrift(10, _TEXT, True)
            c.alignment = Alignment(horizontal="center" if c is datum else "right", vertical="center")
        zelle = _zusammen(ws, r, 13, 15, _vorschlag_info(v) if v else None)
        zelle.font = _schrift(8, _TEXT_MITTEL)
        zelle.alignment = Alignment(indent=1, vertical="center")
    # Ergebnis (rechnet live mit)
    r = letzte + 1
    ergebnisse = [("Summe / Toplam", f"=SUM({get_column_letter(_EINGABE_MENGE)}{erste}:"
                                       f"{get_column_letter(_EINGABE_MENGE)}{letzte})", _MENGE_NULL)]
    if daten:
        kopf, n = daten
        von_d, bis_d = kopf + 1, kopf + n
        s_stand, s_index = get_column_letter(_D_STAND), get_column_letter(_D_INDEX)
        stand = f"{BLATT_DATEN}!${s_stand}${von_d}:${s_stand}${bis_d}"
        index = f"{BLATT_DATEN}!${s_index}${von_d}:${s_index}${bis_d}"
        labels = f"{BLATT_DATEN}!$A${von_d}:$A${bis_d}"
        ergebnisse += [
            ("Tiefster Stand / En düşük", f"=MIN({stand})", _MENGE_VORZEICHEN),
            ("Bestand Ende / Son stok", f"={BLATT_DATEN}!${s_stand}${bis_d}", _MENGE_VORZEICHEN),
            ("1. Fehlwoche / İlk eksik", f'=IF(COUNT({index})=0,"keine / yok",IF(MIN({index})<=1,"sofort / hemen",'
                                         f'INDEX({labels},MIN({index})+1)))', None),
        ]
    for k, (text, formel, fmt) in enumerate(ergebnisse):
        ws.cell(r + k, _EINGABE_DATUM, value=text).font = _schrift(8, _TEXT_MITTEL)
        c = ws.cell(r + k, _EINGABE_MENGE, value=formel)
        c.font = _schrift(10, _TEXT, True)
        c.alignment = Alignment(horizontal="right")
        if fmt:
            c.number_format = fmt
        _stil_bereich(ws, r + k, _EINGABE_DATUM, _EINGABE_MENGE, rahmen=_UNTEN)
    hinweis = _zusammen(
        ws, r + len(ergebnisse), _EINGABE_DATUM, _D_LETZTE,
        "Gelbe Felder ändern (Datum + Stück) → das Diagramm links rechnet sofort neu. Rot trotz Vorschlag = Ware ist "
        "unterwegs, kommt aber zu spät.  /  Sarı alanları değiştirin → grafik anında güncellenir. Öneriye rağmen "
        "kırmızı = mal yolda ama geç geliyor.",
        bis_zeile=r + len(ergebnisse) + 2,
    )
    hinweis.font = _schrift(8, _TEXT_HELL, italic=True)
    hinweis.alignment = Alignment(wrap_text=True, vertical="top")
    return erste, letzte


def _schreibe_details(ws, ws_daten, bericht: dict, uebersicht_zeilen: dict, sprache: str, daten_positionen: dict) -> dict:
    a = bericht["artikel"]
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    _titel(ws, "Details je Artikel", "Parça bazında detay", st, [
        "Je Artikel eine Karte: Kennzahlen · ① Bestandsprognose je Woche, daneben Bestand, NRI und Abrufe der "
        f"nächsten {ABRUF_TAGE // 7} Wochen · ② Vorschlag mit einstellbarem Wareneingang (gelbe Felder) · Bedarf je Kunde.",
        "Her parça için bir kart: göstergeler · ① haftalık stok tahmini, yanında stok, NRI ve sonraki "
        f"{ABRUF_TAGE // 7} haftanın çağrıları · ② ayarlanabilir mal girişi ile öneri (sarı alanlar) · müşteri bazında ihtiyaç.",
    ])
    for i, breite in enumerate(DETAIL_BREITEN, start=1):
        ws.column_dimensions[get_column_letter(i)].width = breite
    ws.column_dimensions[get_column_letter(DETAIL_NORM_SPALTE)].hidden = True
    zeile = ERSTE_ZEILE
    titel_zeilen = {}
    for r in a.itertuples(index=False):
        werte = {c: r[a.columns.get_loc(c)] for c in a.columns}
        norm = werte["Norm-Nr"]
        gedeckt = bool(werte["Gedeckt"])
        titel_zeilen[norm] = zeile
        u_zeile = uebersicht_zeilen.get(norm)
        if zeile > ERSTE_ZEILE:
            ws.row_breaks.append(Break(id=zeile - 1))   # Druck: jede Karte auf einer neuen Seite

        # Titelleiste: Akzentstreifen, Nr. + Norm-Nr gross, VW-Nr + Bezeichnung, Status, Link zurueck
        ws.cell(zeile, 1).fill = _fuellung(STUFEN[5]["balken"] if gedeckt else STUFEN[1]["balken"])
        titel = _zusammen(ws, zeile, _D_ERSTE, 10, _reich(
            (f"{werte['Rang']}.  {norm}", _inline(15, _TEXT, True)),
            (f"     VW {werte['VW-Nr']}" if werte["VW-Nr"] else "", _inline(11, _TEXT_MITTEL, True)),
            (f"     {werte['Kurztext']}" if werte["Kurztext"] else "", _inline(10, _TEXT_HELL)),
        ))
        titel.alignment = Alignment(vertical="center", indent=1)
        etikett = _zusammen(ws, zeile, 11, 13)
        _status_etikett(etikett, gedeckt, 10,
                        f"Gedeckt bis {wo} Wo.: Ja / Evet" if gedeckt else f"Gedeckt bis {wo} Wo.: Nein / Hayır")
        _stil_bereich(ws, zeile, 11, 13, _fuellung(STUFEN[5]["fill"] if gedeckt else STUFEN[1]["fill"]))
        if u_zeile:
            link = _zusammen(ws, zeile, 14, 15, "↑ Übersicht / Özet")
            link.hyperlink = Hyperlink(ref=link.coordinate, location=f"'{BLATT_UEBERSICHT}'!A{u_zeile}")
            link.font = _schrift(9, _LINK, underline="single")
            link.alignment = Alignment(horizontal="right", vertical="center")
        _stil_bereich(ws, zeile, 1, _D_LETZTE, rahmen=Border(top=Side(style="medium", color=_TEXT),
                                                             bottom=_LINIE_DUENN))
        ws.row_dimensions[zeile].height = 30

        # Notizen (Spiegel der Uebersicht; hier Getipptes wird auch uebernommen)
        r_n = zeile + 1
        for label_spalte, von, bis, quelle, hg, rand, farbe, text in (
            (_D_ERSTE, DETAIL_NOTIZ_DISPO, 8, U_NOTIZ_DISPO, _DISPO_HG, _DISPO_RAND, _DISPO_TEXT, "Notiz Dispo\nDispo notu"),
            (9, DETAIL_NOTIZ_PROD, _D_LETZTE, U_NOTIZ_PROD, _PROD_HG, _PROD_RAND, _PROD_TEXT, "Notiz Produktion\nÜretim notu"),
        ):
            label = ws.cell(r_n, label_spalte, value=text)
            label.font = _schrift(8, farbe, True)
            label.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right")
            wert = None
            if u_zeile:
                ref = f"'{BLATT_UEBERSICHT}'!{get_column_letter(quelle)}{u_zeile}"
                wert = f'=IF({ref}="","",{ref})'
            zelle = _zusammen(ws, r_n, von, bis, wert)
            zelle.font = _schrift(9, farbe)
            zelle.alignment = Alignment(wrap_text=True, vertical="top")
            _stil_bereich(ws, r_n, von, bis, _fuellung(hg), _rahmen(rand))
        ws.cell(r_n, DETAIL_NORM_SPALTE, value=norm)
        ws.row_dimensions[r_n].height = 32
        ws.row_dimensions[zeile + 2].height = 8

        # Kennzahlen-Kacheln
        _karten_kacheln(ws, zeile + 3, werte, bericht)
        ws.row_dimensions[zeile + 6].height = 8

        # ① Prognose (je Woche) + rechts Bestand, NRI und Abrufe der naechsten 4 Wochen
        r1 = zeile + 7
        _abschnitt(ws, r1, _reich(("①  Bestandsprognose je Woche", _inline(11, _TEXT, True)),
                                  ("   Stok tahmini · grün = Bestand, rot = Fehlmenge, grau = Bedarf, "
                                   "blau = unterwegs (NRI)", _inline(8, _TEXT_HELL))),
                   f"Unterwegs & Abrufe {ABRUF_TAGE // 7} Wochen  ·  Yolda & çağrılar")
        panel_zeilen = _abrufe_panel(ws, r1 + 1, abrufe_tabelle(bericht, norm), st)
        hoehe = max(DIAGRAMM_ZEILEN, panel_zeilen)
        for z in range(r1 + 1, r1 + 1 + hoehe):
            ws.row_dimensions[z].height = DIAGRAMM_ZEILENHOEHE
        position = daten_positionen["artikel"].get(norm)
        if position:
            kopf, n = position
            diagramm = _prognose_diagramm(ws_daten, kopf, n)
            _anker(diagramm, _D_ERSTE, r1 + 1, _D_DIAGRAMM_BIS, r1 + DIAGRAMM_ZEILEN)
            ws.add_chart(diagramm)

        # ② Vorschlag mit einstellbarem Wareneingang
        r2 = r1 + 1 + hoehe + 1
        _abschnitt(ws, r2, _reich(("②  Vorschlag – mit Wareneingang", _inline(11, _TEXT, True)),
                                  ("   Öneri – mal girişi ile · orange = vorgeschlagener Wareneingang / önerilen "
                                   "mal girişi", _inline(8, _TEXT_HELL))),
                   "Wareneingang planen  ·  Mal girişi planla")
        for z in range(r2 + 1, r2 + 1 + DIAGRAMM_ZEILEN):
            ws.row_dimensions[z].height = DIAGRAMM_ZEILENHOEHE
        eingabe_von, eingabe_bis = _vorschlag_panel(ws, r2 + 1, bericht["vorschlag"].get(norm, []), position, st)
        if position:
            kopf, n = position
            _schreibe_vorschlag_formeln(ws_daten, kopf, n, bericht["verlauf"][norm]["bestand"][0],
                                        eingabe_von, eingabe_bis)
            diagramm = _prognose_diagramm(ws_daten, kopf, n, mit_vorschlag=True)
            _anker(diagramm, _D_ERSTE, r2 + 1, _D_DIAGRAMM_BIS, r2 + DIAGRAMM_ZEILEN)
            ws.add_chart(diagramm)

        # Bedarf je Kunde
        r3 = r2 + 1 + DIAGRAMM_ZEILEN + 1
        _abschnitt(ws, r3, "Bedarf je Kunde  ·  Müşteri bazında ihtiyaç", None)
        belegt = _kunden_tabelle(ws, r3 + 1, bericht["kunden"].get(norm), bericht, werte)
        zeile = r3 + 1 + belegt + 3  # Abstand zur naechsten Karte
    if a.empty:
        ws.cell(ERSTE_ZEILE, 1, value="Nichts zu melden. / Bildirilecek bir şey yok.").font = _schrift(10, _GRUEN, italic=True)
    _druck(ws, None, hochformat=True)   # Hochformat: eine ganze Karte je Seite
    return titel_zeilen


# --- Wochen, Unterwegs, Archiv -------------------------------------------------

def _schreibe_wochen(ws, bericht: dict) -> None:
    a, matrix, wochen_liste = bericht["artikel"], bericht["matrix"], bericht["wochen"]
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    grenze_kurz = st + pd.Timedelta(days=rt)
    _titel(ws, f"Bedarf je Woche (bis {wo} Wochen)", f"Haftalık ihtiyaç ({wo} haftaya kadar)", st, [
        "Je Artikel: Bedarf (offene Menge nach Ladedatum) · Zulauf (unterwegs, nach Ankunft) · Fehlt (weder bei uns "
        f"noch unterwegs). Erste Spalte = Rückstand bis {st:%d.%m.}. Gelb: Reaktionszeit {rt} Tage.",
        "Her parça için: İhtiyaç (yükleme tarihine göre açık miktar) · Gelecek (yolda, varışa göre) · Eksik (ne depomuzda "
        f"ne yolda). İlk sütun = {st:%d.%m.} dahil gecikme. Sarı: {rt} günlük reaksiyon süresi.",
    ])
    kopf = [("Nr.", "No", 5), ("Norm-Nr", "Parça No", 12), ("VW-Nr", "VW No", 14), ("Bezeichnung", "Tanım", 26),
            ("Zeile", "Satır", 17), (f"bis {st:%d.%m.}", f"{st:%d.%m.} dahil", 10)]
    for montag in wochen_liste:
        kw = montag.isocalendar()[1]
        kopf.append((f"KW {kw}", f"{montag:%d.%m.}", 9))
    kopf.append(("Summe", "Toplam", 11))
    _kopf(ws, kopf, rt, wo)
    erste_wochenspalte = 7
    for j, montag in enumerate(wochen_liste):
        if montag <= grenze_kurz:
            ws.cell(KOPFZEILE, erste_wochenspalte + j).fill = _fuellung(STUFEN[3]["fill"])
            ws.cell(KOPFZEILE, erste_wochenspalte + j).font = _schrift(9, STUFEN[3]["font"], True)
    ws.cell(KOPFZEILE, 6).fill = _fuellung(STUFEN[1]["fill"])
    ws.cell(KOPFZEILE, 6).font = _schrift(9, STUFEN[1]["font"], True)
    zeile = ERSTE_ZEILE
    bezeichnungen = [("bedarf", "Bedarf / İhtiyaç"), ("zulauf", "Zulauf / Gelecek"), ("fehlt", "Fehlt / Eksik")]
    letzte_spalte = erste_wochenspalte + len(wochen_liste)
    for r in a.itertuples(index=False):
        werte = {c: r[a.columns.get_loc(c)] for c in a.columns}
        norm = werte["Norm-Nr"]
        daten = matrix.get(norm, {})
        for k, (schluessel, label) in enumerate(bezeichnungen):
            if k == 0:
                for s, wert in enumerate((werte["Rang"], norm, werte["VW-Nr"] or None, werte["Kurztext"] or None), start=1):
                    zelle = ws.cell(zeile, s, value=wert)
                    zelle.alignment = Alignment(vertical="top", wrap_text=s == 4)
                    zelle.font = _schrift(9, _TEXT_HELL if s in (1, 4) else _TEXT, s == 2)
            ws.cell(zeile, 5, value=label).alignment = Alignment(vertical="top")
            ws.cell(zeile, 5).font = _schrift(9, _TEXT_MITTEL)
            reihe = daten.get(schluessel, [])
            for j, wert in enumerate(reihe):
                zelle = ws.cell(zeile, 6 + j, value=wert if wert else None)
                zelle.number_format = _MENGE
                zelle.font = _schrift(9)
                if schluessel == "fehlt" and wert > 0:
                    zelle.fill = _fuellung(STUFEN[1]["fill"])
                    zelle.font = _schrift(9, STUFEN[1]["font"], True)
                elif schluessel == "zulauf" and wert > 0:
                    zelle.font = _schrift(9, _BLAU)
            summe = ws.cell(zeile, letzte_spalte, value=sum(reihe) if reihe else None)
            summe.number_format = _MENGE
            summe.font = _schrift(9, _TEXT, True)
            for s in range(1, letzte_spalte + 1):
                ws.cell(zeile, s).border = Border(bottom=_DICK if k == 2 else _LINIE_DUENN)
            zeile += 1
    ws.freeze_panes = ws.cell(ERSTE_ZEILE, 6)
    _druck(ws)


def _schreibe_unterwegs(ws, bericht: dict, sprache: str) -> None:
    u, a, st = bericht["alle_zugaenge"], bericht["artikel"], bericht["stichtag"]
    stamm = bericht["stammdaten"]
    t = TEXTE[sprache]
    _titel(ws, "Unterwegs zu uns (ZMM1000)", "Bize doğru yolda (ZMM1000)", st, [
        "Alle Zugänge, nach Ankunft sortiert. Ankunft überfällig = geplante Ankunft vor dem Stand, aber noch nicht bei "
        "uns eingebucht. „Nr. im Bericht“ = Artikel steht in der Übersicht (Link).",
        "Tüm sevkiyatlar, varışa göre sıralı. Varış gecikti = planlanan varış tarihi geçti, ama henüz depomuza "
        "girmedi. „Rapordaki No“ = parça özette yer alıyor (bağlantı).",
    ])
    _kopf(ws, UNTERWEGS_SPALTEN)
    rang = dict(zip(a["Norm-Nr"], a["Rang"])) if not a.empty else {}
    sortiert = u.sort_values(["Ankunft gerechnet", "Referenz", "Norm-Nr"], kind="stable") if not u.empty else u
    zeile = ERSTE_ZEILE
    for _, z in sortiert.iterrows():
        geplant = z.get("Geplante Ankunft")
        ueberfaellig = pd.notna(geplant) and pd.Timestamp(geplant) < st
        hinweis = t["ankunft_ueberfaellig"].format(datum=_datum_kurz(geplant)) if ueberfaellig else None
        norm = z["Norm-Nr"]
        vw = stamm.at[norm, "VW-Nr"] if norm in stamm.index else ""
        text = stamm.at[norm, "Kurztext"] if norm in stamm.index else ""
        werte = [str(z.get("Referenz", "") or ""), str(z.get("Transport", "") or ""), str(z.get("Spediteur", "") or ""),
                 _datum_wert(geplant), hinweis, norm, vw or None, text or None, float(z["Menge"]), rang.get(norm)]
        for s_, wert in enumerate(werte, start=1):
            zelle = ws.cell(zeile, s_, value=wert)
            zelle.border = _UNTEN
            zelle.font = _schrift(9, _TEXT_HELL if s_ == 8 else _TEXT, s_ == 1)
            if s_ == 4:
                zelle.number_format = _DATUM
            elif s_ == 9:
                zelle.number_format = _MENGE_NULL
        if hinweis:
            ws.cell(zeile, 5).font = _schrift(9, _ROT)
        if norm in rang:
            zelle = ws.cell(zeile, 10)
            zelle.hyperlink = Hyperlink(ref=zelle.coordinate,
                                        location=f"'{BLATT_UEBERSICHT}'!A{UEBERSICHT_ERSTE_ZEILE + (rang[norm] - 1) * ZEILEN_JE_ARTIKEL}")
            zelle.font = _schrift(9, _LINK, underline="single")
            zelle.alignment = Alignment(horizontal="center")
        zeile += 1
    ws.freeze_panes = ws.cell(ERSTE_ZEILE, 1)
    ws.auto_filter.ref = f"A{KOPFZEILE}:{get_column_letter(len(UNTERWEGS_SPALTEN))}{max(zeile - 1, ERSTE_ZEILE)}"
    _druck(ws)


def _schreibe_archiv(ws, archiv: dict, stand: pd.Timestamp) -> None:
    _titel(ws, "Notizen zu Artikeln, die gerade nicht im Bericht stehen", "Şu anda raporda olmayan parçaların notları", stand, [
        "Werden automatisch wieder in die Übersicht übernommen, sobald der Artikel wieder im Bericht steht.",
        "Parça tekrar raporda yer aldığında notlar otomatik olarak özete geri aktarılır.",
    ])
    _kopf(ws, [("Norm-Nr", "Parça No", 12), ("Notiz Dispo", "Dispo notu", 50), ("Notiz Produktion", "Üretim notu (Türkiye)", 50)])
    for i, (norm, n) in enumerate(sorted(archiv.items(), key=lambda x: str(x[0])), start=ERSTE_ZEILE):
        ws.cell(i, 1, value=norm).font = _schrift(10, _TEXT, True)
        for s, schluessel, fuellung in ((2, "dispo", _DISPO_FUELLUNG), (3, "produktion", _PROD_FUELLUNG)):
            zelle = ws.cell(i, s, value=n.get(schluessel) or None)
            zelle.fill = fuellung
            zelle.font = _schrift(9)
            zelle.alignment = Alignment(wrap_text=True, vertical="top")
            zelle.border = _rahmen(_DISPO_RAND if s == 2 else _PROD_RAND)


def erstelle_bericht_datei(bericht: dict, notizen: dict | None = None, sprache: str = "TR") -> bytes:
    """Excel-Bericht als Bytes. sprache = Sprache der erzeugten Hinweistexte
    ("DE" oder "TR"); Spaltenkoepfe und Stufen stehen immer zweisprachig drin."""
    notizen = notizen or {}
    sprache = "DE" if str(sprache).upper().startswith("DE") else "TR"
    wb = Workbook()
    ws_u = wb.active
    ws_u.title = BLATT_UEBERSICHT
    ws_d = wb.create_sheet(BLATT_DETAILS)
    ws_w = wb.create_sheet(BLATT_WOCHEN)
    ws_n = wb.create_sheet(BLATT_UNTERWEGS)
    ws_daten = wb.create_sheet(BLATT_DATEN)

    daten_positionen = _schreibe_diagrammdaten(ws_daten, bericht, sprache)
    uebersicht_zeilen = _schreibe_uebersicht(ws_u, bericht, notizen)
    titel_zeilen = _schreibe_details(ws_d, ws_daten, bericht, uebersicht_zeilen, sprache, daten_positionen)
    for norm, zeile in uebersicht_zeilen.items():
        ziel = titel_zeilen.get(norm)
        if ziel:
            for spalte in (U_DETAILS, U_NORM):
                zelle = ws_u.cell(zeile, spalte)
                zelle.hyperlink = Hyperlink(ref=zelle.coordinate, location=f"'{BLATT_DETAILS}'!A{ziel}")
    _schreibe_wochen(ws_w, bericht)
    _schreibe_unterwegs(ws_n, bericht, sprache)

    archiv = {n: e for n, e in notizen.items() if n not in uebersicht_zeilen}
    if archiv:
        ws_a = wb.create_sheet(BLATT_ARCHIV)
        _schreibe_archiv(ws_a, archiv, bericht["stichtag"])
        # Diagrammdaten (ausgeblendet) bleiben das letzte Blatt
        wb.move_sheet(ws_daten, offset=1)
    wb.calculation.fullCalcOnLoad = True   # Vorschlags-Formeln beim Oeffnen rechnen

    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def dateiname(stichtag) -> str:
    return f"Produktion_Lieferuebersicht_{pd.Timestamp(stichtag):%Y%m%d}.xlsx"


def kennzahlen(bericht: dict) -> dict:
    a = bericht["artikel"]
    d = bericht["dashboard"]
    return {
        "artikel": len(a),
        "je_stufe": {s: d["je_stufe"][s]["anzahl"] for s in STUFEN},
        "menge_je_stufe": {s: d["je_stufe"][s]["menge"] for s in STUFEN},
        "nri": d["nri"],
        "nri_bericht": d["nri_bericht"],
        "unterwegs_menge": d["unterwegs_menge"],
        "fehlt_gesamt": d["fehlt_gesamt"],
        "letztes_ladedatum": bericht["zeilen"]["Ladedatum"].max() if not bericht["zeilen"].empty else pd.NaT,
    }
