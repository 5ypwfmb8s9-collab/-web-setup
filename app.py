"""Streamlit-Oberflaeche fuer das Ladelisten-Tool.

Datei(en) hochladen -> Verarbeitung laeuft automatisch -> Download der
fertigen Ausgabedatei.
"""

import io
from datetime import date

import streamlit as st

from ladeliste_logic import generate_workbook

st.set_page_config(page_title="Ladelisten-Tool", layout="wide")

st.title("Ladelisten-Tool")
st.write(
    "Lade eine oder mehrere Excel-Dateien mit dem Blatt "
    "**\"Avis Lade Listen\"** hoch. Die Verarbeitung startet automatisch."
)

uploaded_files = st.file_uploader(
    "Excel-Quelldateien",
    type=["xlsx"],
    accept_multiple_files=True,
)

uploaded_planung = st.file_uploader(
    "Planungsdatei (optional) - fuellt \"Planung für Staplerfahrer\" und erstellt ein Abweichungen-Blatt",
    type=["xlsx"],
    accept_multiple_files=False,
)

if not uploaded_files:
    st.info("Bitte mindestens eine Excel-Datei hochladen.")
    st.stop()

file_buffers = [io.BytesIO(f.getvalue()) for f in uploaded_files]
planung_buffer = io.BytesIO(uploaded_planung.getvalue()) if uploaded_planung else None

with st.spinner("Verarbeitung laeuft..."):
    try:
        result = generate_workbook(file_buffers, planung_file=planung_buffer)
    except ValueError as exc:
        st.error(f"Fehler beim Einlesen der Dateien: {exc}")
        st.stop()

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
    st.stop()

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
)
