"""VW AI - Streamlit-Oberflaeche.

Hauptseite (Start) + Reiter fuer die einzelnen Werkzeuge: "Ladelisten"
(automatische Verarbeitung von Excel-Ladelisten), "Reklamationen"
(Ausfallfracht-Dashboard mit lokaler Drag-&-Drop-Erfassung) und
"Referenz" (Nachschlage-Liste der SLB-Referenznummern).
"""

import io
import os
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ladeliste_logic import generate_workbook
from reklamation_logic import STATUS_OPTIONS
from reklamation_lokal import (
    ERGEBNIS_OPTIONEN,
    EXCEL_COLUMNS,
    ZUGEWIESEN_OPTIONEN,
    erstelle_fallordner,
    excel_pfad,
    extrahiere_abholtag,
    extrahiere_beleg_und_datum,
    extrahiere_betrag,
    extrahiere_firma,
    extrahiere_referenznummern,
    guess_absender_betreff,
    guess_eingangsdatum,
    lade_excel,
    lade_gespeicherten_archivordner,
    lade_gespeicherten_basisordner,
    sicherer_pdf_dateiname,
    speichere_archivordner,
    speichere_basisordner,
    speichere_excel,
    speichere_pdf,
)

st.set_page_config(page_title="VW AI", page_icon="✨", layout="wide")

# ---------------------------------------------------------------------------
# Globales Styling: dunkler Hintergrund + Copilot-Gradient-Schimmer auf
# Buttons/Akzenten (Lila/Blau/Pink), schlicht gehalten.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @keyframes copilot-shimmer {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    .stButton > button,
    .stDownloadButton > button,
    [data-testid^="stBaseButton"] {
        border-radius: 10px !important;
        border: 2px solid transparent !important;
        background:
            linear-gradient(#121218, #121218) padding-box,
            linear-gradient(90deg, #8B5CF6, #3B82F6, #EC4899, #8B5CF6) border-box !important;
        background-size: 300% 300% !important;
        animation: copilot-shimmer 6s ease infinite;
        color: #f2f2f5 !important;
        font-weight: 600 !important;
        transition: filter 0.15s ease;
    }
    .stButton > button:hover,
    .stDownloadButton > button:hover,
    [data-testid^="stBaseButton"]:hover {
        filter: brightness(1.25);
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
    }

    .vwai-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #f2f2f5;
        background: linear-gradient(90deg, #8B5CF6, #3B82F6, #EC4899, #8B5CF6);
        background-size: 300% 300%;
        animation: copilot-shimmer 6s ease infinite;
        margin-left: 8px;
        vertical-align: middle;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

HERO_HTML = """
<div style="position:relative;width:100%;height:420px;background:#000;
            border-radius:18px;overflow:hidden;font-family:sans-serif;">
  <canvas id="vwai-particles" style="position:absolute;inset:0;width:100%;height:100%;"></canvas>
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;text-align:center;">
    <div style="font-size:68px;font-weight:800;letter-spacing:2px;
                background:linear-gradient(90deg,#8B5CF6,#3B82F6,#EC4899,#8B5CF6);
                background-size:300% 300%;
                animation:hero-shimmer 6s ease infinite;
                -webkit-background-clip:text;background-clip:text;color:transparent;">
      VW AI
    </div>
    <div style="color:#9a9aa5;margin-top:10px;font-size:16px;">
      Intelligente Werkzeuge fuer Logistik &amp; Qualitaet
    </div>
  </div>
</div>
<style>
  @keyframes hero-shimmer {
      0%   { background-position: 0% 50%; }
      50%  { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
  }
</style>
<script>
  const canvas = document.getElementById('vwai-particles');
  const ctx = canvas.getContext('2d');

  function resize() {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const N = 70;
  const pts = Array.from({length: N}, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
  }));

  function tick() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const p of pts) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
          if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
      }

      for (let i = 0; i < N; i++) {
          for (let j = i + 1; j < N; j++) {
              const dx = pts[i].x - pts[j].x;
              const dy = pts[i].y - pts[j].y;
              const d = Math.sqrt(dx * dx + dy * dy);
              if (d < 110) {
                  ctx.strokeStyle = `rgba(150,150,190,${1 - d / 110})`;
                  ctx.lineWidth = 1;
                  ctx.beginPath();
                  ctx.moveTo(pts[i].x, pts[i].y);
                  ctx.lineTo(pts[j].x, pts[j].y);
                  ctx.stroke();
              }
          }
      }

      for (const p of pts) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(225,225,255,0.9)';
          ctx.fill();
      }

      requestAnimationFrame(tick);
  }
  tick();
</script>
"""


def render_start_tab() -> None:
    components.html(HERO_HTML, height=440, scrolling=False)
    st.markdown(
        "<p style='text-align:center;color:#8a8a95;'>"
        "Waehle oben einen Reiter, um ein Werkzeug zu starten."
        "</p>",
        unsafe_allow_html=True,
    )


def render_ladelisten_tab() -> None:
    st.title("Ladelisten")
    st.write(
        "Lade eine oder mehrere Excel-Dateien mit dem Blatt "
        "**\"Avis Lade Listen\"** hoch. Die Verarbeitung startet automatisch."
    )

    uploaded_files = st.file_uploader(
        "Excel-Quelldateien",
        type=["xlsx"],
        accept_multiple_files=True,
        key="ladelisten_avis_files",
    )

    uploaded_planung = st.file_uploader(
        "Planungsdatei (optional) - fuellt \"Planung für Staplerfahrer\" und erstellt ein Abweichungen-Blatt",
        type=["xlsx"],
        accept_multiple_files=False,
        key="ladelisten_planung_file",
    )

    if not uploaded_files:
        st.info("Bitte mindestens eine Excel-Datei hochladen.")
        return

    file_buffers = [io.BytesIO(f.getvalue()) for f in uploaded_files]
    planung_buffer = io.BytesIO(uploaded_planung.getvalue()) if uploaded_planung else None

    with st.spinner("Verarbeitung laeuft..."):
        try:
            result = generate_workbook(file_buffers, planung_file=planung_buffer)
        except ValueError as exc:
            st.error(f"Fehler beim Einlesen der Dateien: {exc}")
            return

    st.subheader("Zusammenfassung je LKW-Blatt")
    st.table(
        [
            {
                "Blatt": s.sheet_name,
                "Positionen": s.position_count,
                "Gesamtgewicht": round(s.gesamtgewicht, 1),
                "Menge 111444": s.total_111444,
                "Menge VWPAL": s.total_vwpal,
            }
            for s in result.summaries
        ]
    )

    if result.planung is not None:
        st.subheader("Planungsabgleich")
        p = result.planung
        st.write(
            f"{p.positions_gefuellt} Positionen mit LKW befuellt, "
            f"{p.positions_ignoriert} Abladestellen ignoriert (nie in Avis-Listen), "
            f"{p.positions_ohne_treffer} ohne Treffer in den Avis-Daten."
        )
        if p.abweichungen:
            st.warning(f"{len(p.abweichungen)} Abweichung(en) gefunden.")
            st.table(
                [
                    {
                        "Abladestelle": a.abladestelle,
                        "Erwartet VWPAL": a.erwartet_vwpal,
                        "Erwartet 111444": a.erwartet_111444,
                        "Tatsaechlich VWPAL": a.tatsaechlich_vwpal,
                        "Tatsaechlich 111444": a.tatsaechlich_111444,
                        "Abweichung": a.beschreibung,
                    }
                    for a in p.abweichungen
                ]
            )
        else:
            st.success("Keine Abweichungen zwischen Planung und Avis-Daten gefunden.")

    st.subheader("Validierung")
    failed = [v for v in result.validation if not v.passed]
    for v in result.validation:
        if v.passed:
            st.success(f"{v.check}: {v.message}")
        else:
            st.error(f"{v.check}: {v.message}")

    if failed:
        st.error(
            f"{len(failed)} Validierung(en) fehlgeschlagen. "
            "Die Ausgabedatei wird nicht zum Download angeboten."
        )
        return

    output_buffer = io.BytesIO()
    result.workbook.save(output_buffer)
    output_buffer.seek(0)

    filename = f"Ladelisten_{date.today().isoformat()}.xlsx"

    st.success("Verarbeitung abgeschlossen. Alle Validierungen erfolgreich.")
    st.download_button(
        label="Ausgabedatei herunterladen",
        data=output_buffer,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="ladelisten_download",
    )


def render_reklamationen_tab() -> None:
    st.title("Reklamationen")
    st.markdown(
        '<span class="vwai-badge">✨ Ausfallfracht-Dashboard</span>',
        unsafe_allow_html=True,
    )

    with st.expander("Ordner-Einstellungen"):
        basisordner = st.text_input(
            "Basisordner (mit SharePoint/OneDrive synchronisiert)",
            value=st.session_state.get(
                "reklamationen_basisordner", lade_gespeicherten_basisordner()
            ),
            key="reklamationen_basisordner_input",
        )
        if st.button("Ordner merken", key="reklamationen_basisordner_speichern"):
            speichere_basisordner(basisordner)
            st.session_state["reklamationen_basisordner"] = basisordner
            st.success("Ordner gemerkt - wird beim naechsten Start automatisch vorausgefuellt.")

        archivordner = st.text_input(
            "Archiv-Basisordner (Planung/Ladeliste/Avisierung, Jahr wird automatisch ergaenzt)",
            value=st.session_state.get(
                "reklamationen_archivordner", lade_gespeicherten_archivordner()
            ),
            key="reklamationen_archivordner_input",
        )
        if st.button("Archivordner merken", key="reklamationen_archivordner_speichern"):
            speichere_archivordner(archivordner)
            st.session_state["reklamationen_archivordner"] = archivordner
            st.success("Archivordner gemerkt.")

    if not basisordner:
        st.info("Bitte oben einen Basisordner angeben.")
        return

    pfad = excel_pfad(basisordner)

    if st.session_state.get("reklamationen_geladener_ordner") != basisordner:
        try:
            geladene_rows = lade_excel(pfad)
        except PermissionError:
            st.error(
                f"`{os.path.basename(pfad)}` ist gerade geoeffnet (z.B. in Excel) "
                "und kann nicht gelesen werden. Datei schliessen und die Seite "
                "neu laden."
            )
            return
        st.session_state["reklamationen_rows"] = geladene_rows
        st.session_state["reklamationen_verarbeitete_uploads"] = set()
        st.session_state["reklamationen_geladener_ordner"] = basisordner

    # Platzhalter fuer das Dashboard (Kennzahlen + Tabelle) - soll ueber
    # dem Upload-Bereich erscheinen, wird aber erst weiter unten befuellt,
    # nachdem neu hochgeladene PDFs verarbeitet wurden.
    dashboard_platzhalter = st.container()

    st.write(
        "Ausfallfracht-/Storno-PDFs (Duvenbeck) hier per Drag & Drop hochladen. "
        "PDF und Angaben werden automatisch im Basisordner erfasst."
    )
    uploaded_pdfs = st.file_uploader(
        "PDFs hochladen (Ausfallfracht-Rechnungen oder Storno)",
        type=["pdf"],
        accept_multiple_files=True,
        key="reklamationen_pdf_upload",
    )

    if uploaded_pdfs:
        neu_erfasst = 0
        nicht_erkannt = []
        fall_meldungen = []
        for f in uploaded_pdfs:
            kennung = (f.name, f.size)
            if kennung in st.session_state["reklamationen_verarbeitete_uploads"]:
                continue

            inhalt = f.getvalue()
            beleg_nr, pdf_datum = extrahiere_beleg_und_datum(inhalt)
            neuer_dateiname = sicherer_pdf_dateiname(beleg_nr, f.name)

            gespeicherter_pfad = speichere_pdf(basisordner, neuer_dateiname, inhalt)
            eintrag = {
                "Eingangsdatum": pdf_datum or guess_eingangsdatum(f.name),
                "Abholtag": extrahiere_abholtag(inhalt) or "",
                "Firma": extrahiere_firma(inhalt) or "",
                "Dateiname_PDF": os.path.basename(gespeicherter_pfad),
                "OneDrive_Pfad": gespeicherter_pfad,
                "Betrag": extrahiere_betrag(inhalt) or "",
                "Zugewiesen": "",
                "Status": "Offen",
                "Prüfdatum": "",
                "Ergebnis": "",
                "Bemerkung": "",
                "Referenznummern": ";".join(extrahiere_referenznummern(inhalt)),
            }
            eintrag.update(guess_absender_betreff(f.name))
            st.session_state["reklamationen_rows"].append(eintrag)
            st.session_state["reklamationen_verarbeitete_uploads"].add(kennung)
            neu_erfasst += 1
            if beleg_nr is None:
                nicht_erkannt.append(f.name)

            abholtag = eintrag["Abholtag"]
            if beleg_nr and abholtag and archivordner:
                fallordner, fehlend = erstelle_fallordner(
                    archivordner, basisordner, beleg_nr, abholtag, gespeicherter_pfad
                )
                if fehlend:
                    fall_meldungen.append(
                        f"{f.name}: Fall-Ordner erstellt, aber nicht gefunden: "
                        + ", ".join(fehlend)
                    )
                else:
                    fall_meldungen.append(
                        f"{f.name}: alle Dateien in Fall-{beleg_nr} zusammengefasst."
                    )

        if neu_erfasst:
            try:
                speichere_excel(pfad, st.session_state["reklamationen_rows"])
                st.success(f"{neu_erfasst} PDF(s) gespeichert und erfasst.")
            except PermissionError:
                st.error(
                    f"`{os.path.basename(pfad)}` ist gerade geoeffnet (z.B. in "
                    "Excel) und konnte nicht aktualisiert werden. Die PDFs "
                    "wurden trotzdem gespeichert - Datei schliessen und "
                    "'Aenderungen speichern' unten klicken, um die Excel-Datei "
                    "nachzuziehen."
                )
        if nicht_erkannt:
            st.warning(
                "Beleg-Nr./Datum konnten nicht automatisch erkannt werden bei: "
                + ", ".join(nicht_erkannt)
                + ". Bitte Eingangsdatum und Dateiname unten von Hand pruefen."
            )
        for meldung in fall_meldungen:
            st.info(meldung)

    rows = st.session_state["reklamationen_rows"]
    with dashboard_platzhalter:
        if not rows:
            st.info("Noch keine Reklamationen erfasst. Unten PDFs hochladen.")
            return

        df = pd.DataFrame(rows, columns=EXCEL_COLUMNS)

        status_counts = df["Status"].value_counts()
        ergebnis_counts = df["Ergebnis"].value_counts()
        kennzahlen = [(s, int(status_counts.get(s, 0))) for s in STATUS_OPTIONS]
        kennzahlen += [
            ("Berechtigt", int(ergebnis_counts.get("Berechtigt", 0))),
            ("Unberechtigt", int(ergebnis_counts.get("Unberechtigt", 0))),
        ]
        cols = st.columns(len(kennzahlen))
        for col, (label, wert) in zip(cols, kennzahlen):
            col.metric(label, wert)

        edited_df = st.data_editor(
            df,
            key="reklamationen_editor",
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "Dateiname_PDF": st.column_config.TextColumn(disabled=True),
                "OneDrive_Pfad": st.column_config.TextColumn(disabled=True),
                "Referenznummern": st.column_config.TextColumn(disabled=True),
                "Zugewiesen": st.column_config.SelectboxColumn(
                    "Zugewiesen", options=ZUGEWIESEN_OPTIONEN
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=STATUS_OPTIONS, required=True
                ),
                "Ergebnis": st.column_config.SelectboxColumn(
                    "Ergebnis", options=ERGEBNIS_OPTIONEN
                ),
            },
        )

        if st.button("Änderungen speichern", key="reklamationen_save"):
            neue_rows = edited_df.to_dict("records")
            st.session_state["reklamationen_rows"] = neue_rows
            try:
                speichere_excel(pfad, neue_rows)
                st.success("Gespeichert.")
            except PermissionError:
                st.error(
                    f"`{os.path.basename(pfad)}` ist gerade geoeffnet (z.B. in "
                    "Excel) und kann nicht gespeichert werden. Datei schliessen "
                    "und nochmal auf 'Aenderungen speichern' klicken - deine "
                    "Aenderungen sind bis dahin nicht verloren."
                )


def render_referenz_tab() -> None:
    st.title("Referenz")
    st.write(
        "Nachschlage-Liste aller SLB-Referenznummern aus den im Reiter "
        "Reklamationen erfassten Rechnungen."
    )

    rows = st.session_state.get("reklamationen_rows", [])
    eintraege = []
    for row in rows:
        nummern = [n for n in (row.get("Referenznummern") or "").split(";") if n]
        for nummer in nummern:
            eintraege.append(
                {
                    "Referenznummer": nummer,
                    "Beleg-Nr": os.path.splitext(row.get("Dateiname_PDF") or "")[0],
                    "Firma": row.get("Firma") or "",
                    "Betreff": row.get("Betreff") or "",
                    "Eingangsdatum": row.get("Eingangsdatum") or "",
                }
            )

    if not eintraege:
        st.info(
            "Noch keine Referenznummern erfasst - werden automatisch aus "
            "hochgeladenen Rechnungen im Reiter Reklamationen uebernommen."
        )
        return

    df = pd.DataFrame(eintraege)
    suche = st.text_input("Suche nach Referenznummer", key="referenz_suche")
    if suche:
        df = df[df["Referenznummer"].str.contains(suche, case=False, na=False)]

    st.dataframe(df, hide_index=True, use_container_width=True)


tab_start, tab_ladelisten, tab_reklamationen, tab_referenz = st.tabs(
    ["Start", "Ladelisten", "Reklamationen", "Referenz"]
)

with tab_start:
    render_start_tab()

with tab_ladelisten:
    render_ladelisten_tab()

with tab_reklamationen:
    render_reklamationen_tab()

with tab_referenz:
    render_referenz_tab()
