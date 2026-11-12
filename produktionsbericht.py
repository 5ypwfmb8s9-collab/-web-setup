"""Bericht fuer die Produktion (Reiter "Ausgabedatei" im Dashboard Dispo).

Excel-Datei, die die Dispo der Produktion in der Tuerkei schickt. Sie zeigt,
was fehlt, was schon unterwegs ist und was in den naechsten Wochen gebraucht
wird - je Artikel nach Dringlichkeit sortiert. Beide Seiten schreiben ihre
Notizen hinein; beim naechsten Bericht werden sie uebernommen (letzten Bericht
hochladen).

Blaetter:
  Uebersicht  oben ein kleines Dashboard (Kacheln: Artikel je Dringlichkeit,
              Fehlmengen, Unterwegs; Diagramme: Artikel je Stufe, Bedarf /
              Zulauf / Fehlt je Woche), darunter eine Zeile je Artikel,
              dringendste zuerst, mit Notizspalten (Dispo / Produktion).
  Details     je Artikel ein Block: Bestandsprognose als Diagramm (Bestand
              faellt mit dem Bedarf, steigt mit jedem Zugang; unter null =
              Fehlmenge - wie die "verfuegbare Menge" in SAP MD04), Kennzahlen
              (Durchschnittsbedarf je Woche / Monat, auch je Kunde, Reichweite),
              danach Unterwegs (NRI), Rueckstand, naechste Tage (Reaktionszeit
              Tuerkei), spaetere Wochen mit Fehlmenge.
  Wochen      Bedarf / Zulauf / Fehlt je Kalenderwoche bis zum Horizont.
  Unterwegs   alle Zugaenge zu uns (ZMM1000) mit NRI.
  Notizen-Archiv  Notizen von Artikeln, die gerade nicht im Bericht stehen.
  Diagrammdaten   (ausgeblendet) Zahlen hinter den Diagrammen.

Rechnet nur mit den Spalten, die logic.berechne bereits liefert (Offene Menge,
Kum. Bedarf Artikel, Bestand verfuegbar) und den vorbereiteten Zugaengen -
die Dispositionslogik selbst wird nicht veraendert. Je Einteilung wird die
offene Menge in der Reihenfolge des Ladedatums verteilt (wie logic.py):
zuerst Bestand bei uns, dann die Zugaenge in Reihenfolge der Ankunft.
  rechtzeitig  durch Bestand oder einen Zugang, der bis zum Ladedatum da ist
  spaet        durch einen Zugang, der erst nach dem Ladedatum ankommt
  fehlt        weder bei uns noch unterwegs -> muss aus der Tuerkei kommen
(spaet + fehlt = Fehlmenge aus logic.py)

Durchschnittsbedarf: offene Mengen im Bedarfsexport (bis zum Horizont) geteilt
durch die Wochen, die der Export abdeckt (vom aeltesten Ladedatum bis zum
letzten Ladedatum im Export, hoechstens bis zum Horizont). Reicht der Export
nur wenige Tage, ist der Durchschnitt entsprechend grob - die Basis steht im
Bericht dabei.
"""
from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.chart import AreaChart, BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

from dispo_dashboard.loaders import materialnr

BLATT_UEBERSICHT = "Übersicht - Özet"
BLATT_DETAILS = "Details - Detay"
BLATT_WOCHEN = "Wochen - Haftalık"
BLATT_UNTERWEGS = "Unterwegs - Yolda"
BLATT_ARCHIV = "Notizen-Archiv - Not arşivi"
BLATT_DATEN = "Diagrammdaten"

KOPFZEILE = 4            # Details, Wochen, Unterwegs, Archiv
ERSTE_ZEILE = 5
UEBERSICHT_KOPFZEILE = 22   # Uebersicht: darueber das Dashboard
UEBERSICHT_ERSTE_ZEILE = UEBERSICHT_KOPFZEILE + 1
DASHBOARD_ZEILEN = (4, UEBERSICHT_KOPFZEILE - 1)   # gruppiert (einklappbar)

STANDARD_REAKTION_TAGE = 14
STANDARD_WOCHEN = 22
DIAGRAMM_ZEILEN = 15       # Hoehe des Prognose-Diagramms je Artikelblock (Zeilen)
MAX_KUNDEN_IM_BLOCK = 5

# Dringlichkeitsstufen je Artikel (Sortierung: Stufe, dann erster Engpass)
STUFEN = {
    1: {"de": "Rückstand – fehlt", "tr": "Gecikme – eksik", "fill": "FFC7CE", "font": "9C0006", "balken": "C00000"},
    2: {"de": "Rückstand – unterwegs", "tr": "Gecikme – yolda", "fill": "F8CBAD", "font": "833C0B", "balken": "ED7D31"},
    3: {"de": "Engpass ≤ {tage} Tage", "tr": "Darboğaz ≤ {tage} gün", "fill": "FFEB9C", "font": "7F6000", "balken": "FFC000"},
    4: {"de": "Später ≤ {wochen} Wochen", "tr": "İleride ≤ {wochen} hafta", "fill": "DDEBF7", "font": "1F4E78", "balken": "5B9BD5"},
    5: {"de": "Gedeckt", "tr": "Karşılandı", "fill": "C6EFCE", "font": "006100", "balken": "70AD47"},
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
    erster = next((i for i, v in enumerate(verlauf) if v < -1e-9), None)
    if erster is None:
        erster_fehltag = None
    elif erster <= 1:
        erster_fehltag = "sofort"
    else:
        erster_fehltag = tage[erster - 2]
    return {
        "labels": labels,
        "tage": [None, st] + tage,
        "bedarf": bedarf,
        "zulauf": zulauf,
        "bestand": verlauf,
        "bestand_plus": [max(v, 0.0) for v in verlauf],
        "fehl_minus": [min(v, 0.0) for v in verlauf],
        "erster_fehltag": erster_fehltag,
    }


def berechne_bericht(
    positionen: pd.DataFrame,
    zugang: pd.DataFrame | None,
    stichtag,
    reaktion_tage: int = STANDARD_REAKTION_TAGE,
    wochen: int = STANDARD_WOCHEN,
    gedeckte_aufnehmen: bool = False,
) -> dict:
    """Rechnet alles fuer den Bericht. Rueckgabe-dict:
    artikel   DataFrame je Artikel (sortiert, mit Stufe/Rang, Ø-Bedarf, Reichweite)
    zeilen    DataFrame je offener Einteilung im Horizont (mit Deckungsherkunft)
    unterwegs DataFrame der Zugaenge (nur Artikel im Bericht), alle_zugaenge alle
    wochen    Liste der Wochenanfaenge (Montag) der Spalten nach "bis heute"
    matrix    {Norm-Nr: {"bedarf": [...], "zulauf": [...], "fehlt": [...]}}
              Index 0 = bis einschliesslich Stichtag, dann je Woche
    verlauf   {Norm-Nr: Bestandsprognose je Tag} (siehe _bestandsverlauf)
    kunden    {Norm-Nr: DataFrame Kunde / Bedarf / Ø Woche / Ø Monat / Anteil}
    dashboard Kennzahlen fuer das Dashboard (je Stufe, Wochensummen, Unterwegs)
    sowie stichtag, reaktion_tage, wochen_horizont, horizont, basis (Ø-Basis)."""
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
        zeilen_df = pd.DataFrame(columns=["Position", "Norm-Nr", "Bereich", "Ladedatum", "Kunde", "Offen", "Fehlt",
                                          "Spaet", "Rechtzeitig", "Aus Bestand", "Rechtzeitig unterwegs"])

    erste = positionen.drop_duplicates("Norm-Nr").set_index("Norm-Nr")
    stammdaten = pd.DataFrame({
        "VW-Nr": erste["VW-Nr"].fillna("").astype(str) if "VW-Nr" in erste.columns else "",
        "Kurztext": erste["Kurztext"].fillna("").astype(str),
        "Bestand": pd.to_numeric(erste["Bestand verfügbar"], errors="coerce").fillna(0.0),
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

    matrix, verlauf, kunden_je_artikel = {}, {}, {}
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

_DUENN = Side(style="thin", color="BFBFBF")
_DICK = Side(style="medium", color="595959")
_RAHMEN = Border(left=_DUENN, right=_DUENN, top=_DUENN, bottom=_DUENN)
_KOPF_FUELLUNG = PatternFill("solid", fgColor="1F4E78")
_KOPF_SCHRIFT = Font(bold=True, color="FFFFFF", size=10)
_DISPO_FUELLUNG = PatternFill("solid", fgColor="DDEBF7")
_PROD_FUELLUNG = PatternFill("solid", fgColor="FCE4D6")
_PANEL_FUELLUNG = PatternFill("solid", fgColor="F2F2F2")
_GRAU = Font(color="808080", size=10)
_MENGE = '#,##0;-#,##0;""'
_MENGE_NULL = "#,##0"
_DATUM = "DD.MM.YYYY"
_PROZENT = "0%"

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
    ("Ø Bedarf je Woche", "Haftalık ort. ihtiyaç", 12),
    ("Reichweite (Wochen)", "Yeterlilik (hafta)", 11),
    ("Rückstand fehlt", "Gecikme – eksik", 12),
    ("Rückstand kommt später", "Gecikme – geç geliyor", 13),
    ("Fehlt ≤ {tage} Tage", "Eksik ≤ {tage} gün", 12),
    ("Fehlt später (bis {wochen} Wo.)", "Eksik ileride ({wochen} hf.)", 13),
    ("Erster Engpass", "İlk darboğaz", 12),
    ("Notiz Dispo", "Dispo notu", 42),
    ("Notiz Produktion", "Üretim notu (Türkiye)", 42),
]
U_NORM, U_NOTIZ_DISPO, U_NOTIZ_PROD = 3, 16, 17
_U_SPALTE = {name: i for i, (name, _, _) in enumerate(UEBERSICHT_SPALTEN, start=1)}

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
_PANEL_SPALTE = 9   # Kennzahlen-Panel im Artikelblock: Spalten I..K

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


def _kopf(ws, spalten, reaktion_tage: int = STANDARD_REAKTION_TAGE, wochen: int = STANDARD_WOCHEN,
          zeile: int = KOPFZEILE) -> None:
    for i, (de, tr, breite) in enumerate(spalten, start=1):
        text = f"{de.format(tage=reaktion_tage, wochen=wochen)}\n{tr.format(tage=reaktion_tage, wochen=wochen)}".strip()
        zelle = ws.cell(zeile, i, value=text)
        zelle.fill = _KOPF_FUELLUNG
        zelle.font = _KOPF_SCHRIFT
        zelle.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        zelle.border = _RAHMEN
        ws.column_dimensions[get_column_letter(i)].width = breite
    ws.row_dimensions[zeile].height = 48


def _titel(ws, titel_de: str, titel_tr: str, stand: pd.Timestamp, zeilen: list[str]) -> None:
    ws.cell(1, 1, value=f"{titel_de} · {titel_tr} — Stand / Tarih: {stand:%d.%m.%Y}").font = Font(bold=True, size=14, color="1F4E78")
    for i, text in enumerate(zeilen[:2], start=2):
        ws.cell(i, 1, value=text).font = Font(size=9, color="595959")


def _druck(ws, kopfzeile: int = KOPFZEILE) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{kopfzeile}:{kopfzeile}"
    ws.print_options.gridLines = False


def _stufe_stil(zelle, stufe: int) -> None:
    zelle.fill = PatternFill("solid", fgColor=STUFEN[stufe]["fill"])
    zelle.font = Font(bold=True, color=STUFEN[stufe]["font"], size=10)


def _datum_wert(wert):
    return pd.Timestamp(wert).to_pydatetime() if pd.notna(wert) else None


def _achsen_sichtbar(chart) -> None:
    # openpyxl 3.1 laesst Achsen sonst in Excel weg
    chart.x_axis.delete = False
    chart.y_axis.delete = False


# --- Diagrammdaten (ausgeblendetes Blatt) ------------------------------------

def _schreibe_diagrammdaten(ws, bericht: dict, sprache: str = "TR") -> dict:
    """Schreibt die Zahlen hinter allen Diagrammen. Rueckgabe: Zeilen-Positionen
    {"stufen": (kopf, erste, letzte), "wochen": (...), "artikel": {Norm-Nr: (kopf, n)}}."""
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    ws.sheet_state = "hidden"
    ws.cell(1, 1, value="Zahlen hinter den Diagrammen - bitte nicht aendern / Grafiklerin verileri - lütfen değiştirmeyin")
    # Artikel je Stufe
    ws.cell(2, 1, value="Dringlichkeit / Aciliyet")
    ws.cell(2, 2, value="Artikel / Parça")
    ws.cell(2, 3, value="Menge / Miktar")
    for i, stufe in enumerate((1, 2, 3, 4), start=3):
        ws.cell(i, 1, value=_stufe_text(stufe, rt, wo, "de"))
        ws.cell(i, 2, value=bericht["dashboard"]["je_stufe"][stufe]["anzahl"])
        ws.cell(i, 3, value=bericht["dashboard"]["je_stufe"][stufe]["menge"])
    positionen = {"stufen": (2, 3, 6)}
    # Wochen-Summen
    kopf = 8
    ws.cell(kopf, 1, value="Woche / Hafta")
    ws.cell(kopf, 2, value="Bedarf / İhtiyaç")
    ws.cell(kopf, 3, value="Zulauf / Gelecek")
    ws.cell(kopf, 4, value="Fehlt / Eksik")
    labels = [f"≤ {st:%d.%m.}"] + [f"KW {w.isocalendar()[1]}" for w in bericht["wochen"]]
    summen = bericht["dashboard"]["wochen_summen"]
    for i, label in enumerate(labels):
        ws.cell(kopf + 1 + i, 1, value=label)
        for s, k in enumerate(("bedarf", "zulauf", "fehlt"), start=2):
            ws.cell(kopf + 1 + i, s, value=summen[k][i])
    positionen["wochen"] = (kopf, kopf + 1, kopf + len(labels))
    # Bestandsprognose je Artikel
    zeile = kopf + len(labels) + 3
    positionen["artikel"] = {}
    for norm, v in bericht["verlauf"].items():
        ws.cell(zeile, 1, value=f"Artikel {norm}")
        kopf = zeile + 1
        for s, text in enumerate(("Zeitpunkt / Zaman", "Bedarf / İhtiyaç", "Zulauf / Gelecek",
                                  "Bestand / Stok", "Fehlmenge / Eksik"), start=1):
            ws.cell(kopf, s, value=text)
        n = len(v["labels"])
        start_labels = ("Bestand", "Rückst.") if sprache == "DE" else ("Stok", "Gecikme")
        for i in range(n):
            ws.cell(kopf + 1 + i, 1, value=start_labels[i] if i < 2 else v["labels"][i])
            ws.cell(kopf + 1 + i, 2, value=v["bedarf"][i])
            ws.cell(kopf + 1 + i, 3, value=v["zulauf"][i])
            ws.cell(kopf + 1 + i, 4, value=v["bestand_plus"][i])
            ws.cell(kopf + 1 + i, 5, value=v["fehl_minus"][i])
        positionen["artikel"][norm] = (kopf, n)
        zeile = kopf + n + 2
    return positionen


def _bestandsdiagramm(ws_daten, kopf: int, n: int, titel: str):
    """Bestandsprognose: gruene Flaeche = Bestand, rote Flaeche = Fehlmenge
    (unter null), graue Balken = Bedarf, blaue Balken = Zulauf."""
    area = AreaChart()
    area.grouping = "standard"
    area.add_data(Reference(ws_daten, min_col=4, max_col=5, min_row=kopf, max_row=kopf + n), titles_from_data=True)
    area.set_categories(Reference(ws_daten, min_col=1, min_row=kopf + 1, max_row=kopf + n))
    for s, fuellung, rand in zip(area.series, ("C6EFCE", "FFC7CE"), ("548235", "C00000")):
        s.graphicalProperties.solidFill = fuellung
        s.graphicalProperties.line.solidFill = rand
        s.graphicalProperties.line.width = 19050
    bar = BarChart()
    bar.type = "col"
    bar.grouping = "clustered"
    bar.gapWidth = 30
    bar.add_data(Reference(ws_daten, min_col=2, max_col=3, min_row=kopf, max_row=kopf + n), titles_from_data=True)
    bar.series[0].graphicalProperties.solidFill = "7F7F7F"
    bar.series[1].graphicalProperties.solidFill = "2E75B6"
    area += bar   # Kombi-Diagramm: Flaechen + Balken auf denselben Achsen
    area.title = titel
    area.x_axis.tickLblSkip = 7
    area.x_axis.tickMarkSkip = 7
    area.y_axis.number_format = "#,##0"
    area.y_axis.title = "Stück / Adet"
    area.legend.position = "b"
    area.height = 7.9
    area.width = 24.0
    _achsen_sichtbar(area)
    return area


def _stufen_diagramm(ws_daten, position: tuple, titel: str):
    kopf, erste, letzte = position
    bar = BarChart()
    bar.type = "bar"
    bar.add_data(Reference(ws_daten, min_col=2, min_row=kopf, max_row=letzte), titles_from_data=True)
    bar.set_categories(Reference(ws_daten, min_col=1, min_row=erste, max_row=letzte))
    for i, stufe in enumerate((1, 2, 3, 4)):
        punkt = DataPoint(idx=i)
        punkt.graphicalProperties.solidFill = STUFEN[stufe]["balken"]
        bar.series[0].dPt.append(punkt)
    bar.series[0].graphicalProperties.solidFill = "A6A6A6"
    bar.dataLabels = DataLabelList()
    bar.dataLabels.showVal = True
    bar.dataLabels.showCatName = False
    bar.dataLabels.showSerName = False
    bar.dataLabels.showLegendKey = False
    bar.dataLabels.showPercent = False
    bar.legend = None
    bar.title = titel
    bar.x_axis.scaling.orientation = "maxMin"   # Stufe 1 oben
    bar.y_axis.majorGridlines = None
    bar.y_axis.number_format = "0"
    bar.gapWidth = 60
    bar.height = 6.0
    bar.width = 10.5
    _achsen_sichtbar(bar)
    bar.y_axis.delete = True
    return bar


def _wochen_diagramm(ws_daten, position: tuple, titel: str):
    kopf, erste, letzte = position
    bar = BarChart()
    bar.type = "col"
    bar.grouping = "clustered"
    bar.gapWidth = 40
    bar.add_data(Reference(ws_daten, min_col=2, max_col=4, min_row=kopf, max_row=letzte), titles_from_data=True)
    bar.set_categories(Reference(ws_daten, min_col=1, min_row=erste, max_row=letzte))
    for s, farbe in zip(bar.series, ("A6A6A6", "2E75B6", "C00000")):
        s.graphicalProperties.solidFill = farbe
    bar.title = titel
    bar.y_axis.number_format = "#,##0"
    bar.legend.position = "b"
    bar.height = 6.0
    bar.width = 21.0
    _achsen_sichtbar(bar)
    return bar


# --- Uebersicht mit Dashboard ------------------------------------------------

def _kachel(ws, zeile: int, von: int, bis: int, titel: str, wert, untertitel: str, fuellung: str, schrift: str) -> None:
    for r, text, font in (
        (zeile, titel, Font(bold=True, size=9, color=schrift)),
        (zeile + 1, wert, Font(bold=True, size=20, color=schrift)),
        (zeile + 2, untertitel, Font(size=9, color=schrift)),
    ):
        ws.merge_cells(start_row=r, start_column=von, end_row=r, end_column=bis)
        zelle = ws.cell(r, von, value=text)
        zelle.font = font
        zelle.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for s in range(von, bis + 1):
            ws.cell(r, s).fill = PatternFill("solid", fgColor=fuellung)
            ws.cell(r, s).border = Border(
                left=_DUENN if s == von else None, right=_DUENN if s == bis else None,
                top=_DUENN if r == zeile else None, bottom=_DUENN if r == zeile + 2 else None,
            )
    ws.row_dimensions[zeile].height = 26
    ws.row_dimensions[zeile + 1].height = 30
    ws.row_dimensions[zeile + 2].height = 26


def _schreibe_dashboard(ws, ws_daten, bericht: dict, daten_positionen: dict) -> None:
    d, rt, wo, st = bericht["dashboard"], bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    s = d["je_stufe"]
    ankunft = d["naechste_ankunft"]
    kacheln = [
        ("Artikel im Bericht\nRapordaki parça", d["artikel"],
         f"davon Rückstand / gecikme: {s[1]['anzahl'] + s[2]['anzahl']}", "D9E1F2", "1F3864"),
        ("Rückstand – fehlt\nGecikme – eksik", s[1]["anzahl"],
         f"{_menge_text(s[1]['menge'])} Stück / adet", STUFEN[1]["fill"], STUFEN[1]["font"]),
        ("Rückstand – unterwegs\nGecikme – yolda", s[2]["anzahl"],
         f"{_menge_text(s[2]['menge'])} Stück kommen zu spät / geç geliyor", STUFEN[2]["fill"], STUFEN[2]["font"]),
        (f"Engpass ≤ {rt} Tage\nDarboğaz ≤ {rt} gün", s[3]["anzahl"],
         f"{_menge_text(s[3]['menge'])} Stück fehlen / eksik", STUFEN[3]["fill"], STUFEN[3]["font"]),
        (f"Später ≤ {wo} Wochen\nİleride ≤ {wo} hafta", s[4]["anzahl"],
         f"{_menge_text(s[4]['menge'])} Stück fehlen / eksik", STUFEN[4]["fill"], STUFEN[4]["font"]),
        ("Unterwegs für diese Artikel (NRI)\nBu parçalar için yolda (NRI)", d["nri_bericht"],
         f"{_menge_text(d['unterwegs_menge'])} Stück / adet"
         + (f" · ab / ilk {_datum_kurz(ankunft)}" if pd.notna(ankunft) else "")
         + f" · gesamt / toplam {d['nri']} NRI", "DEEBF7", "1F4E78"),
        ("Fehlt gesamt\nToplam eksik", _menge_text(d["fehlt_gesamt"]),
         "muss aus der Türkei kommen / Türkiye'den gelmeli", "F4CCCC", "9C0006"),
    ]
    bereiche = [(1, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15)]
    for (titel, wert, unter, fuellung, schrift), (von, bis) in zip(kacheln, bereiche):
        _kachel(ws, 5, von, bis, titel, wert, unter, fuellung, schrift)
    if d["artikel"]:
        ws.add_chart(_stufen_diagramm(ws_daten, daten_positionen["stufen"],
                                      "Artikel je Dringlichkeit / Aciliyete göre parça"), "A9")
        ws.add_chart(_wochen_diagramm(ws_daten, daten_positionen["wochen"],
                                      "Alle Artikel je Woche / Tüm parçalar haftalık"), "F9")
    else:
        ws.cell(9, 1, value="Nichts zu melden: kein Rückstand und keine Fehlmenge im Vorschauzeitraum. / "
                            "Bildirilecek bir şey yok.").font = Font(italic=True, color="006100")
    for r in range(DASHBOARD_ZEILEN[0], DASHBOARD_ZEILEN[1] + 1):
        ws.row_dimensions[r].outlineLevel = 1
    ws.sheet_properties.outlinePr.summaryBelow = False


def _schreibe_uebersicht(ws, ws_daten, bericht: dict, notizen: dict, daten_positionen: dict) -> dict:
    a = bericht["artikel"]
    rt, wo, basis = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["basis"]
    _titel(ws, "Lieferübersicht für die Produktion", "Üretim için teslimat özeti", bericht["stichtag"], [
        "Reihenfolge: 1 Rückstand fehlt → 2 Rückstand unterwegs → 3 Engpass ≤ "
        f"{rt} Tage → 4 später (bis {wo} Wochen). „Fehlt“ = weder bei uns noch unterwegs – muss aus der Türkei "
        "kommen. Notizen in die blaue (Dispo) bzw. orange (Produktion) Spalte. Klick auf die Norm-Nr → Details mit "
        f"Bestandsprognose. Ø Bedarf aus {basis['von']:%d.%m.}–{basis['bis']:%d.%m.} ({_wochen_text(basis['wochen'])} Wochen).",
        "Sıralama: 1 Gecikme eksik → 2 Gecikme yolda → 3 Darboğaz ≤ "
        f"{rt} gün → 4 ileride ({wo} haftaya kadar). „Eksik“ = ne depomuzda ne yolda – Türkiye'den gelmesi "
        "gerekiyor. Notları mavi (Dispo) veya turuncu (Üretim) sütuna yazın. Parça no'ya tıklayın → stok tahmini. "
        f"Ort. ihtiyaç {basis['von']:%d.%m.}–{basis['bis']:%d.%m.} ({_wochen_text(basis['wochen'])} hafta) bazında.",
    ])
    _kopf(ws, UEBERSICHT_SPALTEN, rt, wo, zeile=UEBERSICHT_KOPFZEILE)
    _schreibe_dashboard(ws, ws_daten, bericht, daten_positionen)
    zeilen_je_artikel = {}
    mengen = ("Bestand bei uns", "Unterwegs", "Ø Bedarf je Woche")
    fehl = ("Rückstand fehlt", "Rückstand kommt später", "Fehlt ≤ {tage} Tage", "Fehlt später (bis {wochen} Wo.)")
    daten = ("Nächste Ankunft", "Erster Engpass")
    umbruch = ("Dringlichkeit", "Bezeichnung", "Notiz Dispo", "Notiz Produktion")
    for i, r in enumerate(a.itertuples(index=False), start=UEBERSICHT_ERSTE_ZEILE):
        werte = {c: r[a.columns.get_loc(c)] for c in a.columns}
        norm = werte["Norm-Nr"]
        zeilen_je_artikel[norm] = i
        n = notizen.get(norm, {})
        reichweite = werte["Reichweite Wochen"]
        inhalt = {
            "Nr.": werte["Rang"],
            "Dringlichkeit": _stufe_zweisprachig(werte["Stufe"], rt, wo),
            "Norm-Nr": norm,
            "VW-Nr": werte["VW-Nr"] or None,
            "Bezeichnung": werte["Kurztext"] or None,
            "Bestand bei uns": werte["Bestand"],
            "Unterwegs": werte["Unterwegs"],
            "Nächste Ankunft": _datum_wert(werte["Nächste Ankunft"]),
            "Ø Bedarf je Woche": werte["Ø Woche"],
            "Reichweite (Wochen)": None if reichweite is None or pd.isna(reichweite) else round(float(reichweite), 1),
            "Rückstand fehlt": werte["Rückstand fehlt"],
            "Rückstand kommt später": werte["Rückstand später"],
            "Fehlt ≤ {tage} Tage": werte["Kurz fehlt"],
            "Fehlt später (bis {wochen} Wo.)": werte["Später fehlt"],
            "Erster Engpass": _datum_wert(werte["Erster Engpass"]),
            "Notiz Dispo": n.get("dispo") or None,
            "Notiz Produktion": n.get("produktion") or None,
        }
        for name, wert in inhalt.items():
            s = _U_SPALTE[name]
            zelle = ws.cell(i, s, value=wert)
            zelle.border = _RAHMEN
            zelle.alignment = Alignment(vertical="top", wrap_text=name in umbruch)
            if name in mengen:
                zelle.number_format = _MENGE_NULL
            elif name in fehl:
                zelle.number_format = _MENGE
                if wert and name in ("Rückstand fehlt", "Fehlt ≤ {tage} Tage"):
                    zelle.font = Font(bold=True, color="9C0006")
            elif name in daten:
                zelle.number_format = _DATUM
            elif name == "Reichweite (Wochen)":
                zelle.number_format = "0.0"
        _stufe_stil(ws.cell(i, _U_SPALTE["Dringlichkeit"]), werte["Stufe"])
        ws.cell(i, U_NOTIZ_DISPO).fill = _DISPO_FUELLUNG
        ws.cell(i, U_NOTIZ_PROD).fill = _PROD_FUELLUNG
    letzte = max(UEBERSICHT_ERSTE_ZEILE, UEBERSICHT_ERSTE_ZEILE + len(a) - 1)
    if len(a):
        for name, farbe in (("Unterwegs", "9DC3E6"), ("Rückstand fehlt", "FF8F8F"), ("Rückstand kommt später", "F4B183"),
                            ("Fehlt ≤ {tage} Tage", "FFD966"), ("Fehlt später (bis {wochen} Wo.)", "9DC3E6")):
            spalte = get_column_letter(_U_SPALTE[name])
            ws.conditional_formatting.add(
                f"{spalte}{UEBERSICHT_ERSTE_ZEILE}:{spalte}{letzte}",
                DataBarRule(start_type="num", start_value=0, end_type="max", color=farbe, showValue=True),
            )
    ws.freeze_panes = "D1"   # nur die Spalten Nr./Dringlichkeit/Norm-Nr fixieren (Dashboard oben bleibt scrollbar)
    ws.auto_filter.ref = f"A{UEBERSICHT_KOPFZEILE}:{get_column_letter(len(UEBERSICHT_SPALTEN))}{letzte}"
    _druck(ws, UEBERSICHT_KOPFZEILE)
    return zeilen_je_artikel


# --- Details je Artikel -------------------------------------------------------

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


def _schreibe_kennzahlen_panel(ws, zeile: int, werte: dict, kunden: pd.DataFrame, bericht: dict) -> None:
    """Kennzahlen + Bedarf je Kunde rechts neben dem Prognose-Diagramm (Spalten I..K)."""
    basis = bericht["basis"]
    v = bericht["verlauf"].get(werte["Norm-Nr"], {})
    erster = v.get("erster_fehltag")
    if erster is None:
        erster_text = "– (gedeckt / karşılandı)"
    elif erster == "sofort":
        erster_text = "sofort / hemen (Rückstand)"
    else:
        erster_text = f"{pd.Timestamp(erster):%d.%m.%Y}"
    reichweite = werte["Reichweite Wochen"]
    reichweite_text = "–" if reichweite is None or pd.isna(reichweite) else f"{_wochen_text(reichweite)} Wochen / hafta"
    p = _PANEL_SPALTE
    ueberschrift = ws.cell(zeile, p, value="Kennzahlen / Göstergeler")
    ueberschrift.font = Font(bold=True, color="FFFFFF", size=10)
    for s in range(p, p + 3):
        ws.cell(zeile, s).fill = _KOPF_FUELLUNG
    zeilen = [
        ("Bestand bei uns / Bizdeki stok", werte["Bestand"], _MENGE_NULL, ""),
        ("Unterwegs / Yolda", werte["Unterwegs"], _MENGE_NULL,
         f"{werte['Anzahl NRI']} NRI, ab / ilk {_datum_kurz(werte['Nächste Ankunft'])}" if werte["Unterwegs"] > 0 else ""),
        ("Fehlt gesamt / Toplam eksik", werte["Fehlt gesamt"], _MENGE_NULL, "aus der Türkei / Türkiye'den"),
        ("Ø Bedarf je Woche / Haftalık ort. ihtiyaç", werte["Ø Woche"], _MENGE_NULL,
         f"Basis {basis['von']:%d.%m.}–{basis['bis']:%d.%m.} ({_wochen_text(basis['wochen'])} Wo.)"),
        ("Ø Bedarf je Monat / Aylık ort. ihtiyaç", werte["Ø Monat"], _MENGE_NULL, ""),
        ("Reichweite Bestand + unterwegs / Yeterlilik", reichweite_text, None, ""),
        ("Erster Fehltag / İlk eksik günü", erster_text, None, ""),
    ]
    for k, (label, wert, fmt, extra) in enumerate(zeilen, start=1):
        r = zeile + k
        ws.cell(r, p, value=label).font = Font(size=9, color="404040")
        zelle = ws.cell(r, p + 1, value=wert)
        zelle.font = Font(bold=True, size=10)
        zelle.alignment = Alignment(horizontal="right")
        if fmt:
            zelle.number_format = fmt
        ws.cell(r, p + 2, value=extra or None).font = Font(size=8, color="7F7F7F")
        for s in range(p, p + 3):
            ws.cell(r, s).fill = _PANEL_FUELLUNG
    if label == "Erster Fehltag / İlk eksik günü" and erster is not None:
        ws.cell(zeile + len(zeilen), p + 1).font = Font(bold=True, size=10, color="9C0006")
    # Bedarf je Kunde
    r = zeile + len(zeilen) + 2
    for s, text in enumerate(("Bedarf je Kunde / Müşteri bazında", "Ø je Woche / Haftalık", "Ø je Monat / Aylık"), start=p):
        zelle = ws.cell(r, s, value=text)
        zelle.font = Font(bold=True, color="FFFFFF", size=9)
        zelle.fill = _KOPF_FUELLUNG
        zelle.alignment = Alignment(horizontal="left" if s == p else "right")
    r += 1
    if kunden is None or kunden.empty:
        ws.cell(r, p, value="–")
        return
    sichtbar = kunden.head(MAX_KUNDEN_IM_BLOCK)
    rest = kunden.iloc[MAX_KUNDEN_IM_BLOCK:]
    for _, k in sichtbar.iterrows():
        ws.cell(r, p, value=f"{k['Kunde']} ({k['Anteil']:.0%})").font = Font(size=9)
        for s, wert in ((p + 1, k["Ø Woche"]), (p + 2, k["Ø Monat"])):
            zelle = ws.cell(r, s, value=wert)
            zelle.number_format = _MENGE_NULL
            zelle.font = Font(size=9)
        for s in range(p, p + 3):
            ws.cell(r, s).fill = _PANEL_FUELLUNG
            ws.cell(r, s).border = Border(bottom=_DUENN)
        r += 1
    if not rest.empty:
        ws.cell(r, p, value=f"weitere {len(rest)} Kunden / diğer ({rest['Anteil'].sum():.0%})").font = Font(size=9, italic=True)
        for s, wert in ((p + 1, rest["Ø Woche"].sum()), (p + 2, rest["Ø Monat"].sum())):
            zelle = ws.cell(r, s, value=wert)
            zelle.number_format = _MENGE_NULL
            zelle.font = Font(size=9, italic=True)
        for s in range(p, p + 3):
            ws.cell(r, s).fill = _PANEL_FUELLUNG


def _schreibe_details(ws, ws_daten, bericht: dict, uebersicht_zeilen: dict, sprache: str, daten_positionen: dict) -> dict:
    a, zeilen, unterwegs = bericht["artikel"], bericht["zeilen"], bericht["unterwegs"]
    rt, wo, st = bericht["reaktion_tage"], bericht["wochen_horizont"], bericht["stichtag"]
    t = TEXTE[sprache]
    _titel(ws, "Details je Artikel", "Parça bazında detay", st, [
        "Je Artikel: Bestandsprognose (grün = Bestand, rot = Fehlmenge, grau = Bedarf, blau = Zulauf/NRI), Kennzahlen, "
        f"dann Unterwegs (NRI) · Rückstand (bis {st:%d.%m.}) · nächste {rt} Tage · spätere Wochen mit Fehlmenge "
        f"(bis {wo} Wochen). Notizen bitte in der Übersicht.",
        "Her parça için: stok tahmini (yeşil = stok, kırmızı = eksik, gri = ihtiyaç, mavi = gelecek/NRI), göstergeler, "
        f"sonra Yolda (NRI) · Gecikme ({st:%d.%m.} dahil) · sonraki {rt} gün · eksik olan sonraki haftalar "
        f"({wo} haftaya kadar). Notları lütfen özet sayfasına yazın.",
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
        ws.row_dimensions[zeile].height = 20
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
        # Prognose-Diagramm (links, Spalten A..H) + Kennzahlen-Panel (rechts, I..K)
        position = daten_positionen["artikel"].get(norm)
        if position:
            kopf, n = position
            ws.add_chart(_bestandsdiagramm(ws_daten, kopf, n, f"Bestandsprognose / Stok tahmini – {norm}"),
                         f"A{zeile}")
        _schreibe_kennzahlen_panel(ws, zeile, werte, bericht["kunden"].get(norm), bericht)
        zeile += DIAGRAMM_ZEILEN + 1

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


# --- Wochen, Unterwegs, Archiv -------------------------------------------------

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
            zelle.hyperlink = Hyperlink(ref=zelle.coordinate,
                                        location=f"'{BLATT_UEBERSICHT}'!A{UEBERSICHT_ERSTE_ZEILE + rang[norm] - 1}")
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
    ws_daten = wb.create_sheet(BLATT_DATEN)

    daten_positionen = _schreibe_diagrammdaten(ws_daten, bericht, sprache)
    uebersicht_zeilen = _schreibe_uebersicht(ws_u, ws_daten, bericht, notizen, daten_positionen)
    titel_zeilen = _schreibe_details(ws_d, ws_daten, bericht, uebersicht_zeilen, sprache, daten_positionen)
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
        ws_a = wb.create_sheet(BLATT_ARCHIV)
        _schreibe_archiv(ws_a, archiv, bericht["stichtag"])
        # Diagrammdaten (ausgeblendet) bleiben das letzte Blatt
        wb.move_sheet(ws_daten, offset=1)

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
