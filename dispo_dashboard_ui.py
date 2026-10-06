"""Oberflaeche fuer den Reiter "Dashboard Dispo" in VW AI.

Zeigt die von dispo_dashboard (config/loaders/logic - unveraendert genutzt)
berechnete Auswertung an. Die taeglichen SAP-Exporte kommen aus einem lokalen
Ordner (Netzlaufwerk), daher nur in der lokal installierten Version
verfuegbar, nicht in der zentral gehosteten.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from dispo_dashboard import config, loaders, logic

ORDNER_DATEI = ".dispo_sap_ordner.txt"

QUELLEN = [
    ("bedarf", "Bedarf (Lieferplan-Einteilungen)"),
    ("bestand", "Bestand (EWM)"),
    ("zugang", "Zugänge (ZMM1000)"),
    ("stockreport", "Stock Report Versender (nur Info)"),
]

STATUS_REIHENFOLGE = [
    "Rückstand ungedeckt",
    "Rückstand, Zugang kommt",
    "Rückstand gedeckt",
    "Engpass",
    "Zugang zu spät",
    "Fehlmenge später",
    "Gedeckt",
    "Erledigt",
]

POSITIONEN_SPALTEN = [
    "Werk", "Kunde", "Abladestelle", "Norm-Nr", "Kurztext", "Ladedatum",
    "Wunschtermin", "Bestellmenge", "Geliefert", "Offene Menge", "Fehlmenge",
    "Gedeckt ab", "Verspätung (Tage)", "Status",
]

ARTIKEL_SPALTEN = [
    "Norm-Nr", "Kurztext", "Kunden", "Bestand verfügbar", "Offene Menge gesamt",
    "Rückstand (Menge)", "Erste Fehlmenge am", "Zugänge unterwegs",
    "Nächster Zugang", "Reichweite (Tage)", "Ampel",
]

_AMPEL_FARBEN = {"Rot": "#ef4444", "Gelb": "#f59e0b", "Grün": "#22c55e"}
_STATUS_FARBEN = {
    "Rückstand ungedeckt": "#ef4444",
    "Engpass": "#ef4444",
    "Rückstand, Zugang kommt": "#f59e0b",
    "Zugang zu spät": "#f59e0b",
    "Rückstand gedeckt": "#f59e0b",
    "Gedeckt": "#22c55e",
    "Erledigt": "#22c55e",
}


def lade_gespeicherten_ordner() -> str:
    try:
        return Path(ORDNER_DATEI).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def speichere_ordner(pfad: str) -> None:
    Path(ORDNER_DATEI).write_text(pfad, encoding="utf-8")


def _lade_und_berechne(ordner: str) -> dict:
    dateien = loaders.neueste_dateien(ordner)
    fehlend = [t for t in ["bedarf", "bestand", "zugang"] if t not in dateien]
    if fehlend:
        raise ValueError(f"Es fehlen Dateien fuer: {', '.join(fehlend)}")

    stichtag = loaders.datum_der_datei(dateien["bedarf"][0])
    bedarf = loaders.lade_bedarf(dateien["bedarf"][0])
    _, bestand_artikel = loaders.lade_bestand(dateien["bestand"][0])
    zugang = loaders.lade_zugang(dateien["zugang"][0])
    positionen, artikel, _ = logic.berechne(bedarf, bestand_artikel, zugang, stichtag)

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


def render_dispo_tab() -> None:
    st.title("Dashboard Dispo")
    st.markdown(
        '<span class="vwai-badge">✨ Dispositions-Übersicht</span>',
        unsafe_allow_html=True,
    )

    if os.name != "nt":
        st.info(
            "Dashboard Dispo ist nur in der lokal installierten Version "
            "verfuegbar (greift auf einen Windows-/Netzlaufwerk-Ordner mit "
            "den taeglichen SAP-Exporten zu, den eine zentral gehostete "
            "Version nicht erreichen kann). Bitte dafuer die lokale "
            "Installation auf einem Windows-PC nutzen."
        )
        return

    with st.expander("Ordner-Einstellungen"):
        ordner = st.text_input(
            "Ordner mit den taeglichen SAP-Exporten",
            value=st.session_state.get("dispo_ordner", lade_gespeicherten_ordner()),
            key="dispo_ordner_input",
        )
        if st.button("Ordner merken", key="dispo_ordner_speichern"):
            speichere_ordner(ordner)
            st.session_state["dispo_ordner"] = ordner
            st.success("Ordner gemerkt - wird beim naechsten Start automatisch vorausgefuellt.")

    if not ordner:
        st.info("Bitte oben einen Ordner mit den SAP-Exporten angeben.")
        return

    kopf_links, kopf_rechts = st.columns([5, 1])
    with kopf_rechts:
        aktualisieren = st.button("🔄 Aktualisieren", key="dispo_aktualisieren")

    ordner_geaendert = st.session_state.get("dispo_geladener_ordner") != ordner
    if "dispo_daten" not in st.session_state or ordner_geaendert or aktualisieren:
        with st.spinner("SAP-Exporte werden eingelesen..."):
            try:
                st.session_state["dispo_daten"] = _lade_und_berechne(ordner)
                st.session_state["dispo_geladener_ordner"] = ordner
            except (ValueError, FileNotFoundError) as exc:
                st.error(f"Fehler beim Einlesen: {exc}")
                return

    daten = st.session_state["dispo_daten"]
    stichtag = daten["stichtag"]
    positionen = daten["positionen"]
    artikel = daten["artikel"]

    with kopf_links:
        st.caption(f"Stichtag: {stichtag:%d.%m.%Y}")

    # --- Datenstand je Quelle -------------------------------------------------
    datenstand_zeilen = []
    for label, datum, name in daten["datenstand"]:
        veraltet = (stichtag - datum).days >= config.QUELLE_VERALTET_TAGE
        datenstand_zeilen.append({
            "Quelle": label,
            "Datenstand": datum.strftime("%d.%m.%Y") + (" ⚠️ veraltet" if veraltet else ""),
            "Datei": name,
        })
    st.dataframe(pd.DataFrame(datenstand_zeilen), hide_index=True, use_container_width=True)

    # --- Kennzahlen -------------------------------------------------------
    status_counts = positionen["Status"].value_counts()
    ampel_counts = artikel["Ampel"].value_counts()

    status_cols = st.columns(len(STATUS_REIHENFOLGE))
    for col, status in zip(status_cols, STATUS_REIHENFOLGE):
        col.metric(status, int(status_counts.get(status, 0)))

    ampel_cols = st.columns(3)
    for col, ampel in zip(ampel_cols, ["Rot", "Gelb", "Grün"]):
        col.metric(f"Ampel {ampel}", int(ampel_counts.get(ampel, 0)))

    st.divider()

    # --- Rückstand ----------------------------------------------------------
    st.subheader("Rückstand")
    rueckstand = positionen[positionen["Status"].str.startswith("Rückstand")]
    f1, f2 = st.columns(2)
    with f1:
        rueckstand = _filter_auswahl(rueckstand, "Werk", "Werk", "rueckstand")
    with f2:
        rueckstand = _filter_auswahl(rueckstand, "Kunde", "Kunde", "rueckstand")
    st.dataframe(
        rueckstand[POSITIONEN_SPALTEN].style.map(_faerbe(_STATUS_FARBEN), subset=["Status"]),
        hide_index=True,
        use_container_width=True,
    )

    # --- Deckung je Artikel --------------------------------------------------
    st.subheader("Deckung je Artikel")
    deckung = _filter_auswahl(artikel, "Ampel", "Ampel", "deckung")
    st.dataframe(
        deckung[ARTIKEL_SPALTEN].style.map(_faerbe(_AMPEL_FARBEN), subset=["Ampel"]),
        hide_index=True,
        use_container_width=True,
    )

    # --- Positionen -----------------------------------------------------------
    st.subheader("Positionen")
    p1, p2, p3 = st.columns(3)
    pos_gefiltert = positionen
    with p1:
        pos_gefiltert = _filter_auswahl(pos_gefiltert, "Werk", "Werk", "positionen")
    with p2:
        pos_gefiltert = _filter_auswahl(pos_gefiltert, "Kunde", "Kunde", "positionen")
    with p3:
        pos_gefiltert = _filter_auswahl(pos_gefiltert, "Status", "Status", "positionen")
    st.dataframe(
        pos_gefiltert[POSITIONEN_SPALTEN].style.map(_faerbe(_STATUS_FARBEN), subset=["Status"]),
        hide_index=True,
        use_container_width=True,
    )
