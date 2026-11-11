"""Bericht fuer die Produktion (Reiter "Ausgabedatei" im Dashboard Dispo).

Excel-Datei, die die Dispo der Produktion in der Tuerkei schickt. Sie zeigt,
was fehlt, was schon unterwegs ist und was in den naechsten Wochen gebraucht
wird - je Artikel nach Dringlichkeit sortiert. Beide Seiten schreiben ihre
Notizen hinein; beim naechsten Bericht werden sie uebernommen (letzten Bericht
hochladen).

Blaetter:
  Uebersicht  eine Zeile je Artikel, dringendste zuerst, mit Notizspalten
              (Dispo / Produktion) - hier werden die Notizen geschrieben.
  Details     je Artikel ein Block: Unterwegs (NRI), Rueckstand, naechste
              Tage (Reaktionszeit Tuerkei), spaetere Wochen mit Fehlmenge.
  Wochen      Bedarf / Zulauf / Fehlt je Kalenderwoche bis zum Horizont.
  Unterwegs   alle Zugaenge zu uns (ZMM1000) mit NRI.
  Notizen-Archiv  Notizen von Artikeln, die gerade nicht im Bericht stehen.

Rechnet nur mit den Spalten, die logic.berechne bereits liefert (Offene Menge,
Kum. Bedarf Artikel, Bestand verfuegbar) und den vorbereiteten Zugaengen -
die Dispositionslogik selbst wird nicht veraendert. Je Einteilung wird die
offene Menge in der Reihenfolge des Ladedatums verteilt (wie logic.py):
zuerst Bestand bei uns, dann die Zugaenge in Reihenfolge der Ankunft.
  rechtzeitig  durch Bestand oder einen Zugang, der bis zum Ladedatum da ist
  spaet        durch einen Zugang, der erst nach dem Ladedatum ankommt
  fehlt        weder bei uns noch unterwegs -> muss aus der Tuerkei kommen
(spaet + fehlt = Fehlmenge aus logic.py)
"""
from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

from dispo_dashboard.loaders import materialnr

BLATT_UEBERSICHT = "Übersicht - Özet"
BLATT_DETAILS = "Details - Detay"
BLATT_WOCHEN = "Wochen - Haftalık"
BLATT_UNTERWEGS = "Unterwegs - Yolda"
BLATT_ARCHIV = "Notizen-Archiv - Not arşivi"

KOPFZEILE = 4
ERSTE_ZEILE = 5

STANDARD_REAKTION_TAGE = 14
STANDARD_WOCHEN = 22

# Dringlichkeitsstufen je Artikel (Sortierung: Stufe, dann erster Engpass)
STUFEN = {
    1: {"de": "Rückstand – fehlt", "tr": "Gecikme – eksik", "fill": "FFC7CE", "font": "9C0006"},
    2: {"de": "Rückstand – unterwegs", "tr": "Gecikme – yolda", "fill": "F8CBAD", "font": "833C0B"},
    3: {"de": "Engpass ≤ {tage} Tage", "tr": "Darboğaz ≤ {tage} gün", "fill": "FFEB9C", "font": "7F6000"},
    4: {"de": "Später ≤ {wochen} Wochen", "tr": "İleride ≤ {wochen} hafta", "fill": "DDEBF7", "font": "1F4E78"},
    5: {"de": "Gedeckt", "tr": "Karşılandı", "fill": "C6EFCE", "font": "006100"},
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


def berechne_bericht(
    positionen: pd.DataFrame,
    zugang: pd.DataFrame | None,
    stichtag,
    reaktion_tage: int = STANDARD_REAKTION_TAGE,
    wochen: int = STANDARD_WOCHEN,
    gedeckte_aufnehmen: bool = False,
) -> dict:
    """Rechnet alles fuer den Bericht. Rueckgabe-dict:
    artikel   DataFrame je Artikel (sortiert, mit Stufe/Rang)
    zeilen    DataFrame je offener Einteilung im Horizont (mit Deckungsherkunft)
    unterwegs DataFrame der Zugaenge (nur Artikel im Bericht)
    wochen    Liste der Wochenanfaenge (Montag) der Spalten nach "bis heute"
    matrix    {Norm-Nr: {"bedarf": [...], "zulauf": [...], "fehlt": [...]}}
              Index 0 = bis einschliesslich Stichtag, dann je Woche
    sowie stichtag, reaktion_tage, wochen_horizont."""
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

    zeilen = []
    for norm_nr, gruppe in positionen.groupby("Norm-Nr", sort=False):
        bestand = float(pd.to_numeric(gruppe["Bestand verfügbar"], errors="coerce").fillna(0).iloc[0])
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
        zeilen_df = pd.DataFrame(columns=["Norm-Nr", "Bereich", "Ladedatum", "Offen", "Fehlt", "Spaet",
                                          "Rechtzeitig", "Aus Bestand", "Rechtzeitig unterwegs"])

    erste = positionen.drop_duplicates("Norm-Nr").set_index("Norm-Nr")
    stammdaten = pd.DataFrame({
        "VW-Nr": erste["VW-Nr"].fillna("").astype(str) if "VW-Nr" in erste.columns else "",
        "Kurztext": erste["Kurztext"].fillna("").astype(str),
        "Bestand": pd.to_numeric(erste["Bestand verfügbar"], errors="coerce").fillna(0.0),
    }, index=erste.index)

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
        artikel.append({
            "Norm-Nr": norm_nr,
            "VW-Nr": stammdaten.at[norm_nr, "VW-Nr"],
            "Kurztext": stammdaten.at[norm_nr, "Kurztext"],
            "Kunden": ", ".join(kunden),
            "Bestand": float(stammdaten.at[norm_nr, "Bestand"]),
            "Unterwegs": float(zg["Menge"].sum()) if not zg.empty else 0.0,
            "Anzahl NRI": int(zg["Referenz"].replace("", pd.NA).dropna().nunique()) if not zg.empty else 0,
            "Nächste Ankunft": zg["Ankunft gerechnet"].min() if not zg.empty else pd.NaT,
            "Rückstand fehlt": float(rueck["Fehlt"].sum()),
            "Rückstand später": float(rueck["Spaet"].sum()),
            "Kurz fehlt": float(kurz["Fehlt"].sum()),
            "Kurz später": float(kurz["Spaet"].sum()),
            "Später fehlt": float(lang["Fehlt"].sum()),
            "Fehlt gesamt": float(z["Fehlt"].sum()),
            "Erster Engpass": erster,
            "Bedarf Horizont": float(z["Offen"].sum()),
            "Stufe": stufe,
        })
    artikel_df = pd.DataFrame(artikel)
    if artikel_df.empty:
        artikel_df = pd.DataFrame(columns=["Norm-Nr", "Stufe", "Erster Engpass", "Fehlt gesamt", "Rang"])
    else:
        if not gedeckte_aufnehmen:
            artikel_df = artikel_df[artikel_df["Stufe"] <= 4]
        # Innerhalb einer Stufe: erst Artikel, bei denen wirklich etwas fehlt
        # (Produktion muss handeln), dann die, deren Ware schon unterwegs ist;
        # jeweils nach erstem Engpass, dann groesster Menge.
        artikel_df = artikel_df.assign(
            _ohne_fehlt=(artikel_df["Fehlt gesamt"] <= 0).astype(int),
            _menge=artikel_df["Fehlt gesamt"] + artikel_df["Rückstand später"] + artikel_df["Kurz später"],
        ).sort_values(["Stufe", "_ohne_fehlt", "Erster Engpass", "_menge", "Norm-Nr"],
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

    matrix = {}
    for norm_nr in artikel_df["Norm-Nr"]:
        werte = {k: [0.0] * (anzahl + 1) for k in ("bedarf", "zulauf", "fehlt")}
        for _, z in zeilen_df[zeilen_df["Norm-Nr"] == norm_nr].iterrows():
            i = _spalte(z["Ladedatum"])
            if i is not None:
                werte["bedarf"][i] += z["Offen"]
                werte["fehlt"][i] += z["Fehlt"]
        for _, z in unterwegs[unterwegs["Norm-Nr"] == norm_nr].iterrows():
            i = _spalte(z["Ankunft gerechnet"])
            if i is not None:
                werte["zulauf"][i] += float(z["Menge"])
        matrix[norm_nr] = werte

    return {
        "artikel": artikel_df,
        "zeilen": zeilen_df,
        "unterwegs": unterwegs,
        "alle_zugaenge": alle_zugaenge,
        "stammdaten": stammdaten,
        "wochen": wochen_liste,
        "matrix": matrix,
        "stichtag": st,
        "reaktion_tage": int(reaktion_tage),
        "wochen_horizont": int(wochen),
        "horizont": horizont,
    }


# --- Notizen aus einem frueheren Bericht -------------------------------------

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
        spalten = _kopf_spalten(ws, KOPFZEILE)
        s_norm, s_dispo, s_prod = spalten.get("Norm-Nr"), spalten.get("Notiz Dispo"), spalten.get("Notiz Produktion")
        if not (s_norm and (s_dispo or s_prod)):
            continue
        for r in range(ERSTE_ZEILE, ws.max_row + 1):
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

_DUENN = Side(style="thin", color="BFBFBF")
_DICK = Side(style="medium", color="595959")
_RAHMEN = Border(left=_DUENN, right=_DUENN, top=_DUENN, bottom=_DUENN)
_KOPF_FUELLUNG = PatternFill("solid", fgColor="1F4E78")
_KOPF_SCHRIFT = Font(bold=True, color="FFFFFF", size=10)
_DISPO_FUELLUNG = PatternFill("solid", fgColor="DDEBF7")
_PROD_FUELLUNG = PatternFill("solid", fgColor="FCE4D6")
_GRAU = Font(color="808080", size=10)
_MENGE = '#,##0;-#,##0;""'
_MENGE_NULL = "#,##0"
_DATUM = "DD.MM.YYYY"

UEBERSICHT_SPALTEN = [
    # (Kopf DE, Kopf TR, Breite)
    ("Nr.", "No", 5),
    ("Dringlichkeit", "Aciliyet", 22),
    ("Norm-Nr", "Parça No", 12),
    ("VW-Nr", "VW No", 12),
    ("Bezeichnung", "Tanım", 28),
    ("Bestand bei uns", "Bizdeki stok", 12),
    ("Unterwegs", "Yolda", 11),
    ("Nächste Ankunft", "Sonraki varış", 12),
    ("Rückstand fehlt", "Gecikme – eksik", 12),
    ("Rückstand kommt später", "Gecikme – geç geliyor", 13),
    ("Fehlt ≤ {tage} Tage", "Eksik ≤ {tage} gün", 12),
    ("Fehlt später (bis {wochen} Wo.)", "Eksik ileride ({wochen} hf.)", 13),
    ("Erster Engpass", "İlk darboğaz", 12),
    ("Notiz Dispo", "Dispo notu", 42),
    ("Notiz Produktion", "Üretim notu (Türkiye)", 42),
]
U_NORM, U_NOTIZ_DISPO, U_NOTIZ_PROD = 3, 14, 15

DETAIL_SPALTEN = [
    ("Bereich", "Bölüm", 19),
    ("Datum", "Tarih", 11),
    ("Werk · Abladestelle / NRI", "Tesis · Boşaltma yeri / NRI", 24),
    ("Kunde / Spediteur", "Müşteri / Nakliyeci", 26),
    ("Menge", "Miktar", 11),
    ("rechtzeitig gedeckt", "zamanında karşılanan", 14),
    ("kommt später (unterwegs)", "geç geliyor (yolda)", 14),
    ("fehlt", "eksik", 11),
    ("Hinweis", "Açıklama", 46),
    ("Notiz Dispo", "Dispo notu", 30),
    ("Notiz Produktion", "Üretim notu (Türkiye)", 30),
    ("Norm-Nr (intern)", "", 2),
]
DETAIL_NOTIZ_DISPO, DETAIL_NOTIZ_PROD, DETAIL_NORM_SPALTE = 10, 11, 12

UNTERWEGS_SPALTEN = [
    ("NRI", "NRI", 19),
    ("Transport", "Sevkiyat", 11),
    ("Spediteur", "Nakliyeci", 30),
    ("Geplante Ankunft", "Planlanan varış", 13),
    ("Hinweis", "Açıklama", 30),
    ("Norm-Nr", "Parça No", 12),
    ("VW-Nr", "VW No", 12),
    ("Bezeichnung", "Tanım", 28),
    ("Menge", "Miktar", 11),
    ("Nr. im Bericht", "Rapordaki No", 10),
]


def _kopf(ws, spalten, reaktion_tage: int = STANDARD_REAKTION_TAGE, wochen: int = STANDARD_WOCHEN) -> None:
    for i, (de, tr, breite) in enumerate(spalten, start=1):
        text = f"{de.format(tage=reaktion_tage, wochen=wochen)}\n{tr.format(tage=reaktion_tage, wochen=wochen)}".strip()
        zelle = ws.cell(KOPFZEILE, i, value=text)
        zelle.fill = _KOPF_FUELLUNG
        zelle.font = _KOPF_SCHRIFT
        zelle.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        zelle.border = _RAHMEN
        ws.column_dimensions[get_column_letter(i)].width = breite
    ws.row_dimensions[KOPFZEILE].height = 48


def _titel(ws, titel_de: str, titel_tr: str, stand: pd.Timestamp, zeilen: list[str]) -> None:
    ws.cell(1, 1, value=f"{titel_de} · {titel_tr} — Stand / Tarih: {stand:%d.%m.%Y}").font = Font(bold=True, size=14, color="1F4E78")
    for i, text in enumerate(zeilen[:2], start=2):
        ws.cell(i, 1, value=text).font = Font(size=9, color="595959")


def _druck(ws) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{KOPFZEILE}:{KOPFZEILE}"
    ws.print_options.gridLines = False


def _stufe_stil(zelle, stufe: int) -> None:
    zelle.fill = PatternFill("solid", fgColor=STUFEN[stufe]["fill"])
    zelle.font = Font(bold=True, color=STUFEN[stufe]["font"], size=10)


def _datum_wert(wert):
    return pd.Timestamp(wert).to_pydatetime() if pd.notna(wert) else None


def _schreibe_uebersicht(ws, bericht: dict, notizen: dict) -> dict:
    a = bericht["artikel"]
    rt, wo = bericht["reaktion_tage"], bericht["wochen_horizont"]
    _titel(ws, "Lieferübersicht für die Produktion", "Üretim için teslimat özeti", bericht["stichtag"], [
        "Reihenfolge: 1 Rückstand fehlt → 2 Rückstand unterwegs → 3 Engpass ≤ "
        f"{rt} Tage → 4 später (bis {wo} Wochen). „Fehlt“ = weder bei uns noch unterwegs – "
        "muss aus der Türkei kommen. Notizen in die blaue (Dispo) bzw. orange (Produktion) Spalte schreiben.",
        "Sıralama: 1 Gecikme eksik → 2 Gecikme yolda → 3 Darboğaz ≤ "
        f"{rt} gün → 4 ileride ({wo} haftaya kadar). „Eksik“ = ne depomuzda ne yolda – "
        "Türkiye'den gelmesi gerekiyor. Notları mavi (Dispo) veya turuncu (Üretim) sütuna yazın.",
    ])
    _kopf(ws, UEBERSICHT_SPALTEN, rt, wo)
    zeilen_je_artikel = {}
    for i, r in enumerate(a.itertuples(index=False), start=ERSTE_ZEILE):
        norm = r[a.columns.get_loc("Norm-Nr")]
        werte = {c: r[a.columns.get_loc(c)] for c in a.columns}
        zeilen_je_artikel[norm] = i
        n = notizen.get(norm, {})
        inhalt = [
            werte["Rang"],
            _stufe_zweisprachig(werte["Stufe"], rt, wo),
            norm,
            werte["VW-Nr"] or None,
            werte["Kurztext"] or None,
            werte["Bestand"],
            werte["Unterwegs"],
            _datum_wert(werte["Nächste Ankunft"]),
            werte["Rückstand fehlt"],
            werte["Rückstand später"],
            werte["Kurz fehlt"],
            werte["Später fehlt"],
            _datum_wert(werte["Erster Engpass"]),
            n.get("dispo") or None,
            n.get("produktion") or None,
        ]
        for s, wert in enumerate(inhalt, start=1):
            zelle = ws.cell(i, s, value=wert)
            zelle.border = _RAHMEN
            zelle.alignment = Alignment(vertical="top", wrap_text=s in (2, 5, 14, 15))
            if s in (6, 7):
                zelle.number_format = _MENGE_NULL
            elif s in (9, 10, 11, 12):
                zelle.number_format = _MENGE
                if wert and s in (9, 11):
                    zelle.font = Font(bold=True, color="9C0006")
            elif s in (8, 13):
                zelle.number_format = _DATUM
        _stufe_stil(ws.cell(i, 2), werte["Stufe"])
        ws.cell(i, U_NOTIZ_DISPO).fill = _DISPO_FUELLUNG
        ws.cell(i, U_NOTIZ_PROD).fill = _PROD_FUELLUNG
    letzte = max(ERSTE_ZEILE, ERSTE_ZEILE + len(a) - 1)
    ws.freeze_panes = ws.cell(ERSTE_ZEILE, 4)
    ws.auto_filter.ref = f"A{KOPFZEILE}:{get_column_letter(len(UEBERSICHT_SPALTEN))}{letzte}"
    _druck(ws)
    return zeilen_je_artikel


def _hinweis_zeile(z, sprache: str, reaktion_tage: int) -> str:
    t = TEXTE[sprache]
    teile = []
    if z["Aus Bestand"] > 0:
        teile.append(t["bestand"].format(m=_menge_text(z["Aus Bestand"])))
    for referenz, ankunft, menge in z["Quellen rechtzeitig"]:
        teile.append(f"{referenz or 'NRI ?'} ({_datum_kurz(ankunft)}) {_menge_text(menge)}")
    for referenz, ankunft, menge in z["Quellen spaet"]:
        tage = (pd.Timestamp(ankunft) - z["Ladedatum"]).days
        teile.append(f"{referenz or 'NRI ?'} ({_datum_kurz(ankunft)}) {_menge_text(menge)} – "
                     + t["spaet"].format(t=tage))
    if z["Fehlt"] > 0:
        text = t["fehlt"].format(m=_menge_text(z["Fehlt"]))
        if z["Bereich"] == "rueckstand":
            text += " – " + t["ueberfaellig"]
        elif z["Bereich"] == "kurz" and z["Transportart"]:
            art = z["Transportart"] if sprache == "DE" else TRANSPORT_TR.get(z["Transportart"], z["Transportart"])
            text += " – " + t["puenktlich"].format(art=art)
        teile.append(text)
    elif z["Bereich"] == "rueckstand" and z["Spaet"] <= 0:
        teile.append(t["dispo"])
    return " · ".join(teile)


def _schreibe_details(ws, bericht: dict, uebersicht_zeilen: dict, sprache: str) -> dict:
    a, zeilen, unterwegs = bericht["artikel"], bericht["zeilen"], bericht["unterwegs"]
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    t = TEXTE[sprache]
    _titel(ws, "Details je Artikel", "Parça bazında detay", st, [
        f"Bereiche: Unterwegs (NRI) · Rückstand (bis {st:%d.%m.}) · nächste {rt} Tage · spätere Wochen mit "
        f"Fehlmenge (bis {wo} Wochen). Vollständiger Wochenbedarf: Blatt „{BLATT_WOCHEN}“. Notizen bitte in der Übersicht.",
        f"Bölümler: Yolda (NRI) · Gecikme ({st:%d.%m.} dahil) · sonraki {rt} gün · eksik olan sonraki haftalar "
        f"({wo} haftaya kadar). Tüm haftalık ihtiyaç: „{BLATT_WOCHEN}“ sayfası. Notları lütfen özet sayfasına yazın.",
    ])
    _kopf(ws, DETAIL_SPALTEN, rt, wo)
    ws.column_dimensions[get_column_letter(DETAIL_NORM_SPALTE)].hidden = True
    zeile = ERSTE_ZEILE
    titel_zeilen = {}
    bereich_text = {
        "unterwegs": "Unterwegs / Yolda",
        "rueckstand": "Rückstand / Gecikme",
        "kurz": f"≤ {rt} Tage / ≤ {rt} gün",
    }
    for r in a.itertuples(index=False):
        werte = {c: r[a.columns.get_loc(c)] for c in a.columns}
        norm = werte["Norm-Nr"]
        stufe = werte["Stufe"]
        titel_zeilen[norm] = zeile
        # Titelzeile
        ws.cell(zeile, 1, value=f"{werte['Rang']}.")
        titel = " · ".join(str(x) for x in (norm, werte["VW-Nr"], werte["Kurztext"]) if x)
        ws.cell(zeile, 2, value=f"{titel}   —   {_stufe_text(stufe, rt, wo, 'de')} / {_stufe_text(stufe, rt, wo, 'tr')}")
        ws.merge_cells(start_row=zeile, start_column=2, end_row=zeile, end_column=9)
        for s in range(1, 10):
            _stufe_stil(ws.cell(zeile, s), stufe)
            ws.cell(zeile, s).border = Border(top=_DICK)
        ws.cell(zeile, 2).font = Font(bold=True, color=STUFEN[stufe]["font"], size=11)
        u_zeile = uebersicht_zeilen.get(norm)
        if u_zeile:
            ws.cell(zeile, 1).hyperlink = Hyperlink(ref=ws.cell(zeile, 1).coordinate,
                                                    location=f"'{BLATT_UEBERSICHT}'!A{u_zeile}")
            for s, quelle in ((DETAIL_NOTIZ_DISPO, U_NOTIZ_DISPO), (DETAIL_NOTIZ_PROD, U_NOTIZ_PROD)):
                ref = f"'{BLATT_UEBERSICHT}'!{get_column_letter(quelle)}{u_zeile}"
                zelle = ws.cell(zeile, s, value=f'=IF({ref}="","",{ref})')
                zelle.fill = _DISPO_FUELLUNG if s == DETAIL_NOTIZ_DISPO else _PROD_FUELLUNG
                zelle.alignment = Alignment(wrap_text=True, vertical="top")
                zelle.border = Border(top=_DICK)
        ws.cell(zeile, DETAIL_NORM_SPALTE, value=norm)
        zeile += 1
        # Kennzahlen
        ankunft = werte["Nächste Ankunft"]
        kennzahlen = (
            f"Bestand bei uns / Bizdeki stok: {_menge_text(werte['Bestand'])}  ·  "
            f"Unterwegs / Yolda: {_menge_text(werte['Unterwegs'])}"
            + (f" ({werte['Anzahl NRI']} NRI, ab / ilk {_datum_kurz(ankunft)})" if werte["Unterwegs"] > 0 else "")
            + f"  ·  Fehlt gesamt / Toplam eksik: {_menge_text(werte['Fehlt gesamt'])}"
            + (f"  ·  Kunden / Müşteriler: {werte['Kunden']}" if werte["Kunden"] else "")
        )
        ws.cell(zeile, 2, value=kennzahlen).font = Font(italic=True, size=9, color="404040")
        ws.merge_cells(start_row=zeile, start_column=2, end_row=zeile, end_column=9)
        zeile += 1

        def _zeile_schreiben(werte_zeile: list, grau: bool = False, fett_fehlt: bool = False):
            nonlocal zeile
            for s, wert in enumerate(werte_zeile, start=1):
                zelle = ws.cell(zeile, s, value=wert)
                zelle.alignment = Alignment(vertical="top", wrap_text=s == 9)
                zelle.border = Border(bottom=_DUENN)
                if s == 2:
                    zelle.number_format = _DATUM
                elif s in (5, 6, 7, 8):
                    zelle.number_format = _MENGE
                if grau:
                    zelle.font = _GRAU
            if fett_fehlt:
                ws.cell(zeile, 8).font = Font(bold=True, color="9C0006")
            zeile += 1

        # Unterwegs
        for k, (_, u) in enumerate(unterwegs[unterwegs["Norm-Nr"] == norm].iterrows()):
            hinweis = []
            if u.get("Transport"):
                hinweis.append(t["transport"].format(nr=u["Transport"]))
            if pd.notna(u.get("Geplante Ankunft")) and pd.Timestamp(u["Geplante Ankunft"]) < st:
                hinweis.append(t["ankunft_ueberfaellig"].format(datum=_datum_kurz(u["Geplante Ankunft"])))
            _zeile_schreiben([bereich_text["unterwegs"] if k == 0 else None, _datum_wert(u["Ankunft gerechnet"]),
                              str(u.get("Referenz", "") or ""), str(u.get("Spediteur", "") or ""),
                              float(u["Menge"]), None, None, None, " · ".join(hinweis)])
        # Rueckstand und naechste Tage: jede Einteilung
        az = zeilen[zeilen["Norm-Nr"] == norm]
        for bereich in ("rueckstand", "kurz"):
            for k, (_, z) in enumerate(az[az["Bereich"] == bereich].iterrows()):
                ort = " · ".join(x for x in (z["Werk"], z["Abladestelle"]) if x)
                problem = z["Fehlt"] > 0 or z["Spaet"] > 0
                _zeile_schreiben([bereich_text[bereich] if k == 0 else None, _datum_wert(z["Ladedatum"]), ort, z["Kunde"],
                                  z["Offen"], z["Rechtzeitig"], z["Spaet"], z["Fehlt"],
                                  _hinweis_zeile(z, sprache, rt)],
                                 grau=not problem, fett_fehlt=z["Fehlt"] > 0)
        # Spaetere Wochen: nur Wochen mit Fehlmenge, je Woche zusammengefasst
        lang = az[(az["Bereich"] == "lang") & ((az["Fehlt"] > 0) | (az["Spaet"] > 0))]
        if not lang.empty:
            lang = lang.assign(_woche=lang["Ladedatum"].map(_montag))
            for woche, g in lang.groupby("_woche", sort=True):
                kw = woche.isocalendar()[1]
                _zeile_schreiben([f"KW {kw} / {kw}. hafta", woche.to_pydatetime(), "", "",
                                  g["Offen"].sum(), g["Rechtzeitig"].sum(), g["Spaet"].sum(), g["Fehlt"].sum(),
                                  t["einteilungen"].format(n=len(g))],
                                 fett_fehlt=g["Fehlt"].sum() > 0)
        zeile += 1  # Leerzeile zwischen den Bloecken
    ws.freeze_panes = ws.cell(ERSTE_ZEILE, 1)
    _druck(ws)
    return titel_zeilen


def _schreibe_wochen(ws, bericht: dict) -> None:
    a, matrix, wochen_liste = bericht["artikel"], bericht["matrix"], bericht["wochen"]
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    grenze_kurz = st + pd.Timedelta(days=rt)
    _titel(ws, f"Bedarf je Woche (bis {wo} Wochen)", f"Haftalık ihtiyaç ({wo} haftaya kadar)", st, [
        "Je Artikel: Bedarf (offene Menge nach Ladedatum) · Zulauf (unterwegs, nach Ankunft) · Fehlt (weder bei uns "
        f"noch unterwegs). Erste Spalte = Rückstand bis {st:%d.%m.}. Gelb hinterlegt: Reaktionszeit {rt} Tage.",
        "Her parça için: İhtiyaç (yükleme tarihine göre açık miktar) · Gelecek (yolda, varışa göre) · Eksik (ne depomuzda "
        f"ne yolda). İlk sütun = {st:%d.%m.} dahil gecikme. Sarı: {rt} günlük reaksiyon süresi.",
    ])
    kopf = [("Nr.", "No", 5), ("Norm-Nr", "Parça No", 12), ("VW-Nr", "VW No", 12), ("Bezeichnung", "Tanım", 26),
            ("Zeile", "Satır", 17), (f"bis {st:%d.%m.}", f"{st:%d.%m.} dahil", 10)]
    for montag in wochen_liste:
        kw = montag.isocalendar()[1]
        kopf.append((f"KW {kw}", f"{montag:%d.%m.}", 9))
    kopf.append(("Summe", "Toplam", 11))
    _kopf(ws, kopf, rt, wo)
    erste_wochenspalte = 7
    for j, montag in enumerate(wochen_liste):
        if montag <= grenze_kurz:
            ws.cell(KOPFZEILE, erste_wochenspalte + j).fill = PatternFill("solid", fgColor="BF8F00")
    ws.cell(KOPFZEILE, 6).fill = PatternFill("solid", fgColor="9C0006")
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
                    ws.cell(zeile, s, value=wert).alignment = Alignment(vertical="top", wrap_text=s == 4)
                ws.cell(zeile, 2).font = Font(bold=True)
            ws.cell(zeile, 5, value=label).alignment = Alignment(vertical="top")
            ws.cell(zeile, 5).font = Font(size=9, color="404040")
            reihe = daten.get(schluessel, [])
            for j, wert in enumerate(reihe):
                zelle = ws.cell(zeile, 6 + j, value=wert if wert else None)
                zelle.number_format = _MENGE
                if schluessel == "fehlt" and wert > 0:
                    zelle.fill = PatternFill("solid", fgColor="FFC7CE")
                    zelle.font = Font(bold=True, color="9C0006")
                elif schluessel == "zulauf" and wert > 0:
                    zelle.font = Font(color="1F4E78")
            summe = ws.cell(zeile, letzte_spalte, value=sum(reihe) if reihe else None)
            summe.number_format = _MENGE
            summe.font = Font(bold=True)
            for s in range(1, letzte_spalte + 1):
                ws.cell(zeile, s).border = Border(bottom=_DICK if k == 2 else _DUENN, left=_DUENN, right=_DUENN)
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
            zelle.border = _RAHMEN
            if s_ == 4:
                zelle.number_format = _DATUM
            elif s_ == 9:
                zelle.number_format = _MENGE_NULL
        if hinweis:
            ws.cell(zeile, 5).font = Font(color="9C0006")
        if norm in rang:
            zelle = ws.cell(zeile, 10)
            zelle.hyperlink = Hyperlink(ref=zelle.coordinate, location=f"'{BLATT_UEBERSICHT}'!A{ERSTE_ZEILE + rang[norm] - 1}")
            zelle.font = Font(color="0563C1", underline="single")
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
        ws.cell(i, 1, value=norm)
        for s, schluessel, fuellung in ((2, "dispo", _DISPO_FUELLUNG), (3, "produktion", _PROD_FUELLUNG)):
            zelle = ws.cell(i, s, value=n.get(schluessel) or None)
            zelle.fill = fuellung
            zelle.alignment = Alignment(wrap_text=True, vertical="top")


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

    uebersicht_zeilen = _schreibe_uebersicht(ws_u, bericht, notizen)
    titel_zeilen = _schreibe_details(ws_d, bericht, uebersicht_zeilen, sprache)
    for norm, zeile in uebersicht_zeilen.items():
        ziel = titel_zeilen.get(norm)
        if ziel:
            zelle = ws_u.cell(zeile, U_NORM)
            zelle.hyperlink = Hyperlink(ref=zelle.coordinate, location=f"'{BLATT_DETAILS}'!A{ziel}")
            zelle.font = Font(color="0563C1", underline="single")
    _schreibe_wochen(ws_w, bericht)
    _schreibe_unterwegs(ws_n, bericht, sprache)

    archiv = {n: e for n, e in notizen.items() if n not in uebersicht_zeilen}
    if archiv:
        _schreibe_archiv(wb.create_sheet(BLATT_ARCHIV), archiv, bericht["stichtag"])

    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def dateiname(stichtag) -> str:
    return f"Produktion_Lieferuebersicht_{pd.Timestamp(stichtag):%Y%m%d}.xlsx"


def kennzahlen(bericht: dict) -> dict:
    a = bericht["artikel"]
    zaehler = a["Stufe"].value_counts().to_dict() if not a.empty else {}
    return {
        "artikel": len(a),
        "je_stufe": {s: int(zaehler.get(s, 0)) for s in STUFEN},
        "nri": int(bericht["alle_zugaenge"]["Referenz"].replace("", pd.NA).dropna().nunique())
        if not bericht["alle_zugaenge"].empty else 0,
        "letztes_ladedatum": bericht["zeilen"]["Ladedatum"].max() if not bericht["zeilen"].empty else pd.NaT,
    }

