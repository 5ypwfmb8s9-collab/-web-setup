"""Oberflaeche fuer den Reiter "Dashboard Dispo" in DISPO PRO.

Zeigt die von dispo_dashboard (config/loaders/logic - unveraendert genutzt)
berechnete Auswertung an. Die taeglichen SAP-Exporte koennen entweder direkt
hochgeladen werden (funktioniert ueberall, auch auf Streamlit Cloud) oder -
nur in der lokal installierten Version - aus einem Ordner (z. B. Netzlaufwerk)
gelesen werden.

Aufbau: oben eine schlanke Uebersicht (Kennzahlen + ein Hauptdiagramm), die
Detailansichten (Rückstand, Deckung je Artikel, Abbauplan, Ausgabedatei)
stecken als eigene Unter-Reiter dahinter. Der Datei-Upload steht ganz unten.
"""

import io
import json
import re
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dispo_dashboard import config, loaders, logic

import bestand_logik
import produktionsbericht

ORDNER_DATEI = ".dispo_sap_ordner.txt"
KONTAKTE_DATEI = ".dispo_kontakte.json"
REICHWEITE_DATEI = ".dispo_reichweite.json"
ARTIKELLISTE_DATEI = Path(__file__).resolve().parent / "dispo_dashboard" / "artikelliste.xlsx"

QUELLEN = [
    ("bedarf", "Bedarf (Lieferplan-Einteilungen)"),
    ("bestand", "Bestand (EWM)"),
    ("zugang", "Zugänge (ZMM1000)"),
    ("stockreport", "Stock Report Versender (nur Info)"),
]

TRANSPORTARTEN = ["Luftfracht", "Minivan", "Express LKW", "LKW"]

# Volle Spaltenliste fuer die Ausgabedatei (Excel-Export). Sortiert nach
# Dringlichkeit (siehe _dringlichkeit_sortierung) - oben steht, was am
# dringendsten gebraucht wird.
POSITIONEN_SPALTEN_EXPORT = [
    "Werk", "Kunde", "Abladestelle", "Norm-Nr", "VW-Nr", "Ladedatum",
    "Wunschtermin", "Bestellmenge", "Geliefert", "Offene Menge", "Fehlmenge",
    "Gedeckt ab", "Verspätung (Tage)", "Deckender Import", "Versandart",
    "Transportart", "Status", "Dringlichkeit",
]

# Schlanke Spaltenliste fuer die Positionen-Tabelle innerhalb der
# Artikel-Detailansicht (Reiter "Rückstand"): kein Werk/Kunde-Wirrwarr aus
# Bestellmenge/Geliefert/Fehlmenge, nur die offene Menge.
POSITIONEN_SPALTEN_DETAIL = [
    "Werk", "Kunde", "Abladestelle", "Ladedatum", "Offene Menge", "Gedeckt ab",
    "Verspätung (Tage)", "Deckender Import", "Versandart", "Status",
]

RUECKSTAND_ARTIKEL_SPALTEN = [
    "Norm-Nr", "VW-Nr", "Kunden", "Rückstand (Menge)", "Zugänge unterwegs", "Dringlichkeit",
]

ARTIKEL_SPALTEN = [
    "Norm-Nr", "VW-Nr", "Kunden", "Bestand verfügbar", "Offene Menge gesamt",
    "Rückstand (Menge)", "Erste Fehlmenge am", "Zugänge unterwegs",
    "Nächster Zugang", "Reichweite (Tage)", "Dringlichkeit",
]

LANGFRIST_SPALTEN = [
    "Norm-Nr", "VW-Nr", "Bestand verfügbar", "Zugänge unterwegs",
    "Reichweite (Tage)", "Nächster Zugang", "Empfohlene Bestellmenge", "Dringlichkeit",
]

RUECKSTAND_MIT_BESTAND_SPALTEN = [
    "Norm-Nr", "VW-Nr", "Kunde", "Werk", "Abladestelle", "Ladedatum",
    "Offene Menge (gesamt)", "Gedeckt durch Bestand", "Noch offen ohne Bestand", "Status",
]

MENGEN_SPALTEN_EXPORT = ["Bestellmenge", "Geliefert", "Offene Menge", "Fehlmenge"]
TAGE_SPALTEN_EXPORT = ["Verspätung (Tage)"]
DATUM_SPALTEN_EXPORT = ["Ladedatum", "Wunschtermin", "Gedeckt ab"]

MENGEN_SPALTEN_ARTIKEL = [
    "Bestand verfügbar", "Offene Menge gesamt", "Rückstand (Menge)", "Zugänge unterwegs",
]
TAGE_SPALTEN_ARTIKEL = ["Reichweite (Tage)"]
DATUM_SPALTEN_ARTIKEL = ["Erste Fehlmenge am", "Nächster Zugang"]

_STATUS_FARBEN = {
    "Rückstand ungedeckt": "#ef4444",
    "Engpass": "#ef4444",
    "Rückstand, Zugang kommt": "#f59e0b",
    "Zugang zu spät": "#f59e0b",
    "Rückstand gedeckt": "#f59e0b",
    "Gedeckt": "#22c55e",
    "Erledigt": "#22c55e",
}
_VERSANDART_FARBEN = {"Gebietsspediteur": "#22c55e", "Sonderfahrt": "#ef4444"}
_TRANSPORTART_FARBEN = {
    "Luftfracht": "#ef4444",
    "Minivan": "#f59e0b",
    "Express LKW": "#f59e0b",
    "LKW": "#22c55e",
}

# "Ampel" (Rot/Gelb/Grün) aus logic.py ist fuer die Oberflaeche unanschaulich -
# hier auf ein verstaendliches Wort je Dringlichkeitsstufe abgebildet. Die
# Farben bleiben dieselben Signalfarben wie bisher.
_DRINGLICHKEIT_TEXT = {"Rot": "Kritisch", "Gelb": "Bald fällig", "Grün": "Unkritisch"}
_DRINGLICHKEIT_FARBEN = {"Kritisch": "#ef4444", "Bald fällig": "#f59e0b", "Unkritisch": "#22c55e"}

# Dringlichkeit je POSITION (nicht je Artikel) - selbe drei Stufen, aus dem
# Status abgeleitet. Fuer die Ausgabedatei, damit auch ohne Status-Fachwissen
# klar ist, was dringend gebraucht wird.
_DRINGLICHKEIT_NACH_STATUS = {
    "Rückstand ungedeckt": "Kritisch",
    "Engpass": "Kritisch",
    "Rückstand, Zugang kommt": "Bald fällig",
    "Zugang zu spät": "Bald fällig",
    "Rückstand gedeckt": "Bald fällig",
    "Fehlmenge später": "Unkritisch",
    "Gedeckt": "Unkritisch",
    "Erledigt": "Unkritisch",
}

# Sortierreihenfolge fuer die Ausgabedatei: am dringendsten zuerst.
_STATUS_PRIORITAET = {
    "Rückstand ungedeckt": 0,
    "Engpass": 1,
    "Rückstand, Zugang kommt": 2,
    "Zugang zu spät": 3,
    "Rückstand gedeckt": 4,
    "Fehlmenge später": 5,
    "Gedeckt": 6,
    "Erledigt": 7,
}


def _dringlichkeit_position(status: str) -> str:
    return _DRINGLICHKEIT_NACH_STATUS.get(status, "Unkritisch")


# VW-Nr (Volkswagen-Teilenummer, z. B. "N91096801" oder "WHT007527"): zuerst
# in der gepflegten Artikelliste (dispo_dashboard/artikelliste.xlsx, Norm-Nr
# -> VW-Nr) nachschlagen. Steht ein Artikel dort nicht drin, ersatzweise im
# Kurztext (Artikelbezeichnung des Kunden) nach einem eingebetteten "N" +
# 8 Ziffern suchen. Ist beides erfolglos, bleibt das Feld leer - nicht jeder
# Artikel hat eine erfasste VW-Nr.
_VW_NR_MUSTER = re.compile(r"\bN\d{8}\b")


def _lade_artikelliste() -> dict:
    try:
        liste = pd.read_excel(ARTIKELLISTE_DATEI)
    except FileNotFoundError:
        return {}
    liste = liste.drop_duplicates(subset="NormNr", keep="first")
    return dict(zip(liste["NormNr"], liste["VWNR"]))


_ARTIKELLISTE_VW_NR = _lade_artikelliste()


def _vw_nr(norm_nr, kurztext) -> str:
    aus_liste = _ARTIKELLISTE_VW_NR.get(norm_nr)
    if aus_liste:
        return str(aus_liste)
    treffer = _VW_NR_MUSTER.search(str(kurztext))
    return treffer.group(0) if treffer else ""


def _artikel_label(norm_nr, vw_nr) -> str:
    vw_nr = str(vw_nr) if vw_nr and pd.notna(vw_nr) else ""
    return f"{norm_nr} – {vw_nr}" if vw_nr else str(norm_nr)


# Füllmenge (Standard-Gebindemenge je Kundenwerk + Artikel) aus dem zweiten
# Blatt der Artikelliste (Tabelle1: Werk, Abladestelle, ..., Norm Nr., ...,
# Füllmenge). Steht ein (Werk, Norm-Nr) dort nicht drin, wird ersatzweise die
# haeufigste Füllmenge dieses Artikels ueber alle Werke verwendet.

def _lade_fuellmengen() -> tuple[dict, dict]:
    try:
        tabelle = pd.read_excel(ARTIKELLISTE_DATEI, sheet_name="Tabelle1")
    except (FileNotFoundError, ValueError):
        return {}, {}
    tabelle = tabelle.rename(columns={"Norm NR.": "Norm-Nr", "Füllmenge": "Fuellmenge"})
    tabelle = tabelle.dropna(subset=["Norm-Nr", "Fuellmenge"]).copy()
    tabelle["Norm-Nr"] = pd.to_numeric(tabelle["Norm-Nr"], errors="coerce")
    tabelle["Fuellmenge"] = pd.to_numeric(tabelle["Fuellmenge"], errors="coerce")
    tabelle = tabelle.dropna(subset=["Norm-Nr", "Fuellmenge"])
    tabelle["Norm-Nr"] = tabelle["Norm-Nr"].astype(int)
    tabelle["Werk"] = tabelle["Werk"].astype(str).str.strip()

    je_werk = {
        (werk, norm_nr): menge
        for werk, norm_nr, menge in zip(tabelle["Werk"], tabelle["Norm-Nr"], tabelle["Fuellmenge"])
    }
    je_artikel = (
        tabelle.groupby("Norm-Nr")["Fuellmenge"]
        .agg(lambda s: s.mode().iloc[0])
        .to_dict()
    )
    return je_werk, je_artikel


_FUELLMENGE_JE_WERK, _FUELLMENGE_JE_ARTIKEL = _lade_fuellmengen()


def _fuellmenge(werk, norm_nr):
    if (werk, norm_nr) in _FUELLMENGE_JE_WERK:
        return _FUELLMENGE_JE_WERK[(werk, norm_nr)]
    return _FUELLMENGE_JE_ARTIKEL.get(norm_nr)

# --- Uebersetzung fuer die Ausgabedatei --------------------------------------
UEBERSETZUNG_TR = {
    "Werk": "Tesis", "Kunde": "Müşteri", "Abladestelle": "Boşaltma Yeri",
    "Norm-Nr": "Parça No", "VW-Nr": "VW No", "Ladedatum": "Yükleme Tarihi",
    "Wunschtermin": "İstenen Tarih", "Bestellmenge": "Sipariş Miktarı",
    "Geliefert": "Teslim Edilen", "Offene Menge": "Açık Miktar",
    "Fehlmenge": "Eksik Miktar", "Gedeckt ab": "Karşılanma Tarihi",
    "Verspätung (Tage)": "Gecikme (Gün)", "Deckender Import": "Karşılayan İthalat",
    "Versandart": "Sevkiyat Türü", "Transportart": "Taşıma Türü", "Status": "Durum",
    "Dringlichkeit": "Aciliyet",
}
STATUS_TR = {
    "Rückstand ungedeckt": "Karşılanmamış Gecikme",
    "Rückstand, Zugang kommt": "Gecikme, Sevkiyat Geliyor",
    "Rückstand gedeckt": "Gecikme Karşılandı",
    "Engpass": "Darboğaz",
    "Zugang zu spät": "Sevkiyat Geç Kalıyor",
    "Fehlmenge später": "Eksik Miktar İleride",
    "Gedeckt": "Karşılandı",
    "Erledigt": "Tamamlandı",
}
VERSANDART_TR = {"Gebietsspediteur": "Bölge Nakliyecisi", "Sonderfahrt": "Özel Sefer"}
TRANSPORTART_TR = {
    "Luftfracht": "Hava Kargo", "Minivan": "Minivan",
    "Express LKW": "Ekspres Kamyon", "LKW": "Kamyon",
}
DRINGLICHKEIT_TR = {"Kritisch": "Kritik", "Bald fällig": "Yakında Gerekli", "Unkritisch": "Kritik Değil"}


def lade_gespeicherten_ordner() -> str:
    try:
        return Path(ORDNER_DATEI).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def speichere_ordner(pfad: str) -> None:
    Path(ORDNER_DATEI).write_text(pfad, encoding="utf-8")


def lade_kontakte() -> dict:
    try:
        return json.loads(Path(KONTAKTE_DATEI).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def speichere_kontakte(kontakte: dict) -> None:
    Path(KONTAKTE_DATEI).write_text(
        json.dumps(kontakte, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def lade_reichweite_notizen() -> dict:
    try:
        return json.loads(Path(REICHWEITE_DATEI).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def speichere_reichweite_notizen(daten: dict) -> None:
    Path(REICHWEITE_DATEI).write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Zusaetzliche, von logic.py unabhaengige Ableitungen ---------------------
# (logic.py/loaders.py bleiben unveraendert; diese Funktionen werten nur deren
# bereits berechnete Spalten weiter aus.)

def _versandart(zeile) -> str:
    """Gebietsspediteur, wenn der deckende Zugang vor dem Ladetermin da ist,
    sonst Sonderfahrt. Nur relevant, wenn ueberhaupt eine Fehlmenge besteht."""
    if zeile["Fehlmenge"] <= 0 or pd.isna(zeile["Gedeckt ab"]):
        return ""
    if zeile["Gedeckt ab"] <= zeile["Ladedatum"]:
        return "Gebietsspediteur"
    return "Sonderfahrt"


def _transportart(tage_bis_ladedatum) -> str:
    """Abbauplan-Transportart nach Tagen bis Ladedatum (auch negativ = ueberfaellig)."""
    if pd.isna(tage_bis_ladedatum):
        return ""
    if tage_bis_ladedatum <= 2:
        return "Luftfracht"
    if tage_bis_ladedatum <= 5:
        return "Minivan"
    if tage_bis_ladedatum <= 8:
        return "Express LKW"
    return "LKW"


def _deckende_importe(positionen: pd.DataFrame, zugang_vorbereitet: pd.DataFrame) -> pd.Series:
    """Referenznummer(n) der Zugaenge, die am 'Gedeckt ab'-Datum fuer den Artikel ankommen."""
    if zugang_vorbereitet.empty:
        return pd.Series([""] * len(positionen), index=positionen.index)
    referenzen = (
        zugang_vorbereitet.groupby(["Norm-Nr", "Ankunft gerechnet"])["Referenz"]
        .apply(lambda s: ", ".join(sorted({r for r in s if r})))
    )

    def _lookup(zeile):
        if pd.isna(zeile["Gedeckt ab"]):
            return ""
        return referenzen.get((zeile["Norm-Nr"], zeile["Gedeckt ab"]), "")

    return positionen.apply(_lookup, axis=1)


# --- Scheindeckung: Bestand da, aber wegen Chargen-Splitting nicht nutzbar --
# Eine Position gilt laut Dispositionslogik als gedeckt, sobald die SUMME des
# verfuegbaren Bestands (ueber alle Chargen) ausreicht. Praktisch kann eine
# einzelne Lieferung/ein Füllmenge-Gebinde aber nur aus EINER Chargennummer
# kommen - reicht keine einzelne Charge allein fuer die offene Menge, ist der
# Bestand trotz ausreichender Summe nicht wirklich nutzbar ("Bestand da, aber
# nicht offen [als Problem erkannt]"). Nur fuer das Nahfenster ab Stichtag
# geprueft (SCHEINDECKUNG_FENSTER_TAGE), sonst waere die Liste unueberschaubar
# lang und wenig handlungsrelevant.
SCHEINDECKUNG_FENSTER_TAGE = 7

SCHEINDECKUNG_SPALTEN = [
    "Werk", "Kunde", "Norm-Nr", "VW-Nr", "Ladedatum", "Offene Menge",
    "Bestand (Summe)", "Bestand (größte Charge)", "Anzahl Chargen", "Füllmenge",
]


def _scheindeckung(positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame, stichtag) -> pd.DataFrame:
    verwendbar = bestand_je_charge[bestand_je_charge["Bestandsart"].isin(list(config.BESTAND_VERFUEGBAR))]
    je_charge = verwendbar.groupby(["Norm-Nr", "Charge"])["Menge"].sum()
    kennzahlen = je_charge.groupby("Norm-Nr").agg(
        bestand_summe="sum", bestand_max_charge="max", anzahl_chargen="count",
    )

    st_stichtag = pd.Timestamp(stichtag)
    fenster_ende = st_stichtag + pd.Timedelta(days=SCHEINDECKUNG_FENSTER_TAGE)
    nahfenster = positionen[
        (positionen["Ladedatum"] >= st_stichtag) & (positionen["Ladedatum"] <= fenster_ende)
        & (positionen["Fehlmenge"] <= 0) & (positionen["Offene Menge"] > 0)
    ].copy()
    if nahfenster.empty:
        return nahfenster

    nahfenster = nahfenster.join(kennzahlen, on="Norm-Nr")
    nahfenster = nahfenster[
        nahfenster["bestand_max_charge"].notna()
        & (nahfenster["bestand_max_charge"] < nahfenster["Offene Menge"])
    ].copy()
    if nahfenster.empty:
        return nahfenster

    nahfenster["Füllmenge"] = nahfenster.apply(
        lambda r: _fuellmenge(r["Werk"], r["Norm-Nr"]), axis=1
    )
    nahfenster = nahfenster.rename(columns={
        "bestand_summe": "Bestand (Summe)",
        "bestand_max_charge": "Bestand (größte Charge)",
        "anzahl_chargen": "Anzahl Chargen",
    })
    return nahfenster[SCHEINDECKUNG_SPALTEN].sort_values("Ladedatum").reset_index(drop=True)


def _lade_und_berechne(ordner: str) -> dict:
    dateien = loaders.neueste_dateien(ordner)
    fehlend = [t for t in ["bedarf", "bestand", "zugang"] if t not in dateien]
    if fehlend:
        raise ValueError(f"Es fehlen Dateien fuer: {', '.join(fehlend)}")

    stichtag = loaders.datum_der_datei(dateien["bedarf"][0])
    bedarf = loaders.lade_bedarf(dateien["bedarf"][0])
    bestand_je_charge, bestand_artikel = loaders.lade_bestand(dateien["bestand"][0])
    zugang = loaders.lade_zugang(dateien["zugang"][0])
    positionen, artikel, zugang_vorbereitet = logic.berechne(bedarf, bestand_artikel, zugang, stichtag)

    positionen = positionen.copy()
    positionen["Deckender Import"] = _deckende_importe(positionen, zugang_vorbereitet)
    positionen["Versandart"] = positionen.apply(_versandart, axis=1)
    positionen["Transportart"] = positionen["Tage bis Ladedatum"].apply(_transportart)
    positionen["Dringlichkeit"] = positionen["Status"].apply(_dringlichkeit_position)
    positionen["VW-Nr"] = positionen.apply(lambda r: _vw_nr(r["Norm-Nr"], r["Kurztext"]), axis=1)

    artikel = artikel.copy()
    artikel["Dringlichkeit"] = artikel["Ampel"].map(_DRINGLICHKEIT_TEXT)
    artikel["VW-Nr"] = artikel.apply(lambda r: _vw_nr(r["Norm-Nr"], r["Kurztext"]), axis=1)

    datenstand = [
        (label, loaders.datum_der_datei(dateien[t][0], stichtag), Path(dateien[t][0]).name)
        for t, label in QUELLEN if t in dateien
    ]
    return {
        "stichtag": stichtag,
        "positionen": positionen,
        "artikel": artikel,
        "zugang": zugang_vorbereitet,
        "bestand_je_charge": bestand_je_charge,
        "datenstand": datenstand,
        "scheindeckung": _scheindeckung(positionen, bestand_je_charge, stichtag),
    }


def _filter_auswahl(df: pd.DataFrame, spalte: str, label: str, bereich: str) -> pd.DataFrame:
    optionen = sorted({str(x) for x in df[spalte].dropna() if str(x) != ""})
    auswahl = st.multiselect(label, optionen, key=f"dispo_filter_{bereich}_{spalte}")
    if not auswahl:
        return df
    return df[df[spalte].astype(str).isin(auswahl)]


def _faerbe(farben: dict):
    def _stil(wert):
        farbe = farben.get(wert)
        return f"background-color: {farbe}; color: #0a0a0f; font-weight: 600;" if farbe else ""
    return _stil


def _faerbe_positiv(farbe: str):
    def _stil(wert):
        return f"background-color: {farbe}33;" if wert and wert > 0 else ""
    return _stil


# --- Tabellenhoehe ohne internes Scrollen + separate Suche -------------------
# Streamlit zeigt Tabellen sonst in einer festen, kleinen Box mit eigenem
# Scrollbalken. Hoehe = Kopfzeile + Zeilen in Streamlits eigener Zeilenhoehe
# (empirisch ermittelt: 35px/Zeile + 40px Kopf), damit immer ALLE Zeilen ohne
# Scrollen sichtbar sind - bei vielen Artikeln hilft dafuer die Suche darueber.

def _tabellenhoehe(anzahl_zeilen: int) -> int:
    return 35 * max(anzahl_zeilen, 1) + 40


# Ohne feste Breite quetscht Streamlit die VW-Nr (9 Zeichen, z. B. "N91291201")
# in zu wenige Pixel zusammen, abgeschnitten ohne "...". Deshalb feste Breite.
_VW_NR_SPALTENKONFIG = {"VW-Nr": st.column_config.TextColumn(width=110)}


def _suche(df: pd.DataFrame, spalten: list, key: str) -> pd.DataFrame:
    begriff = st.text_input(
        "🔍 Suche", key=key,
        placeholder="Suchen nach " + " / ".join(spalten),
    )
    if not begriff:
        return df
    treffer = pd.Series(False, index=df.index)
    for spalte in spalten:
        if spalte in df.columns:
            treffer = treffer | df[spalte].astype(str).str.contains(begriff, case=False, na=False, regex=False)
    return df[treffer]


# --- Zahlen-/Datumsformat: Tausenderpunkt, keine Nachkommastellen -----------

def _fmt_menge(wert) -> str:
    if pd.isna(wert):
        return "–"
    return f"{wert:,.0f}".replace(",", ".")


def _fmt_tage(wert) -> str:
    if pd.isna(wert):
        return "–"
    return f"{wert:.0f}"


def _fmt_datum(wert) -> str:
    if pd.isna(wert):
        return "–"
    return pd.Timestamp(wert).strftime("%d.%m.%Y")


def _zeige_tabelle(
    df: pd.DataFrame,
    spalten: list,
    *,
    menge_spalten: tuple = (),
    tage_spalten: tuple = (),
    datum_spalten: tuple = (),
    farben: dict | None = None,
) -> None:
    # Werte VOR der Anzeige in fertige Text-Strings umwandeln (statt
    # Styler.format): st.dataframe zeigt leere/NaN-Zellen sonst immer als
    # woertliches "None" an, unabhaengig von Styler- oder column_config-
    # Formatierung - das ist ein Streamlit-eigenes Verhalten.
    anzeige = df[spalten].copy()
    for s in menge_spalten:
        anzeige[s] = anzeige[s].apply(_fmt_menge)
    for s in tage_spalten:
        anzeige[s] = anzeige[s].apply(_fmt_tage)
    for s in datum_spalten:
        anzeige[s] = anzeige[s].apply(_fmt_datum)
    styler = anzeige.style
    for spalte, farbkarte in (farben or {}).items():
        styler = styler.map(_faerbe(farbkarte), subset=[spalte])
    st.dataframe(
        styler, hide_index=True, use_container_width=True,
        height=_tabellenhoehe(len(anzeige)),
    )


# --- Legende + Uebersicht/Eskalation -----------------------------------------

def _render_legende() -> None:
    with st.expander("Legende"):
        st.markdown(
            "- **Dringlichkeit je Artikel:** 🔴 Kritisch = erste Fehlmenge "
            "≤14 Tage (oder ueberfaellig) · 🟡 Bald fällig ≤30 Tage · "
            "🟢 Unkritisch sonst\n"
            "- **Status:** 🔴 Rückstand ungedeckt/Engpass · 🟡 Rückstand mit "
            "Zugang/Zugang zu spät/Rückstand gedeckt · 🟢 Gedeckt/Erledigt\n"
            "- **Versandart:** Gebietsspediteur = Ware kommt rechtzeitig vor "
            "dem Ladetermin an · Sonderfahrt = Ware kommt erst danach an\n"
            "- **Abbauplan-Transportart** (nach Tagen bis Ladedatum, nur fuer "
            "aktuellen Rückstand/Engpass): 🔴 Luftfracht ≤2 Tage · 🟡 Minivan "
            "3–5 Tage · 🟡 Express LKW 6–8 Tage · 🟢 LKW ab 9 Tage\n"
            "- **Langfristplanung:** Artikel ohne Rückstand, deren Deckung "
            "aber absehbar ausgeht - zeigt, wann und wie viel nachbestellt "
            "werden sollte\n"
            "- **Eskalation** (Deckungsgrad Rückstand durch Transporte): "
            "🟢 ≥80 % · 🟡 50–79 % · 🔴 <50 %"
        )


def _render_scheindeckung_warnung(scheindeckung: pd.DataFrame) -> None:
    if scheindeckung.empty:
        return
    anzahl = len(scheindeckung)
    mehrzahl = "en" if anzahl != 1 else ""
    with st.expander(
        f"⚠️ Bestand vorhanden, aber nicht wirklich nutzbar ({anzahl} Position{mehrzahl})",
        expanded=False,
    ):
        st.caption(
            f"Geprueft nur fuer die naechsten {SCHEINDECKUNG_FENSTER_TAGE} Tage ab "
            "Stichtag (Ladedatum). Diese Positionen gelten im System als gedeckt "
            "(Fehlmenge 0, durch Bestand und/oder eingeplante Zugaenge), aber vom "
            "aktuellen Lagerbestand allein deckt KEINE einzelne Charge die offene "
            "Menge - eine Lieferung/ein Füllmenge-Gebinde kann aber nur aus EINER "
            "Chargennummer kommen. Die Bestandssumme kann daher trotz ausreichender "
            "Gesamtmenge nicht in einem Stueck verwendet werden. Füllmenge nur zur "
            "Information mit angezeigt (Standard-Gebindemenge je Werk/Artikel)."
        )
        anzeige = scheindeckung.copy()
        for s in ["Offene Menge", "Bestand (Summe)", "Bestand (größte Charge)", "Füllmenge"]:
            anzeige[s] = anzeige[s].apply(_fmt_menge)
        anzeige["Ladedatum"] = anzeige["Ladedatum"].apply(_fmt_datum)
        st.dataframe(
            anzeige, hide_index=True, use_container_width=True,
            height=_tabellenhoehe(len(anzeige)),
            column_config=_VW_NR_SPALTENKONFIG,
        )


def _render_uebersicht(artikel: pd.DataFrame) -> None:
    gesamt = len(artikel)
    im_rueckstand = artikel[artikel["Rückstand (Menge)"] > 0]
    anzahl_rueckstand = len(im_rueckstand)
    mit_transport = int((im_rueckstand["Zugänge unterwegs"] > 0).sum())
    ohne_transport = anzahl_rueckstand - mit_transport

    rueckstand_summe = im_rueckstand["Rückstand (Menge)"].sum()
    gedeckt_summe = im_rueckstand[["Rückstand (Menge)", "Zugänge unterwegs"]].min(axis=1).sum()
    deckungsgrad = (gedeckt_summe / rueckstand_summe * 100) if rueckstand_summe else 100.0

    if deckungsgrad >= 80:
        text, farbe = "Rückstand ist gut durch Transporte gedeckt.", "#22c55e"
    elif deckungsgrad >= 50:
        text, farbe = "Deckung reicht nur teilweise - bitte pruefen.", "#f59e0b"
    else:
        text, farbe = "Deckung reicht bei weitem nicht - Abbauplan funktioniert so nicht.", "#ef4444"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artikel im Rückstand", f"{anzahl_rueckstand} von {gesamt}")
    c2.metric("davon auf Transport", mit_transport)
    c3.metric("davon ohne eingeplante Menge", ohne_transport)
    c4.metric("Deckungsgrad Rückstand", _fmt_tage(deckungsgrad) + " %")

    st.markdown(
        f"<div style='padding:10px 14px;border-radius:8px;background:{farbe}22;"
        f"border:1px solid {farbe};color:{farbe};font-weight:600;'>"
        f"Eskalation: {text}</div>",
        unsafe_allow_html=True,
    )


def _render_hauptgrafik(artikel: pd.DataFrame) -> None:
    im_rueckstand = artikel[artikel["Rückstand (Menge)"] > 0].copy()
    if im_rueckstand.empty:
        return
    top = im_rueckstand.nlargest(15, "Rückstand (Menge)").copy()
    top["Label"] = top.apply(lambda r: _artikel_label(r["Norm-Nr"], r["VW-Nr"]), axis=1)
    chart = (
        alt.Chart(top)
        .mark_bar()
        .encode(
            y=alt.Y("Label:N", sort="-x", title=None),
            x=alt.X("Rückstand (Menge):Q", title="Rückstand (Menge)"),
            color=alt.Color(
                "Dringlichkeit:N",
                scale=alt.Scale(
                    domain=["Kritisch", "Bald fällig", "Unkritisch"],
                    range=["#ef4444", "#f59e0b", "#22c55e"],
                ),
                legend=alt.Legend(title="Dringlichkeit"),
            ),
            tooltip=[
                alt.Tooltip("Label:N", title="Artikel"),
                alt.Tooltip("Rückstand (Menge):Q", title="Rückstand", format=",.0f"),
                alt.Tooltip("Dringlichkeit:N", title="Dringlichkeit"),
            ],
        )
        .properties(height=400, title="Top-Artikel nach Rückstand")
    )
    st.altair_chart(chart, use_container_width=True)


# --- Wiederverwendbares Kurvendiagramm: kumulierter Bedarf vs. verfuegbare ---
# Deckung (Bestand + Zugaenge) ueber die Zeit. Zeigt anschaulich, AB WANN die
# Deckung nicht mehr ausreicht - genutzt im Rückstand-Drilldown, bei Deckung
# je Artikel und in der Langfristplanung.

def _verlaufsdiagramm(teilmenge: pd.DataFrame, hoehe: int = 300):
    teil = teilmenge.sort_values("Ladedatum").copy()
    teil["Kumulierter Bedarf"] = teil["Offene Menge"].cumsum()
    teil["Verfügbare Deckung"] = teil["Bestand verfügbar"] + teil["Zugang bis Ladedatum"]
    verlauf = pd.concat([
        pd.DataFrame({
            "Ladedatum": teil["Ladedatum"], "Menge": teil["Verfügbare Deckung"],
            "Reihe": "Verfügbare Deckung",
        }),
        pd.DataFrame({
            "Ladedatum": teil["Ladedatum"], "Menge": teil["Kumulierter Bedarf"],
            "Reihe": "Kumulierter Bedarf",
        }),
    ])
    return (
        alt.Chart(verlauf)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("Ladedatum:T", title="Ladedatum"),
            y=alt.Y("Menge:Q", title="Menge"),
            color=alt.Color(
                "Reihe:N",
                scale=alt.Scale(
                    domain=["Verfügbare Deckung", "Kumulierter Bedarf"],
                    range=["#3B82F6", "#EC4899"],
                ),
                legend=alt.Legend(title=None),
            ),
            tooltip=[
                alt.Tooltip("Ladedatum:T", title="Ladedatum"),
                alt.Tooltip("Reihe:N", title="Reihe"),
                alt.Tooltip("Menge:Q", title="Menge", format=",.0f"),
            ],
        )
        .properties(height=hoehe)
    )


# --- Reiter: Rückstand (Artikel -> Werke/Kunden -> Hauptdiagramm) ------------

def _verbrauch_pro_woche_fuer(positionen: pd.DataFrame, norm_nr, kunde: str | None = None) -> float:
    teil = positionen[positionen["Norm-Nr"] == norm_nr]
    if kunde is not None:
        teil = teil[teil["Kunde"] == kunde]
    if teil.empty:
        return 0.0
    spanne_tage = max((positionen["Ladedatum"].max() - positionen["Ladedatum"].min()).days, 1)
    wochen = max(spanne_tage / 7, 1)
    return teil["Bestellmenge"].sum() / wochen


def _render_reichweite_feld(positionen: pd.DataFrame, norm_nr, kunde: str) -> None:
    schluessel = f"{kunde}|{norm_nr}"
    notizen = st.session_state.setdefault("dispo_reichweite", lade_reichweite_notizen())
    gespeichert = notizen.get(schluessel, {})
    verbrauch = _verbrauch_pro_woche_fuer(positionen, norm_nr, kunde)

    st.markdown("**Reichweite beim Kunden**")
    r1, r2, r3 = st.columns(3)
    with r1:
        st.metric("Verbrauch (Stk/Woche, berechnet)", _fmt_menge(verbrauch))
    with r2:
        bestand = st.number_input(
            "Bestand beim Kunden", min_value=0.0,
            value=float(gespeichert.get("bestand", 0.0)),
            key=f"dispo_reichweite_bestand_{schluessel}",
        )
    with r3:
        reichweite = (bestand / verbrauch) if verbrauch > 0 and bestand > 0 else None
        st.metric("Reichweite (Wochen)", _fmt_tage(reichweite) if reichweite is not None else "–")

    notiz = st.text_input(
        "Notiz", value=gespeichert.get("notiz", ""), key=f"dispo_reichweite_notiz_{schluessel}",
    )
    if st.button("Reichweite speichern", key=f"dispo_reichweite_speichern_{schluessel}"):
        notizen[schluessel] = {"bestand": float(bestand), "notiz": notiz}
        speichere_reichweite_notizen(notizen)
        st.session_state["dispo_reichweite"] = notizen
        st.success("Gespeichert.")


def _render_rueckstand_tab(positionen: pd.DataFrame, artikel: pd.DataFrame) -> None:
    st.caption(
        "Jeder Artikel erscheint einmal. Zeile anklicken (Kaestchen links), "
        "um Werke/Kunden, Hauptdiagramm und Details zu sehen."
    )
    rueckstand_artikel = artikel[artikel["Rückstand (Menge)"] > 0]
    if rueckstand_artikel.empty:
        st.success("Kein Rückstand - alles im grünen Bereich.")
        return

    gefiltert = _suche(rueckstand_artikel, ["Norm-Nr", "VW-Nr", "Kunden"], key="dispo_suche_rueckstand")
    anzeige = gefiltert[RUECKSTAND_ARTIKEL_SPALTEN].copy()
    anzeige["Rückstand (Menge)"] = anzeige["Rückstand (Menge)"].apply(_fmt_menge)
    anzeige["Zugänge unterwegs"] = anzeige["Zugänge unterwegs"].apply(_fmt_menge)
    auswahl = st.dataframe(
        anzeige.style.map(_faerbe(_DRINGLICHKEIT_FARBEN), subset=["Dringlichkeit"]),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        height=_tabellenhoehe(len(anzeige)),
        column_config=_VW_NR_SPALTENKONFIG,
        key="dispo_rueckstand_artikel_tabelle",
    )
    zeilen = auswahl.selection.rows if auswahl else []
    if not zeilen:
        return

    gewaehlt = gefiltert.iloc[zeilen[0]]
    norm_nr = gewaehlt["Norm-Nr"]
    positionen_artikel = positionen[positionen["Norm-Nr"] == norm_nr]

    st.divider()
    st.markdown(f"### {_artikel_label(norm_nr, gewaehlt['VW-Nr'])}")

    kunden_liste = sorted(positionen_artikel["Kunde"].dropna().unique())
    kunde_auswahl = st.selectbox(
        "Kunde (für Hauptdiagramm und Details)",
        ["(Alle Kunden)"] + kunden_liste,
        key=f"dispo_kunde_auswahl_{norm_nr}",
    )

    if kunde_auswahl == "(Alle Kunden)":
        positionen_gefiltert = positionen_artikel
    else:
        positionen_gefiltert = positionen_artikel[positionen_artikel["Kunde"] == kunde_auswahl]

    if positionen_gefiltert.empty:
        st.info("Keine Positionen fuer diese Auswahl.")
    else:
        st.altair_chart(_verlaufsdiagramm(positionen_gefiltert), use_container_width=True)

    if kunde_auswahl != "(Alle Kunden)":
        _render_reichweite_feld(positionen, norm_nr, kunde_auswahl)

    st.markdown("**Werke / Positionen**")
    _zeige_tabelle(
        positionen_gefiltert, POSITIONEN_SPALTEN_DETAIL,
        menge_spalten=["Offene Menge"],
        tage_spalten=["Verspätung (Tage)"],
        datum_spalten=["Ladedatum", "Gedeckt ab"],
        farben={"Status": _STATUS_FARBEN, "Versandart": _VERSANDART_FARBEN},
    )


# --- Reiter: Deckung je Artikel (Chart + Kontakt-E-Mail je Artikel) ----------

def _render_deckung_tab(positionen: pd.DataFrame, artikel: pd.DataFrame) -> None:
    st.caption("Zeile anklicken (Kaestchen links), um Reichweite-Grafik und Kontakt-E-Mail zu sehen.")
    such_spalte, filter_spalte = st.columns([2, 1])
    with such_spalte:
        gefiltert = _suche(artikel, ["Norm-Nr", "VW-Nr", "Kunden"], key="dispo_suche_deckung")
    with filter_spalte:
        deckung = _filter_auswahl(gefiltert, "Dringlichkeit", "Dringlichkeit", "deckung")
    anzeige_deckung = deckung[ARTIKEL_SPALTEN].copy()
    for s in MENGEN_SPALTEN_ARTIKEL:
        anzeige_deckung[s] = anzeige_deckung[s].apply(_fmt_menge)
    for s in TAGE_SPALTEN_ARTIKEL:
        anzeige_deckung[s] = anzeige_deckung[s].apply(_fmt_tage)
    for s in DATUM_SPALTEN_ARTIKEL:
        anzeige_deckung[s] = anzeige_deckung[s].apply(_fmt_datum)
    auswahl_ereignis = st.dataframe(
        anzeige_deckung.style.map(_faerbe(_DRINGLICHKEIT_FARBEN), subset=["Dringlichkeit"]),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        height=_tabellenhoehe(len(anzeige_deckung)),
        column_config=_VW_NR_SPALTENKONFIG,
        key="dispo_artikel_tabelle",
    )

    ausgewaehlte_zeilen = auswahl_ereignis.selection.rows if auswahl_ereignis else []
    if not ausgewaehlte_zeilen:
        return

    gewaehlt = deckung.iloc[ausgewaehlte_zeilen[0]]
    norm_nr = gewaehlt["Norm-Nr"]
    norm_nr_key = str(norm_nr)

    st.markdown(f"**Reichweite: {_artikel_label(norm_nr, gewaehlt['VW-Nr'])}**")
    grafik_spalte, mail_spalte = st.columns([2, 1])

    with grafik_spalte:
        artikel_positionen = positionen[positionen["Norm-Nr"] == norm_nr]
        if artikel_positionen.empty:
            st.info("Keine Positionen fuer diesen Artikel gefunden.")
        else:
            st.altair_chart(_verlaufsdiagramm(artikel_positionen, hoehe=320), use_container_width=True)

    with mail_spalte:
        kontakte = st.session_state.setdefault("dispo_kontakte", lade_kontakte())
        neue_mail = st.text_input(
            "E-Mail Ansprechpartner",
            value=kontakte.get(norm_nr_key, ""),
            key=f"dispo_mail_{norm_nr_key}",
        )
        if st.button("E-Mail speichern", key=f"dispo_mail_speichern_{norm_nr_key}"):
            kontakte[norm_nr_key] = neue_mail
            speichere_kontakte(kontakte)
            st.session_state["dispo_kontakte"] = kontakte
            st.success("Gespeichert.")


# --- Reiter: Rückstand mit Bestand (nur physischer Bestand, wie Planung) ----

def _rueckstand_mit_bestand(positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame) -> pd.DataFrame:
    """Von den aktuell als Rückstand gefuehrten Positionen (Ladedatum <
    Stichtag, Status beginnt mit "Rückstand"): welche sind - nach derselben
    Regel wie in der Planung Erstellung (nur physischer Bestand, je Charge/
    Parti-Nr auf volle Fuellmengen abgerundet, keine Zugaenge) - ganz oder
    teilweise JETZT schon durch Bestand gedeckt und koennten sofort
    eingeplant/versendet werden, statt auf einen Zugang zu warten."""
    akut = positionen[positionen["Status"].str.startswith("Rückstand")]
    if akut.empty:
        return akut
    nutzbar = bestand_logik.nutzbarer_bestand_je_artikel(bestand_je_charge, config.BESTAND_VERFUEGBAR)
    _, planbar = bestand_logik.teile_nach_bestand(akut, nutzbar)
    if planbar.empty:
        return planbar

    anzeige = planbar.copy()
    anzeige["Offene Menge (gesamt)"] = akut.loc[anzeige.index, "Offene Menge"]
    anzeige["Gedeckt durch Bestand"] = anzeige["Offene Menge"]
    anzeige["Noch offen ohne Bestand"] = (
        anzeige["Offene Menge (gesamt)"] - anzeige["Gedeckt durch Bestand"]
    )
    return anzeige.sort_values("Ladedatum")


def _render_rueckstand_mit_bestand_tab(positionen: pd.DataFrame, bestand_je_charge: pd.DataFrame) -> None:
    st.caption(
        "Von den aktuellen Rückständen (Ladedatum vor dem Stichtag): welche "
        "sind JETZT schon ganz oder teilweise durch physisch vorhandenen "
        "Bestand gedeckt - unabhängig davon, ob ein Zugang unterwegs ist. "
        "Je Charge/Parti-Nr einzeln auf volle Füllmengen abgerundet (keine "
        "Mischung verschiedener Chargen), ohne Lagerort OUT1 (bereits für "
        "Versand bereitgestellt). Dieselbe Regel wie im Reiter 'Planung "
        "Erstellung' ('Gedeckt durch Bestand' = das, was dort eingeplant "
        "würde). Reicht der Bestand nur für einen Teil, erscheint genau "
        "dieser Teil hier."
    )
    tabelle = _rueckstand_mit_bestand(positionen, bestand_je_charge)
    if tabelle.empty:
        st.success(
            "Kein aktueller Rückstand ist durch vorhandenen Bestand gedeckt - "
            "alles Offene wartet wirklich auf Zugang/Nachschub."
        )
        return

    tabelle = _suche(tabelle, ["Norm-Nr", "VW-Nr", "Kunde", "Abladestelle"], key="dispo_suche_rueckstand_bestand")
    anzeige = tabelle[RUECKSTAND_MIT_BESTAND_SPALTEN].copy()
    anzeige["Ladedatum"] = anzeige["Ladedatum"].dt.strftime("%d.%m.%Y")
    for spalte in ["Offene Menge (gesamt)", "Gedeckt durch Bestand", "Noch offen ohne Bestand"]:
        anzeige[spalte] = anzeige[spalte].apply(_fmt_menge)
    st.dataframe(
        anzeige,
        hide_index=True,
        use_container_width=True,
        height=_tabellenhoehe(len(anzeige)),
        column_config=_VW_NR_SPALTENKONFIG,
        key="dispo_rueckstand_bestand_tabelle",
    )


# --- Reiter: Abbauplan -------------------------------------------------------

def _abbauplan(positionen: pd.DataFrame) -> pd.DataFrame:
    # Nur der AKTUELLE Rückstand/Engpass, nicht die komplette (teils >1 Jahr
    # entfernte) Fehlmengen-Vorschau - sonst landet praktisch alles in "LKW"
    # und der Plan ist nutzlos.
    akut = positionen[
        (positionen["Fehlmenge"] > 0)
        & (positionen["Status"].str.startswith("Rückstand") | (positionen["Status"] == "Engpass"))
    ]
    if akut.empty:
        return akut
    pivot = akut.pivot_table(
        index=["Norm-Nr", "VW-Nr"],
        columns="Transportart",
        values="Fehlmenge",
        aggfunc="sum",
        fill_value=0.0,
    )
    for spalte in TRANSPORTARTEN:
        if spalte not in pivot.columns:
            pivot[spalte] = 0.0
    pivot = pivot[TRANSPORTARTEN]
    pivot["Gesamt offen"] = pivot.sum(axis=1)
    return pivot.reset_index().sort_values("Gesamt offen", ascending=False)


def _render_abbauplan_tab(positionen: pd.DataFrame) -> None:
    st.caption(
        "Nur aktueller Rückstand/Engpass (nicht die komplette Fehlmengen-"
        "Vorschau). Je Artikel, welche offene Menge mit welcher Transportart "
        "noch aufgeholt werden kann (nach Tagen bis Ladedatum: ≤2 Luftfracht, "
        "3–5 Minivan, 6–8 Express LKW, ab 9 LKW)."
    )
    plan = _abbauplan(positionen)
    if plan.empty:
        st.success("Kein aktueller Rückstand/Engpass - kein Abbauplan noetig.")
        return

    plan = _suche(plan, ["Norm-Nr", "VW-Nr"], key="dispo_suche_abbauplan")
    formate = {s: _fmt_menge for s in TRANSPORTARTEN + ["Gesamt offen"]}
    styler = plan.style.format(formate)
    for spalte in TRANSPORTARTEN:
        styler = styler.map(_faerbe_positiv(_TRANSPORTART_FARBEN[spalte]), subset=[spalte])
    st.dataframe(
        styler, hide_index=True, use_container_width=True,
        height=_tabellenhoehe(len(plan)),
        column_config=_VW_NR_SPALTENKONFIG,
    )


# --- Reiter: Langfristplanung (vorausschauend nachbestellen) -----------------

def _render_langfrist_tab(positionen: pd.DataFrame, artikel: pd.DataFrame) -> None:
    st.caption(
        "Artikel ohne aktuellen Rückstand, deren Deckung aber absehbar ausgeht - "
        "rechtzeitig nachbestellen, bevor daraus Rückstand wird. Sortiert nach "
        "verbleibender Reichweite, dringendste zuerst."
    )
    vorausschau = artikel[
        (artikel["Rückstand (Menge)"] <= 0) & artikel["Reichweite (Tage)"].notna()
    ].copy()
    if vorausschau.empty:
        st.success("Alle Artikel ohne Rückstand sind auf absehbare Zeit gedeckt.")
        return

    fehlmenge_je_artikel = positionen.groupby("Norm-Nr")["Fehlmenge"].sum()
    vorausschau["Empfohlene Bestellmenge"] = (
        vorausschau["Norm-Nr"].map(fehlmenge_je_artikel).fillna(0)
    )
    vorausschau = vorausschau.sort_values("Reichweite (Tage)")
    vorausschau = _suche(vorausschau, ["Norm-Nr", "VW-Nr"], key="dispo_suche_langfrist")

    anzeige = vorausschau[LANGFRIST_SPALTEN].copy()
    anzeige["Bestand verfügbar"] = anzeige["Bestand verfügbar"].apply(_fmt_menge)
    anzeige["Zugänge unterwegs"] = anzeige["Zugänge unterwegs"].apply(_fmt_menge)
    anzeige["Reichweite (Tage)"] = anzeige["Reichweite (Tage)"].apply(_fmt_tage)
    anzeige["Nächster Zugang"] = anzeige["Nächster Zugang"].apply(_fmt_datum)
    anzeige["Empfohlene Bestellmenge"] = anzeige["Empfohlene Bestellmenge"].apply(_fmt_menge)

    auswahl = st.dataframe(
        anzeige.style.map(_faerbe(_DRINGLICHKEIT_FARBEN), subset=["Dringlichkeit"]),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        height=_tabellenhoehe(len(anzeige)),
        column_config=_VW_NR_SPALTENKONFIG,
        key="dispo_langfrist_tabelle",
    )
    zeilen = auswahl.selection.rows if auswahl else []
    if not zeilen:
        return

    gewaehlt = vorausschau.iloc[zeilen[0]]
    norm_nr = gewaehlt["Norm-Nr"]
    st.markdown(f"**Verlauf: {_artikel_label(norm_nr, gewaehlt['VW-Nr'])}**")
    artikel_positionen = positionen[positionen["Norm-Nr"] == norm_nr]
    st.altair_chart(_verlaufsdiagramm(artikel_positionen), use_container_width=True)


# --- Reiter: Ausgabedatei (Deutsch/Tuerkisch) --------------------------------

def _export_uebersetzen(df: pd.DataFrame, sprache: str) -> pd.DataFrame:
    export = df.copy()
    if "Status" in export.columns and sprache == "Türkçe":
        export["Status"] = export["Status"].map(STATUS_TR).fillna(export["Status"])
    if "Versandart" in export.columns and sprache == "Türkçe":
        export["Versandart"] = export["Versandart"].map(VERSANDART_TR).fillna(export["Versandart"])
    if "Transportart" in export.columns and sprache == "Türkçe":
        export["Transportart"] = export["Transportart"].map(TRANSPORTART_TR).fillna(export["Transportart"])
    if "Dringlichkeit" in export.columns and sprache == "Türkçe":
        export["Dringlichkeit"] = export["Dringlichkeit"].map(DRINGLICHKEIT_TR).fillna(export["Dringlichkeit"])
    if sprache == "Türkçe":
        export = export.rename(columns=UEBERSETZUNG_TR)
    return export


def _dringlichkeit_sortierung(positionen: pd.DataFrame) -> pd.DataFrame:
    """Dringendstes zuerst: Status-Prioritaet, dann moeglichst ueberfaellig/nah."""
    prioritaet = positionen["Status"].map(_STATUS_PRIORITAET).fillna(99)
    reihenfolge = pd.DataFrame({
        "Prioritaet": prioritaet, "Tage bis Ladedatum": positionen["Tage bis Ladedatum"],
    }, index=positionen.index).sort_values(["Prioritaet", "Tage bis Ladedatum"])
    return positionen.loc[reihenfolge.index]


def _render_positionsliste_alt(positionen: pd.DataFrame) -> None:
    st.caption(
        "Vollstaendige Positionsliste (inkl. Bestellmenge/Geliefert), sortiert "
        "nach Dringlichkeit - oben steht, was am dringendsten gebraucht wird. "
        "Inkl. Transportart (Minivan/LKW/...) als Excel-Datei."
    )
    sprache = st.radio(
        "Sprache", ["Deutsch", "Türkçe"], horizontal=True, key="dispo_export_sprache"
    )

    positionen_sortiert = _dringlichkeit_sortierung(positionen)
    export_df = positionen_sortiert[POSITIONEN_SPALTEN_EXPORT].copy()
    for spalte in DATUM_SPALTEN_EXPORT:
        export_df[spalte] = export_df[spalte].apply(_fmt_datum)
    export_df = _export_uebersetzen(export_df, sprache)

    puffer = io.BytesIO()
    export_df.to_excel(puffer, index=False)
    puffer.seek(0)
    sprachkuerzel = "DE" if sprache == "Deutsch" else "TR"
    st.download_button(
        "📥 Positionsliste herunterladen",
        data=puffer,
        file_name=f"Dispo_Rueckstand_{sprachkuerzel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dispo_export_download",
    )


_BERICHT_VORSCHAU_SPALTEN = {
    "Rang": "Nr.", "Stufe_Text": "Dringlichkeit", "Norm-Nr": "Norm-Nr", "VW-Nr": "VW-Nr",
    "Bestand": "Bestand bei uns", "Unterwegs": "Unterwegs (NRI)",
    "Rückstand fehlt": "Rückstand fehlt", "Rückstand später": "Rückstand unterwegs",
    "Kurz fehlt": "Fehlt (Reaktionszeit)", "Später fehlt": "Fehlt später",
    "Erster Engpass": "Erster Engpass",
}


def _prognose_diagramm(verlauf: dict, stichtag: pd.Timestamp, titel: str, hoehe: int = 260) -> alt.LayerChart:
    """Bestandsprognose wie im Excel-Bericht: Flaeche = Bestand (gruen) bzw.
    Fehlmenge (rot, unter null), Balken = Bedarf (grau), Unterwegs/NRI (blau)
    und - falls verlauf["vorschlag"] da ist - vorgeschlagener Wareneingang
    (orange). Die ersten zwei Punkte (Bestand heute, nach Abzug des
    Rueckstands) liegen auf den zwei Tagen vor dem Stichtag."""
    st_ = pd.Timestamp(stichtag)
    tage = [st_ - pd.Timedelta(days=2), st_ - pd.Timedelta(days=1)] + list(verlauf["tage"][2:])
    vorschlag = verlauf.get("vorschlag")
    df = pd.DataFrame({
        "Datum": pd.to_datetime(tage),
        "Zeitpunkt": ["Bestand heute", f"nach Rückstand (bis {st_:%d.%m.})"] + list(verlauf["labels"][2:]),
        "Bestand": verlauf["bestand"],
        "Bestand (≥ 0)": verlauf["bestand_plus"],
        "Fehlmenge (< 0)": verlauf["fehl_minus"],
        "Bedarf": verlauf["bedarf"],
        "Unterwegs (NRI)": verlauf["zulauf"],
        "Vorschlag": vorschlag if vorschlag is not None else [0.0] * len(tage),
    })
    basis = alt.Chart(df).encode(x=alt.X("Datum:T", title=None, axis=alt.Axis(format="%d.%m.", grid=False)))
    tooltip = [
        alt.Tooltip("Zeitpunkt:N", title="Zeitpunkt"),
        alt.Tooltip("Bestand:Q", title="Bestand (Prognose)", format=",.0f"),
        alt.Tooltip("Bedarf:Q", title="Bedarf", format=",.0f"),
        alt.Tooltip("Unterwegs (NRI):Q", title="Unterwegs (NRI)", format=",.0f"),
    ]
    if vorschlag is not None:
        tooltip.append(alt.Tooltip("Vorschlag:Q", title="Vorschlag", format=",.0f"))
    flaeche_plus = basis.mark_area(color="#10b981", opacity=0.25, line={"color": "#10b981"}).encode(
        y=alt.Y("Bestand (≥ 0):Q", title="Stück"), tooltip=tooltip)
    flaeche_minus = basis.mark_area(color="#ef4444", opacity=0.3, line={"color": "#ef4444"}).encode(
        y="Fehlmenge (< 0):Q", tooltip=tooltip)
    arten = ["Bedarf", "Unterwegs (NRI)"] + (["Vorschlag"] if vorschlag is not None else [])
    farben = ["#94a3b8", "#3b82f6", "#f59e0b"][:len(arten)]
    balken = df.melt(id_vars=["Datum", "Zeitpunkt"], value_vars=arten, var_name="Art", value_name="Menge")
    balken = balken[balken["Menge"] > 0]
    saeulen = alt.Chart(balken).mark_bar(size=4).encode(
        x="Datum:T", y=alt.Y("Menge:Q"),
        color=alt.Color("Art:N", scale=alt.Scale(domain=arten, range=farben),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("Zeitpunkt:N"), alt.Tooltip("Art:N"), alt.Tooltip("Menge:Q", format=",.0f")],
    )
    return alt.layer(flaeche_plus, flaeche_minus, saeulen).properties(
        height=hoehe, title=titel
    ).configure_view(strokeWidth=0).interactive(bind_y=False)


def _fehltag_text(erster) -> str:
    if erster is None:
        return "keiner"
    return "sofort" if erster == "sofort" else f"{pd.Timestamp(erster):%d.%m.%Y}"


def _render_artikel_karte(bericht: dict, gewaehlt: pd.Series, reaktion: int, wochen: int) -> None:
    """Detailkarte zum angeklickten Artikel: Kennzahlen, Ist-Prognose, Bedarf je
    Kunde und Vorschlag mit einstellbarem Wareneingang (rechnet live)."""
    norm_nr = gewaehlt["Norm-Nr"]
    verlauf = bericht["verlauf"].get(norm_nr)
    if not verlauf:
        return
    basis, stichtag = bericht["basis"], bericht["stichtag"]
    stufe = produktionsbericht.STUFEN[int(gewaehlt["Stufe"])]
    st.markdown(
        f"### {gewaehlt['Rang']}. {_artikel_label(norm_nr, gewaehlt['VW-Nr'])}"
        f"  <span style='background:#{stufe['fill']};color:#{stufe['font']};padding:2px 10px;border-radius:10px;"
        f"font-size:0.8rem;font-weight:600'>{stufe['de'].format(tage=reaktion, wochen=wochen)}</span>",
        unsafe_allow_html=True,
    )
    if gewaehlt["Kurztext"]:
        st.caption(gewaehlt["Kurztext"])
    reichweite = gewaehlt["Reichweite Wochen"]
    k = st.columns(7)
    k[0].metric("Bestand bei uns", _fmt_menge(gewaehlt["Bestand"]))
    k[1].metric("Unterwegs (NRI)", _fmt_menge(gewaehlt["Unterwegs"]), f"{gewaehlt['Anzahl NRI']} NRI", delta_color="off")
    k[2].metric("Fehlt gesamt", _fmt_menge(gewaehlt["Fehlt gesamt"]))
    k[3].metric("Ø Bedarf / Woche", _fmt_menge(gewaehlt["Ø Woche"]))
    k[4].metric("Ø Bedarf / Monat", _fmt_menge(gewaehlt["Ø Monat"]))
    k[5].metric("Reichweite", "–" if reichweite is None or pd.isna(reichweite)
                else f"{reichweite:.1f} Wo.".replace(".", ",", 1))
    k[6].metric("Erster Fehltag", _fehltag_text(verlauf["erster_fehltag"]))
    basis_wochen = f"{basis['wochen']:.1f}".replace(".", ",")
    st.caption(f"Ø-Bedarf aus {basis['von']:%d.%m.}–{basis['bis']:%d.%m.} ({basis_wochen} Wochen) · "
               "Reichweite = (Bestand + unterwegs) / Ø Woche")

    links, rechts = st.columns([3, 1])
    with links:
        st.altair_chart(_prognose_diagramm(verlauf, stichtag, "① Bestandsprognose – Ist"), use_container_width=True)
    with rechts:
        st.markdown("**Bedarf je Kunde**")
        kunden = bericht["kunden"].get(norm_nr)
        if kunden is not None and not kunden.empty:
            tabelle = kunden[["Kunde", "Anteil", "Ø Woche", "Ø Monat"]].copy()
            tabelle["Anteil"] = tabelle["Anteil"].apply(lambda a: f"{a:.0%}")
            for s in ("Ø Woche", "Ø Monat"):
                tabelle[s] = tabelle[s].apply(_fmt_menge)
            st.dataframe(tabelle, hide_index=True, use_container_width=True, height=_tabellenhoehe(len(tabelle)))

    vorschlaege = bericht["vorschlag"].get(norm_nr, [])
    zeilen = produktionsbericht.MAX_VORSCHLAEGE
    eingabe = pd.DataFrame({
        "Datum": pd.to_datetime([v["Datum"] for v in vorschlaege] + [pd.NaT] * (zeilen - len(vorschlaege))),
        "Menge": [v["Menge"] for v in vorschlaege] + [None] * (zeilen - len(vorschlaege)),
    })
    links, rechts = st.columns([3, 1])
    with rechts:
        st.markdown("**Wareneingang planen**")
        st.caption("Vorschlag = Fehlmenge (weder bei uns noch unterwegs) zum Bedarfstermin. "
                   "Datum oder Menge ändern → Diagramm rechnet sofort neu. Rot trotz Vorschlag = "
                   "Ware ist unterwegs, kommt aber zu spät.")
        bearbeitet = st.data_editor(
            eingabe, key=f"bericht_vorschlag_{norm_nr}", hide_index=True, num_rows="fixed",
            use_container_width=True,
            column_config={
                "Datum": st.column_config.DateColumn("Datum", format="DD.MM.YYYY"),
                "Menge": st.column_config.NumberColumn("Menge", min_value=0, step=100, format="%d"),
            },
        )
        mit = produktionsbericht.verlauf_mit_vorschlag(
            verlauf, zip(bearbeitet["Datum"], bearbeitet["Menge"]), stichtag)
        summe = pd.to_numeric(bearbeitet["Menge"], errors="coerce").fillna(0).sum()
        st.markdown(
            f"Summe Vorschlag: **{_fmt_menge(summe)}**  \n"
            f"Tiefster Stand: **{_fmt_menge(mit['tiefster'])}** · Bestand Ende: **{_fmt_menge(mit['ende'])}**  \n"
            f"Erster Fehltag: **{_fehltag_text(mit['erster_fehltag'])}**"
        )
    with links:
        st.altair_chart(_prognose_diagramm(mit, stichtag, "② Vorschlag – mit Wareneingang"), use_container_width=True)


def _render_bericht_vorschau(bericht: dict, reaktion: int, wochen: int) -> None:
    artikel = bericht["artikel"]
    vorschau = artikel.copy()
    vorschau["Stufe_Text"] = vorschau["Stufe"].map(
        lambda s: produktionsbericht.STUFEN[s]["de"].format(tage=reaktion, wochen=wochen)
    )
    vorschau = vorschau[list(_BERICHT_VORSCHAU_SPALTEN)].rename(columns=_BERICHT_VORSCHAU_SPALTEN)
    anzeige = vorschau.copy()
    for s in ("Bestand bei uns", "Unterwegs (NRI)", "Rückstand fehlt", "Rückstand unterwegs",
              "Fehlt (Reaktionszeit)", "Fehlt später"):
        anzeige[s] = anzeige[s].apply(lambda w: "" if not w else _fmt_menge(w))
    anzeige["Erster Engpass"] = anzeige["Erster Engpass"].apply(_fmt_datum)
    st.caption("Artikel anklicken → Detailkarte mit Prognose, Ø-Bedarf und einstellbarem Wareneingang "
               "(wie in der Excel-Datei).")
    auswahl = st.dataframe(
        anzeige, hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="single-row",
        height=_tabellenhoehe(len(anzeige)),
        column_config=_VW_NR_SPALTENKONFIG,
        key="bericht_vorschau_tabelle",
    )
    zeilen = auswahl.selection.rows if auswahl else []
    if zeilen:
        st.divider()
        _render_artikel_karte(bericht, artikel.iloc[zeilen[0]], reaktion, wochen)


def _render_export_tab(daten: dict) -> None:
    positionen = daten["positionen"]
    stichtag = pd.Timestamp(daten["stichtag"])
    st.markdown("#### Bericht für die Produktion (Türkei)")
    st.caption(
        "Excel-Datei zum Verschicken an die Produktion. Übersicht: sechs Kacheln und eine Zeile je "
        "Artikel (dringendste zuerst) mit Rückstand, Fehlmengen, Unterwegs und Notizen. Klick auf "
        "die Norm-Nr öffnet die Detailkarte: Kennzahlen (Ø-Bedarf je Woche/Monat, Reichweite, je "
        "Kunde), ① Bestandsprognose und ② Vorschlag mit vorgeschlagenem Wareneingang – Datum und "
        "Menge stehen in gelben Feldern und sind änderbar, das Diagramm rechnet sofort neu. "
        "„Fehlt“ = weder bei uns noch unterwegs, muss also aus der Türkei kommen. Spaltenköpfe "
        "Deutsch/Türkisch. Notizen in die Übersicht schreiben; lädst du den letzten Bericht unten "
        "hoch, werden sie übernommen."
    )
    c1, c2, c3 = st.columns(3)
    reaktion = int(c1.number_input(
        "Reaktionszeit Türkei (Tage)", min_value=1, max_value=60,
        value=produktionsbericht.STANDARD_REAKTION_TAGE, key="bericht_reaktion",
        help="Engpässe innerhalb dieser Tage stehen direkt nach den Rückständen.",
    ))
    wochen = int(c2.number_input(
        "Vorschau (Wochen)", min_value=1, max_value=52,
        value=produktionsbericht.STANDARD_WOCHEN, key="bericht_wochen",
    ))
    sprache = c3.radio("Sprache der Hinweistexte", ["Türkçe", "Deutsch"], horizontal=True, key="bericht_sprache")
    gedeckte = st.checkbox("Auch vollständig gedeckte Artikel aufnehmen", key="bericht_gedeckte")
    vorher = st.file_uploader(
        "Notizen übernehmen: letzten Bericht hochladen (optional)", type=["xlsx"], key="bericht_vorher",
    )

    notizen = {}
    if vorher is not None:
        try:
            notizen = produktionsbericht.lese_notizen(vorher.getvalue())
        except Exception as exc:  # beschaedigte/fremde Datei - Bericht trotzdem erstellen
            st.warning(f"Notizen konnten nicht gelesen werden: {exc}")

    bericht = produktionsbericht.berechne_bericht(
        positionen, daten.get("zugang"), stichtag, reaktion, wochen, gedeckte,
    )
    kz = produktionsbericht.kennzahlen(bericht)
    stufen = kz["je_stufe"]
    mengen = kz["menge_je_stufe"]
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Rückstand – fehlt", stufen[1], f"{_fmt_menge(mengen[1])} Stk", delta_color="off")
    m2.metric("Rückstand – unterwegs", stufen[2], f"{_fmt_menge(mengen[2])} Stk", delta_color="off")
    m3.metric(f"Engpass ≤ {reaktion} Tage", stufen[3], f"{_fmt_menge(mengen[3])} Stk", delta_color="off")
    m4.metric(f"Später ≤ {wochen} Wochen", stufen[4], f"{_fmt_menge(mengen[4])} Stk", delta_color="off")
    m5.metric("NRI für diese Artikel", kz["nri_bericht"], f"{_fmt_menge(kz['unterwegs_menge'])} Stk", delta_color="off")
    m6.metric("Fehlt gesamt", _fmt_menge(kz["fehlt_gesamt"]))

    letztes = positionen["Ladedatum"].max() if not positionen.empty else pd.NaT
    if pd.notna(letztes) and letztes < bericht["horizont"] - pd.Timedelta(days=7):
        st.warning(
            f"⚠️ Der Bedarfsexport reicht nur bis zum {letztes:%d.%m.%Y}. Für die "
            f"{wochen}-Wochen-Vorschau den Lieferplan-Export in SAP bis mindestens "
            f"{bericht['horizont']:%d.%m.%Y} ziehen – sonst fehlen spätere Bedarfe im Bericht."
        )
    if notizen:
        im_bericht = set(bericht["artikel"]["Norm-Nr"]) if not bericht["artikel"].empty else set()
        archiv = len([n for n in notizen if n not in im_bericht])
        st.success(
            f"{len(notizen)} Artikel mit Notizen übernommen"
            + (f" ({archiv} davon stehen gerade nicht im Bericht → Blatt „Notizen-Archiv“)." if archiv else ".")
        )

    inhalt = produktionsbericht.erstelle_bericht_datei(
        bericht, notizen, "TR" if sprache == "Türkçe" else "DE",
    )
    st.download_button(
        "📥 Bericht für die Produktion herunterladen",
        data=inhalt,
        file_name=produktionsbericht.dateiname(stichtag),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="bericht_download",
        type="primary",
    )

    artikel = bericht["artikel"]
    if artikel.empty:
        st.success("Nichts zu melden: kein Rückstand und keine Fehlmenge im Vorschauzeitraum.")
    else:
        _render_bericht_vorschau(bericht, reaktion, wochen)
    with st.expander("So ist die Datei aufgebaut"):
        st.markdown(
            "- **Übersicht** – oben sechs Kacheln: Fehlt gesamt, Artikel je Dringlichkeit (mit "
            "Stückzahlen) und Unterwegs (NRI). Darunter eine Zeile je Artikel, dringendste zuerst: "
            "1 Rückstand fehlt → 2 Rückstand unterwegs (Ware kommt, aber zu spät) → 3 Engpass in der "
            "Reaktionszeit → 4 später. Nur die Mengen, die zählen, plus Notiz Dispo (blau) und "
            "Notiz Produktion (orange). Klick auf die Norm-Nr springt zur Detailkarte.\n"
            "- **Details** – je Artikel eine große Karte: Kennzahlen (Bestand, Unterwegs, Fehlt, "
            "Ø Bedarf je Woche/Monat, Reichweite, erster Fehltag), ① Bestandsprognose (grün = "
            "Bestand, rot = Fehlmenge, grau = Bedarf, blau = unterwegs/NRI – wie MD04) mit Bedarf je "
            "Kunde, ② Vorschlag: dieselbe Prognose mit vorgeschlagenem Wareneingang (orange). Datum "
            "und Menge stehen daneben in gelben Feldern, vorbelegt mit der Fehlmenge zum "
            "Bedarfstermin – ändern, und das Diagramm rechnet sofort neu (Formeln, kein Makro). "
            "Darunter die Termine: unterwegs (NRI), jede Einteilung im Rückstand und in der "
            "Reaktionszeit mit „rechtzeitig / kommt später / fehlt“ und Hinweis, spätere Wochen mit "
            "Fehlmenge. Beim Drucken steht jede Karte auf einer eigenen Seite.\n"
            "- **Wochen** – Bedarf, Zulauf und Fehlmenge je Kalenderwoche bis zum Vorschauende.\n"
            "- **Unterwegs** – alle Zugänge (ZMM1000) mit NRI, Spediteur und Ankunft.\n"
            "- **Notizen-Archiv** – Notizen von Artikeln, die gerade nicht im Bericht stehen; sie "
            "kommen automatisch zurück, sobald der Artikel wieder auftaucht."
        )
    with st.expander("Positionsliste wie bisher (alle Einteilungen, DE/TR)"):
        _render_positionsliste_alt(positionen)


# --- Datenquelle (Upload / Ordner) -------------------------------------------

def _render_datenquelle() -> None:
    st.subheader("Daten aktualisieren")
    hochgeladen = st.file_uploader(
        "SAP-Exporte hochladen (Bedarf, Bestand, Zugänge, optional Stock Report)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="dispo_upload",
    )

    with st.expander("Oder: Ordner mit SAP-Exporten (nur lokal verfuegbar, z. B. Netzlaufwerk)"):
        ordner = st.text_input(
            "Ordner mit den taeglichen SAP-Exporten",
            value=st.session_state.get("dispo_ordner", lade_gespeicherten_ordner()),
            key="dispo_ordner_input",
        )
        if st.button("Ordner merken", key="dispo_ordner_speichern"):
            speichere_ordner(ordner)
            st.session_state["dispo_ordner"] = ordner
            st.success("Ordner gemerkt - wird beim naechsten Start automatisch vorausgefuellt.")

    if hochgeladen:
        aktuelle_signatur = tuple(sorted((d.name, d.size) for d in hochgeladen))
        quelle_ordner = st.session_state.setdefault(
            "dispo_upload_ordner", tempfile.mkdtemp(prefix="dispo_upload_")
        )
    elif ordner:
        aktuelle_signatur = ordner
        quelle_ordner = ordner
    else:
        aktuelle_signatur = None
        quelle_ordner = None

    aktualisieren = st.button("🔄 Aktualisieren", key="dispo_aktualisieren")

    if not quelle_ordner:
        if not st.session_state.get("dispo_daten"):
            st.info("Bitte Dateien hochladen oder (nur lokal) einen Ordner angeben.")
        return

    signatur_geaendert = st.session_state.get("dispo_geladene_signatur") != aktuelle_signatur
    if "dispo_daten" not in st.session_state or signatur_geaendert or aktualisieren:
        if hochgeladen:
            for datei in hochgeladen:
                (Path(quelle_ordner) / datei.name).write_bytes(datei.getvalue())
        with st.spinner("SAP-Exporte werden eingelesen..."):
            try:
                st.session_state["dispo_daten"] = _lade_und_berechne(quelle_ordner)
                st.session_state["dispo_geladene_signatur"] = aktuelle_signatur
            except (ValueError, FileNotFoundError) as exc:
                st.error(f"Fehler beim Einlesen: {exc}")
                return
        st.rerun()


_SUBTAB_CSS = """
<style>
.st-key-dispo_subtabs div[role="tablist"] {
    gap: 8px;
    border-bottom: 2px solid rgba(139,92,246,0.25);
    margin-bottom: 6px;
}
.st-key-dispo_subtabs div[data-testid="stTab"] {
    padding: 16px 28px !important;
    border-radius: 10px 10px 0 0;
    transition: background 0.15s ease;
}
.st-key-dispo_subtabs div[data-testid="stTab"] p {
    font-size: 1.15rem !important;
    font-weight: 600 !important;
}
.st-key-dispo_subtabs div[data-testid="stTab"][data-selected="true"] {
    background: rgba(139,92,246,0.15);
}
</style>
"""


def render_dispo_tab() -> None:
    st.title("Dashboard Dispo")
    st.markdown(
        '<span class="vwai-badge">✨ Dispositions-Übersicht</span>',
        unsafe_allow_html=True,
    )

    _render_legende()

    # Stabiler Platzhalter: IMMER genau einmal aufgerufen (ob mit oder ohne
    # Daten), damit die Position der nachfolgenden Elemente (insbesondere der
    # Upload-Widgets ganz unten) sich zwischen Laeufen nie verschiebt - eine
    # Verschiebung davor hat frueher den Auswahlzustand von st.tabs() zerstoert.
    inhalt_platzhalter = st.container()

    with inhalt_platzhalter:
        daten = st.session_state.get("dispo_daten")
        if daten:
            positionen = daten["positionen"]
            artikel = daten["artikel"]
            stichtag = daten["stichtag"]

            st.caption(f"Stichtag: {stichtag:%d.%m.%Y}")

            warnung_platz = st.empty()
            veraltete_quellen = [
                label for label, datum, _ in daten["datenstand"]
                if (stichtag - datum).days >= config.QUELLE_VERALTET_TAGE
            ]
            if veraltete_quellen:
                warnung_platz.warning("⚠️ Veraltete Daten: " + ", ".join(veraltete_quellen))

            _render_scheindeckung_warnung(daten["scheindeckung"])
            _render_uebersicht(artikel)
            _render_hauptgrafik(artikel)

            st.markdown(_SUBTAB_CSS, unsafe_allow_html=True)
            with st.container(key="dispo_subtabs"):
                (
                    reiter_rueckstand, reiter_rueckstand_bestand, reiter_deckung, reiter_abbau,
                    reiter_langfrist, reiter_export,
                ) = st.tabs(
                    ["Rückstand", "Rückstand mit Bestand", "Deckung je Artikel", "Abbauplan",
                     "Langfristplanung", "Ausgabedatei"]
                )
                with reiter_rueckstand:
                    _render_rueckstand_tab(positionen, artikel)
                with reiter_rueckstand_bestand:
                    _render_rueckstand_mit_bestand_tab(positionen, daten.get("bestand_je_charge"))
                with reiter_deckung:
                    _render_deckung_tab(positionen, artikel)
                with reiter_abbau:
                    _render_abbauplan_tab(positionen)
                with reiter_langfrist:
                    _render_langfrist_tab(positionen, artikel)
                with reiter_export:
                    _render_export_tab(daten)
        else:
            st.info("Bitte unten SAP-Exporte hochladen, um das Dashboard zu sehen.")

    st.divider()
    _render_datenquelle()
