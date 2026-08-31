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

if not uploaded_files:
    st.info("Bitte mindestens eine Excel-Datei hochladen.")
    st.stop()

file_buffers = [io.BytesIO(f.getvalue()) for f in uploaded_files]

with st.spinner("Verarbeitung laeuft..."):
    try:
        result = generate_workbook(file_buffers)
    except ValueError as exc:
        st.error(f"Fehler beim Einlesen der Quelldateien: {exc}")
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
