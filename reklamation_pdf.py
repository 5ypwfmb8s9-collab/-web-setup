"""Reklamationen PDF-Auswertung (Testaufbau).

Andere Art von "Reklamation" als reklamation_lokal.py (dort: Ausfallfracht-/
Storno-Rechnungen von Duvenbeck). Hier geht es um Reklamations-PDFs von
Kunden (Qualitaets-/Lieferreklamationen), die in Format und Sprache stark
variieren koennen (Deutsch, Englisch, ...). Die Felder Grund/Werk/Kunde/
Art.-Nr./Abladestelle/Wert werden per Stichwort-Heuristik aus dem PDF-Text
gezogen - das ist ein erster Testaufbau, keine zuverlaessige Texterkennung
fuer beliebige Layouts. Nutzer prueft/korrigiert die Tabelle vor dem Export.

Kein Bezug zur Dispo-Logik - eigenstaendiges Feature, eigene Datenablage.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import altair as alt
import pandas as pd
import pdfplumber
import streamlit as st

EINTRAEGE_DATEI = ".reklamation_pdf_eintraege.json"

SPALTEN = ["Grund", "Werk", "Kunde", "ArtNr", "Abladestelle", "Wert", "Dateiname"]
SPALTEN_LABEL = {
    "ArtNr": "Art.-Nr.",
}

# Je Feld mehrere Label-Varianten (Deutsch/Englisch/haeufige Abkuerzungen),
# erster Treffer gewinnt. Bewusst grosszuegig - lieber ein unsicherer Treffer
# als gar keiner, da der Nutzer die Tabelle ohnehin durchsieht.
_MUSTER: dict[str, list[str]] = {
    "Grund": [
        r"(?:Reklamationsgrund|Grund|Ursache|Fehlerbeschreibung|Mängelbeschreibung|"
        r"M[äa]ngelart|Reason(?:\s*for\s*complaint)?|Complaint\s*reason|"
        r"Defect\s*description|Root\s*cause)\s*[:\-]\s*(.+)",
    ],
    "Werk": [
        r"(?:Werk(?:scode)?|Kundenwerk|Plant(?:\s*code)?|Receiving\s*plant)\s*[:\-]\s*(\S.*?)(?:\n|$)",
    ],
    "Kunde": [
        r"(?:Kunde|Auftraggeber|Empf[aä]nger|Customer|Client)\s*[:\-]\s*(.+)",
    ],
    "ArtNr": [
        r"(?:Art\.?-?Nr\.?|Artikelnummer|Teilenummer|Material(?:nummer)?|"
        r"Article\s*No\.?|Part\s*No\.?|Part\s*Number)\s*[:\-]\s*(\S+)",
    ],
    "Abladestelle": [
        r"(?:Abladestelle|Lieferort|Werksanschrift|Unloading\s*point|"
        r"Ship-?to(?:\s*location)?|Delivery\s*point)\s*[:\-]\s*(.+)",
    ],
    "Wert": [
        r"(?:Reklamationswert|Schadensh[oö]he|Wert|Betrag|Value|Amount|"
        r"Claim\s*amount|Cost)\s*[:\-]\s*([\d.,]+)\s*(?:EUR|€|USD|\$)?",
    ],
}


def _erster_treffer(text: str, muster_liste: list[str]) -> str:
    for muster in muster_liste:
        treffer = re.search(muster, text, re.IGNORECASE)
        if treffer:
            return treffer.group(1).strip()[:150]
    return ""


def lese_pdf_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n".join(seite.extract_text() or "" for seite in pdf.pages)
    except Exception:
        return ""


def werte_pdf_aus(pdf_bytes: bytes, dateiname: str) -> dict:
    text = lese_pdf_text(pdf_bytes)
    eintrag = {feld: _erster_treffer(text, muster) for feld, muster in _MUSTER.items()}
    eintrag["Dateiname"] = dateiname
    return eintrag


def lade_eintraege() -> list[dict]:
    try:
        return json.loads(Path(EINTRAEGE_DATEI).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def speichere_eintraege(eintraege: list[dict]) -> None:
    Path(EINTRAEGE_DATEI).write_text(
        json.dumps(eintraege, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _tabellenhoehe(anzahl_zeilen: int) -> int:
    return 35 * max(anzahl_zeilen, 1) + 40


def _render_kreisdiagramm(df: pd.DataFrame) -> None:
    gruende = df[df["Grund"].astype(str).str.strip() != ""]["Grund"].value_counts()
    if gruende.empty:
        st.info("Noch kein 'Grund' erkannt - das Kreisdiagramm erscheint, sobald Werte da sind.")
        return
    kreis_df = gruende.reset_index()
    kreis_df.columns = ["Grund", "Anzahl"]
    farben = ["#8B5CF6", "#3B82F6", "#EC4899", "#f59e0b", "#22c55e", "#ef4444", "#06b6d4", "#a3a3a3"]
    chart = (
        alt.Chart(kreis_df)
        .mark_arc(innerRadius=60)
        .encode(
            theta=alt.Theta("Anzahl:Q"),
            color=alt.Color(
                "Grund:N",
                scale=alt.Scale(range=farben[: max(len(kreis_df), 1)]),
                legend=alt.Legend(title="Grund"),
            ),
            tooltip=[alt.Tooltip("Grund:N"), alt.Tooltip("Anzahl:Q")],
        )
        .properties(height=340, title="Reklamationen nach Grund")
    )
    st.altair_chart(chart, use_container_width=True)


def render_reklamation_pdf_tab() -> None:
    st.caption(
        "Testaufbau: Reklamations-PDFs hochladen (Deutsch, Englisch, "
        "unterschiedliche Formate/Vorlagen moeglich). Grund, Werk, Kunde, "
        "Art.-Nr., Abladestelle und Wert werden per Stichwort-Erkennung aus "
        "dem PDF-Text gezogen - das ist noch keine zuverlaessige Erkennung "
        "fuer beliebige Layouts. Bitte die Tabelle unten pruefen und bei "
        "Bedarf von Hand korrigieren, bevor die Ausgabedatei "
        "heruntergeladen wird."
    )

    eintraege = st.session_state.setdefault("reklamation_pdf_eintraege", lade_eintraege())
    verarbeitet = st.session_state.setdefault("reklamation_pdf_verarbeitet", set())

    dashboard_platzhalter = st.container()

    hochgeladen = st.file_uploader(
        "Reklamations-PDFs hochladen",
        type=["pdf"],
        accept_multiple_files=True,
        key="reklamation_pdf_upload",
    )
    if hochgeladen:
        neu = 0
        for datei in hochgeladen:
            kennung = (datei.name, datei.size)
            if kennung in verarbeitet:
                continue
            eintrag = werte_pdf_aus(datei.getvalue(), datei.name)
            eintraege.append(eintrag)
            verarbeitet.add(kennung)
            neu += 1
        if neu:
            speichere_eintraege(eintraege)
            st.success(f"{neu} PDF(s) ausgewertet - bitte unten pruefen.")
            st.rerun()

    with dashboard_platzhalter:
        if not eintraege:
            st.info("Noch keine Reklamations-PDFs hochgeladen.")
            return

        df = pd.DataFrame(eintraege, columns=SPALTEN)
        _render_kreisdiagramm(df)

        st.markdown("**Reklamationen (bitte pruefen/korrigieren)**")
        bearbeitet = st.data_editor(
            df,
            key="reklamation_pdf_editor",
            num_rows="dynamic",
            hide_index=True,
            height=_tabellenhoehe(len(df)),
            column_config={
                "Dateiname": st.column_config.TextColumn(disabled=True),
                "ArtNr": st.column_config.TextColumn(SPALTEN_LABEL["ArtNr"]),
            },
        )

        speicher_spalte, export_spalte = st.columns(2)
        with speicher_spalte:
            if st.button("Änderungen speichern", key="reklamation_pdf_save"):
                neue_eintraege = bearbeitet.to_dict("records")
                st.session_state["reklamation_pdf_eintraege"] = neue_eintraege
                speichere_eintraege(neue_eintraege)
                st.success("Gespeichert.")

        with export_spalte:
            export_df = bearbeitet.rename(columns=SPALTEN_LABEL)
            puffer = io.BytesIO()
            export_df.to_excel(puffer, index=False)
            puffer.seek(0)
            st.download_button(
                "📥 Als Excel herunterladen",
                data=puffer,
                file_name="Reklamationen_PDF_Auswertung.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="reklamation_pdf_export",
            )
