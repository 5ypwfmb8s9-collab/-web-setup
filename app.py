"""VW AI - Streamlit-Oberflaeche.

Hauptseite (Start) + Reiter fuer die einzelnen Werkzeuge. "Ladelisten" ist
das erste Werkzeug (automatische Verarbeitung von Excel-Ladelisten),
"Reklamationen" folgt als naechstes.
"""

import io
from datetime import date

import streamlit as st
import streamlit.components.v1 as components

from ladeliste_logic import generate_workbook

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
        '<span class="vwai-badge">✨ In Vorbereitung</span>',
        unsafe_allow_html=True,
    )
    st.info("Diese Funktion folgt als Naechstes.")


tab_start, tab_ladelisten, tab_reklamationen = st.tabs(
    ["✨ Start", "📦 Ladelisten", "📋 Reklamationen"]
)

with tab_start:
    render_start_tab()

with tab_ladelisten:
    render_ladelisten_tab()

with tab_reklamationen:
    render_reklamationen_tab()
