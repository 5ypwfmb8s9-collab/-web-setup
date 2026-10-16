"""
Einlesen der SAP-Rohexporte. Jede Funktion nimmt die Datei so, wie sie aus SAP kommt,
und gibt einen sauberen DataFrame mit deutschen Spaltennamen zurück.
"""
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import config


def materialnr(x):
    """Materialnummern einheitlich machen (Bedarf liefert Zahl, Bestand Text)."""
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.isdigit() else s


def _pruefe(df, spalten, name):
    fehlend = [s for s in spalten if s not in df.columns]
    if fehlend:
        raise ValueError(f"{name}: im Export fehlen Spalten {fehlend}")


def _spalten_variante(df, varianten, name):
    """Welche Spalten-Variante (z. B. tuerkisch vs. englisch) zu den
    tatsaechlichen Datei-Spalten passt - erste passende gewinnt."""
    for spalten in varianten:
        if set(spalten) <= set(df.columns):
            return spalten
    erwartet = " / ".join(str(sorted(v)) for v in varianten)
    raise ValueError(f"{name}: im Export fehlen Spalten (erwarte eine dieser Varianten: {erwartet})")


def stichtag_aus_dateiname(pfad):
    m = re.search(r"(\d{8})_\d{6}", str(pfad))
    return datetime.strptime(m.group(1), "%Y%m%d").date() if m else date.today()


def datum_der_datei(pfad, bezug=None):
    """
    Datenstand einer Datei:
    1. SAP-Name EXPORT_JJJJMMTT_hhmmss
    2. Name beginnt mit TT.MM (z. B. '28.09_Stok_Raporu') – Jahr so gewählt, dass das Datum nicht nach `bezug` liegt
    3. sonst Änderungsdatum der Datei
    """
    name = Path(pfad).name
    m = re.search(r"(\d{8})_\d{6}", name)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    m = re.match(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", name)
    if m:
        bezug = bezug or date.today()
        tag, mon = int(m.group(1)), int(m.group(2))
        jahr = int(m.group(3)) if m.group(3) else bezug.year
        jahr = jahr + 2000 if jahr < 100 else jahr
        d = date(jahr, mon, tag)
        if not m.group(3) and d > bezug:
            d = date(jahr - 1, mon, tag)
        return d
    return datetime.fromtimestamp(Path(pfad).stat().st_mtime).date()


def dateityp(pfad):
    """Erkennt anhand der Spalten, welcher SAP-Export eine Datei ist (bedarf/bestand/zugang/stockreport)."""
    try:
        xl = pd.ExcelFile(pfad)
    except Exception:
        return None
    if config.STOCKREPORT_BLATT in xl.sheet_names:
        kopf = pd.read_excel(xl, sheet_name=config.STOCKREPORT_BLATT, header=config.STOCKREPORT_KOPFZEILE, nrows=0)
        if set(config.STOCKREPORT_SPALTEN) <= set(kopf.columns):
            return "stockreport"
    kopf = pd.read_excel(xl, nrows=0)
    for typ, spalten in [
        ("bedarf", config.BEDARF_SPALTEN), ("bedarf", config.BEDARF_SPALTEN_EN),
        ("bestand", config.BESTAND_SPALTEN), ("bestand", config.BESTAND_SPALTEN_EN),
        ("zugang", config.ZUGANG_SPALTEN), ("zugang", config.ZUGANG_SPALTEN_EN),
    ]:
        if set(spalten) <= set(kopf.columns):
            return typ
    return None


def neueste_dateien(ordner):
    """Sucht im Ordner je Typ die neueste Datei. Rückgabe: {typ: (pfad, datum)}"""
    funde = {}
    for p in sorted(Path(ordner).glob("*.xls*")):
        if p.name.startswith("~$") or p.name.startswith("Dispo_Auswertung"):
            continue
        typ = dateityp(p)
        if not typ:
            continue
        d = datum_der_datei(p)
        schluessel = (d, p.stat().st_mtime)
        if typ not in funde or schluessel > funde[typ][2]:
            funde[typ] = (p, d, schluessel)
    return {t: (p, d) for t, (p, d, _) in funde.items()}


def lade_bedarf(pfad):
    roh = pd.read_excel(pfad)
    spalten = _spalten_variante(roh, [config.BEDARF_SPALTEN, config.BEDARF_SPALTEN_EN], "Bedarf")
    df = roh[list(spalten)].rename(columns=spalten).copy()
    # Englisches SAP-Layout hat kein Gegenstueck fuer Werk/Einteilung (siehe
    # config.BEDARF_SPALTEN_EN) - Werk bleibt leer, Einteilung wird unten
    # als Sortier-Hilfsfeld je Lieferplan nach Ladedatum durchnummeriert.
    einteilung_synthetisch = "Einteilung" not in df.columns
    if "Werk" not in df.columns:
        df["Werk"] = ""
    if einteilung_synthetisch:
        df["Einteilung"] = 0
    df["Norm-Nr"] = df["Norm-Nr"].map(materialnr)
    for c in ["Ladedatum", "Wunschtermin"]:
        df[c] = pd.to_datetime(df[c])
    for c in ["Werk", "Abladestelle", "Kundenmaterial", "Kurztext", "Kunde"]:
        df[c] = df[c].fillna("").astype(str)
    if einteilung_synthetisch:
        df = df.sort_values(["Lieferplan", "Ladedatum"])
        df["Einteilung"] = df.groupby("Lieferplan").cumcount() + 1
    return df.sort_values(["Norm-Nr", "Ladedatum", "Wunschtermin", "Lieferplan", "Einteilung"]).reset_index(drop=True)


def lade_zugang(pfad):
    """Zugänge je Transport / Lieferung / Artikel (Chargen zusammengefasst, Nullzeilen entfernt)."""
    roh = pd.read_excel(pfad)
    spalten = _spalten_variante(roh, [config.ZUGANG_SPALTEN, config.ZUGANG_SPALTEN_EN], "Zugang")
    df = roh[list(spalten)].rename(columns=spalten).copy()
    df["Norm-Nr"] = df["Norm-Nr"].map(materialnr)
    df["Geplante Ankunft"] = pd.to_datetime(df["Geplante Ankunft"])
    for c in ["Referenz", "Spediteur"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    keys = ["Norm-Nr", "Geplante Ankunft", "Transport", "Referenz", "Spediteur", "Lieferung", "Referenzbeleg"]
    df = df.groupby(keys, as_index=False)["Menge"].sum()
    df = df[df["Menge"] > 0]
    return df.sort_values(["Norm-Nr", "Geplante Ankunft", "Transport", "Lieferung"]).reset_index(drop=True)


def _notizdatum(kopf):
    """Liest ein Datum aus einer Notiz-Spaltenüberschrift ('28.09 notlar', '28.03.2023 ...', datetime)."""
    if isinstance(kopf, datetime):
        return kopf.strftime("%d.%m.%Y")
    m = re.search(r"\d{1,2}\.\d{1,2}(?:\.\d{2,4})?", str(kopf))
    return m.group(0) if m else str(kopf).strip()


def lade_stockreport(pfad):
    """Stock Report des Versenders: Stammdaten/Reichweiten + jeweils neueste Notiz je Artikel."""
    roh = pd.read_excel(pfad, sheet_name=config.STOCKREPORT_BLATT, header=config.STOCKREPORT_KOPFZEILE)
    _pruefe(roh, config.STOCKREPORT_SPALTEN, "Stock Report")
    df = roh[list(config.STOCKREPORT_SPALTEN)].rename(columns=config.STOCKREPORT_SPALTEN).copy()
    df["Norm-Nr"] = df["Norm-Nr"].map(materialnr)

    ab = list(roh.columns).index(config.STOCKREPORT_LETZTE_STAMMSPALTE) + 1
    notizspalten = list(roh.columns)[ab:]   # neueste zuerst
    letzte, vom = [], []
    for _, zeile in roh[notizspalten].iterrows():
        text, datum = "", ""
        for k in notizspalten:
            v = zeile[k]
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s in ("", "0", "0.0"):
                continue
            text, datum = s, _notizdatum(k)
            break
        letzte.append(text)
        vom.append(datum)
    df["Letzte Notiz"] = letzte
    df["Notiz vom"] = vom
    for c in ["Kurztext", "Kundenmaterial", "Verantwortlich", "Kundengruppe"]:
        df[c] = df[c].where(df[c].notna() & (df[c].astype(str) != "0"), "").astype(str)
    df = df[df["Norm-Nr"].notna()].drop_duplicates("Norm-Nr")
    return df.sort_values("Reichweite lt. Report").reset_index(drop=True)


def lade_bestand(pfad):
    """Gibt (Positionen je Charge, Summen je Artikel) zurück."""
    roh = pd.read_excel(pfad)
    spalten = _spalten_variante(roh, [config.BESTAND_SPALTEN, config.BESTAND_SPALTEN_EN], "Bestand")
    df = roh[list(spalten)].rename(columns=spalten).copy()
    df = df[df["Norm-Nr"].notna()]               # Summenzeile aus SAP entfernen
    df["Norm-Nr"] = df["Norm-Nr"].map(materialnr)
    df["Bestandsart"] = df["Bestandsart"].fillna("").astype(str).str.strip()

    arten = list(config.BESTAND_VERFUEGBAR) + list(config.BESTAND_INFO)
    piv = (df[df["Bestandsart"].isin(arten)]
           .pivot_table(index="Norm-Nr", columns="Bestandsart", values="Menge", aggfunc="sum", fill_value=0))
    for a in arten:
        if a not in piv.columns:
            piv[a] = 0
    piv = piv[arten].reset_index()
    kurz = df.groupby("Norm-Nr")["Kurztext"].first()
    piv.insert(1, "Kurztext", piv["Norm-Nr"].map(kurz).fillna(""))
    piv["Verfügbar"] = piv[list(config.BESTAND_VERFUEGBAR)].sum(axis=1)
    return df, piv
