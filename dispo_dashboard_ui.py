"""Oberflaeche fuer den Reiter "Dashboard Dispo" in VW AI.

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
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dispo_dashboard import config, loaders, logic

ORDNER_DATEI = ".dispo_sap_ordner.txt"
KONTAKTE_DATEI = ".dispo_kontakte.json"
REICHWEITE_DATEI = ".dispo_reichweite.json"

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
    "Werk", "Kunde", "Abladestelle", "Norm-Nr", "Kurztext", "Ladedatum",
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
    "Norm-Nr", "Kurztext", "Kunden", "Rückstand (Menge)", "Zugänge unterwegs", "Dringlichkeit",
]

ARTIKEL_SPALTEN = [
    "Norm-Nr", "Kurztext", "Kunden", "Bestand verfügbar", "Offene Menge gesamt",
    "Rückstand (Menge)", "Erste Fehlmenge am", "Zugänge unterwegs",
    "Nächster Zugang", "Reichweite (Tage)", "Dringlichkeit",
]

LANGFRIST_SPALTEN = [
    "Norm-Nr", "Kurztext", "Bestand verfügbar", "Zugänge unterwegs",
    "Reichweite (Tage)", "Nächster Zugang", "Empfohlene Bestellmenge", "Dringlichkeit",
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

# --- Uebersetzung fuer die Ausgabedatei --------------------------------------
UEBERSETZUNG_TR = {
    "Werk": "Tesis", "Kunde": "Müşteri", "Abladestelle": "Boşaltma Yeri",
    "Norm-Nr": "Parça No", "Kurztext": "Kısa Metin", "Ladedatum": "Yükleme Tarihi",
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


def _lade_und_berechne(ordner: str) -> dict:
    dateien = loaders.neueste_dateien(ordner)
    fehlend = [t for t in ["bedarf", "bestand", "zugang"] if t not in dateien]
    if fehlend:
        raise ValueError(f"Es fehlen Dateien fuer: {', '.join(fehlend)}")

    stichtag = loaders.datum_der_datei(dateien["bedarf"][0])
    bedarf = loaders.lade_bedarf(dateien["bedarf"][0])
    _, bestand_artikel = loaders.lade_bestand(dateien["bestand"][0])
    zugang = loaders.lade_zugang(dateien["zugang"][0])
    positionen, artikel, zugang_vorbereitet = logic.berechne(bedarf, bestand_artikel, zugang, stichtag)

    positionen = positionen.copy()
    positionen["Deckender Import"] = _deckende_importe(positionen, zugang_vorbereitet)
    positionen["Versandart"] = positionen.apply(_versandart, axis=1)
    positionen["Transportart"] = positionen["Tage bis Ladedatum"].apply(_transportart)
    positionen["Dringlichkeit"] = positionen["Status"].apply(_dringlichkeit_position)

    artikel = artikel.copy()
    artikel["Dringlichkeit"] = artikel["Ampel"].map(_DRINGLICHKEIT_TEXT)

    datenstand = [
        (label, loaders.datum_der_datei(dateien[t][0], stichtag), Path(dateien[t][0]).name)
        for t, label in QUELLEN if t in dateien
    ]
    return {
        "stichtag": stichtag,
        "positionen": positionen,
        "artikel": artikel,
        "datenstand": datenstand,
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
    st.dataframe(styler, hide_index=True, use_container_width=True)


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
    top["Label"] = top["Norm-Nr"].astype(str) + " – " + top["Kurztext"]
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

    anzeige = rueckstand_artikel[RUECKSTAND_ARTIKEL_SPALTEN].copy()
    anzeige["Rückstand (Menge)"] = anzeige["Rückstand (Menge)"].apply(_fmt_menge)
    anzeige["Zugänge unterwegs"] = anzeige["Zugänge unterwegs"].apply(_fmt_menge)
    auswahl = st.dataframe(
        anzeige.style.map(_faerbe(_DRINGLICHKEIT_FARBEN), subset=["Dringlichkeit"]),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="dispo_rueckstand_artikel_tabelle",
    )
    zeilen = auswahl.selection.rows if auswahl else []
    if not zeilen:
        return

    gewaehlt = rueckstand_artikel.iloc[zeilen[0]]
    norm_nr = gewaehlt["Norm-Nr"]
    positionen_artikel = positionen[positionen["Norm-Nr"] == norm_nr]

    st.divider()
    st.markdown(f"### {norm_nr} – {gewaehlt['Kurztext']}")

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
    deckung = _filter_auswahl(artikel, "Dringlichkeit", "Dringlichkeit", "deckung")
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
        key="dispo_artikel_tabelle",
    )

    ausgewaehlte_zeilen = auswahl_ereignis.selection.rows if auswahl_ereignis else []
    if not ausgewaehlte_zeilen:
        return

    gewaehlt = deckung.iloc[ausgewaehlte_zeilen[0]]
    norm_nr = gewaehlt["Norm-Nr"]
    norm_nr_key = str(norm_nr)

    st.markdown(f"**Reichweite: {norm_nr} – {gewaehlt['Kurztext']}**")
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
        index=["Norm-Nr", "Kurztext"],
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

    formate = {s: _fmt_menge for s in TRANSPORTARTEN + ["Gesamt offen"]}
    styler = plan.style.format(formate)
    for spalte in TRANSPORTARTEN:
        styler = styler.map(_faerbe_positiv(_TRANSPORTART_FARBEN[spalte]), subset=[spalte])
    st.dataframe(styler, hide_index=True, use_container_width=True)


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
        key="dispo_langfrist_tabelle",
    )
    zeilen = auswahl.selection.rows if auswahl else []
    if not zeilen:
        return

    gewaehlt = vorausschau.iloc[zeilen[0]]
    norm_nr = gewaehlt["Norm-Nr"]
    st.markdown(f"**Verlauf: {norm_nr} – {gewaehlt['Kurztext']}**")
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


def _render_export_tab(positionen: pd.DataFrame) -> None:
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
        "📥 Ausgabedatei herunterladen",
        data=puffer,
        file_name=f"Dispo_Rueckstand_{sprachkuerzel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dispo_export_download",
    )


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

            _render_uebersicht(artikel)
            _render_hauptgrafik(artikel)

            (
                reiter_rueckstand, reiter_deckung, reiter_abbau,
                reiter_langfrist, reiter_export,
            ) = st.tabs(
                ["Rückstand", "Deckung je Artikel", "Abbauplan",
                 "Langfristplanung", "Ausgabedatei"]
            )
            with reiter_rueckstand:
                _render_rueckstand_tab(positionen, artikel)
            with reiter_deckung:
                _render_deckung_tab(positionen, artikel)
            with reiter_abbau:
                _render_abbauplan_tab(positionen)
            with reiter_langfrist:
                _render_langfrist_tab(positionen, artikel)
            with reiter_export:
                _render_export_tab(positionen)
        else:
            st.info("Bitte unten SAP-Exporte hochladen, um das Dashboard zu sehen.")

    st.divider()
    _render_datenquelle()
