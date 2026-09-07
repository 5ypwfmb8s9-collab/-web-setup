"""
GÜLYABANI — Streamlit-Hülle für das Browserspiel.

Das Spiel selbst ist reines HTML/JavaScript und braucht Streamlit nicht. Diese
App startet es, erklärt die Regeln und bietet zwei Wege zu spielen:

  * eingebettet auf dieser Seite,
  * in einem eigenen Browser-Tab.

Der zweite Weg existiert aus einem konkreten Grund. Streamlit rendert
Komponenten in einem iframe, dessen sandbox-Attribut `allow-pointer-lock`
nicht enthält:

    sandbox="allow-forms allow-modals allow-popups
             allow-popups-to-escape-sandbox allow-same-origin
             allow-scripts allow-downloads"

Ein Aufruf von requestPointerLock() schlägt darin lautlos fehl, die Maus wird
also nicht eingefangen. Eingebettet greift deshalb die Ersatzsteuerung des
Spiels: ziehen zum Umsehen, klicken zum Schießen. Für echte Mausteuerung
öffnet der Knopf oben rechts dasselbe Spiel in einem eigenen Tab — `allow-
popups-to-escape-sandbox` sorgt dafür, dass dieses Fenster die Sandbox
verlässt und Pointer-Lock wieder erlaubt ist.

Start:
    streamlit run gulyabani_app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
EMBED = APP_DIR / "dist" / "embed.html"
STANDALONE = APP_DIR / "dist" / "gulyabani.html"

st.set_page_config(
    page_title="GÜLYABANI",
    page_icon="🕯️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------
# Oberfläche: dieselbe Palette wie im Spiel — Messing und Knochen auf Schwarz
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
      @import url("https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700;900&family=Barlow+Condensed:wght@300;400;600&display=swap");

      .stApp { background:#07070a; color:#d9d2c4; }
      .block-container { padding:0.6rem 1.1rem 0.4rem 1.1rem; max-width:none; }
      /* The header sits on top of the component and swallows clicks along the
         whole upper edge of the game. Let events fall through it, but keep its
         own buttons (the sidebar toggle) clickable. */
      header[data-testid="stHeader"] {
        background:transparent; height:0; pointer-events:none;
      }
      header[data-testid="stHeader"] button,
      header[data-testid="stHeader"] a { pointer-events:auto; }
      div[data-testid="stToolbar"] { display:none !important; }
      #MainMenu, footer { visibility:hidden; }

      section[data-testid="stSidebar"] > div {
        background:#0a0a0e;
        border-right:1px solid rgba(201,162,39,.16);
      }
      section[data-testid="stSidebar"] * { color:#c2bbad; }

      .gy-brand {
        font-family:"Cinzel",Georgia,serif; font-weight:900;
        font-size:1.55rem; letter-spacing:.16em; color:#e6dfd0;
        text-indent:.16em; margin:0 0 .1rem 0; line-height:1;
      }
      .gy-eyebrow {
        font-family:"Barlow Condensed",system-ui,sans-serif;
        font-size:.62rem; letter-spacing:.42em; color:#7d6a2b;
        text-indent:.42em; margin-bottom:.5rem;
      }
      .gy-rule {
        height:1px; margin:.7rem 0 .9rem 0;
        background:linear-gradient(90deg,transparent,rgba(201,162,39,.55),transparent);
      }
      .gy-h {
        font-family:"Cinzel",Georgia,serif; font-size:.74rem; font-weight:700;
        letter-spacing:.26em; color:#c9a227; margin:1.1rem 0 .45rem 0;
      }
      .gy-rules { font-family:"Barlow Condensed",system-ui,sans-serif;
                  font-size:.92rem; line-height:1.55; color:#a09884; margin:0; padding:0;
                  list-style:none; }
      .gy-rules li { padding-left:.9rem; position:relative; margin-bottom:.3rem; }
      .gy-rules li::before { content:"◆"; position:absolute; left:0; top:.05rem;
                             font-size:.5rem; color:#7d6a2b; }
      .gy-rules b { color:#d9d2c4; font-weight:600; }

      .gy-keys { font-family:"Barlow Condensed",system-ui,sans-serif; font-size:.88rem; }
      .gy-keys div { display:flex; gap:.6rem; align-items:baseline; margin-bottom:.24rem; color:#9a927f; }
      .gy-keys kbd {
        font-family:inherit; font-size:.72rem; letter-spacing:.08em; color:#d9d2c4;
        border:1px solid rgba(232,226,212,.22); border-radius:3px;
        padding:.08rem .38rem; background:rgba(255,255,255,.035);
        min-width:4.6rem; text-align:center; flex:0 0 auto;
      }
      .gy-note { font-size:.76rem; line-height:1.5; color:#6f6857;
                 font-family:"Barlow Condensed",system-ui,sans-serif; }
      .gy-missing {
        border:1px solid rgba(200,65,47,.4); border-left:3px solid #c8412f;
        background:rgba(200,65,47,.07); padding:1rem 1.2rem; color:#e2b0a6;
        font-family:"Barlow Condensed",system-ui,sans-serif;
      }
      .gy-missing code { color:#f0e6cd; background:rgba(0,0,0,.4); padding:.1rem .35rem; }
      div[data-testid="stDownloadButton"] button {
        width:100%; background:rgba(201,162,39,.12); color:#f0e6cd;
        border:1px solid rgba(201,162,39,.45); border-radius:2px;
        font-family:"Barlow Condensed",system-ui,sans-serif;
        letter-spacing:.16em; font-size:.82rem;
      }
      div[data-testid="stDownloadButton"] button:hover {
        background:rgba(201,162,39,.26); border-color:#c9a227; color:#fff;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Seitenleiste
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="gy-eyebrow">ANADOLU KARANLIĞI</div>'
        '<div class="gy-brand">GÜLYABANI</div>'
        '<div class="gy-rule"></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="gy-h">REGELN</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <ul class="gy-rules">
          <li><b>Acht Patronen.</b> Mehr gibt es nicht. Kein Nachladen.</li>
          <li><b>Nur der Kopf zählt.</b> Körpertreffer gehen durch ihn hindurch.</li>
          <li><b>Jeder Kopfschuss</b> wirft ihn zurück und verlangsamt ihn dauerhaft.</li>
          <li><b>Die Lampe</b> zeigt dir den Weg und ihm dich.</li>
          <li><b>Türen</b> halten ihn kurz auf. Er bricht sie. Laut.</li>
          <li><b>Drei Muskalar</b> brechen das Siegel der Ausgangstür.</li>
        </ul>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="gy-h">STEUERUNG</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="gy-keys">
          <div><kbd>W A S D</kbd><span>Bewegen</span></div>
          <div><kbd>Maus</kbd><span>Umsehen</span></div>
          <div><kbd>Umschalt</kbd><span>Sprinten</span></div>
          <div><kbd>Strg / C</kbd><span>Ducken</span></div>
          <div><kbd>Links</kbd><span>Schießen</span></div>
          <div><kbd>Rechts</kbd><span>Kimme und Korn</span></div>
          <div><kbd>F</kbd><span>Taschenlampe</span></div>
          <div><kbd>G</kbd><span>Stein werfen</span></div>
          <div><kbd>E</kbd><span>Benutzen</span></div>
          <div><kbd>Q</kbd><span>Muska spüren</span></div>
          <div><kbd>Leertaste</kbd><span>Losreißen</span></div>
          <div><kbd>Esc</kbd><span>Pause</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="gy-h">MAUSTEUERUNG</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="gy-note">Streamlit bettet die Seite in einen iframe ein, '
        'dessen Sandbox das Einfangen der Maus nicht erlaubt. Eingebettet gilt '
        'daher: <b>ziehen zum Umsehen, klicken zum Schießen</b>. Für echte '
        'Mausteuerung den Knopf <b>Eigener Tab</b> oben rechts benutzen.</div>',
        unsafe_allow_html=True,
    )

    if STANDALONE.exists():
        st.markdown('<div class="gy-h">MITNEHMEN</div>', unsafe_allow_html=True)
        st.download_button(
            "SPIEL HERUNTERLADEN",
            data=STANDALONE.read_bytes(),
            file_name="gulyabani.html",
            mime="text/html",
            help="Eine einzige Datei. Doppelklicken und spielen, auch ohne Internet.",
        )
        size_mb = STANDALONE.stat().st_size / (1024 * 1024)
        st.markdown(
            f'<div class="gy-note">Eine Datei, {size_mb:.1f} MB, keine Installation. '
            'Alle Texturen und Geräusche werden beim Laden erzeugt, das Spiel '
            'läuft vollständig offline.</div>',
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------
# Spielfläche
# --------------------------------------------------------------------------
if not EMBED.exists():
    st.markdown(
        '<div class="gy-missing">'
        "<b>Der Spiel-Build fehlt.</b><br><br>"
        f"Erwartet wurde <code>{EMBED.relative_to(APP_DIR)}</code>. "
        "Einmal bauen mit:<br><br><code>node build.js</code><br><br>"
        "Danach diese Seite neu laden."
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

GAME_HTML = EMBED.read_text(encoding="utf-8")

# Der Wrapper läuft im selben Dokument wie das Spiel. Er tut zwei Dinge:
# den iframe auf die Fensterhöhe ziehen und einen Ausbruch in einen eigenen
# Tab anbieten, wo Pointer-Lock wieder funktioniert.
HOST_SCRIPT = """
<style>
  #gy-tab{
    position:fixed;top:9px;left:50%;transform:translateX(-50%);z-index:300;
    font-family:"Barlow Condensed",system-ui,sans-serif;
    font-size:11px;letter-spacing:.2em;color:#e8dcb8;
    background:rgba(10,10,14,.82);border:1px solid rgba(201,162,39,.45);
    padding:7px 13px;cursor:pointer;border-radius:2px;
    transition:background .16s,border-color .16s;
  }
  #gy-tab:hover{background:rgba(201,162,39,.24);border-color:#c9a227}
  #gy-tab:focus-visible{outline:2px solid #c9a227;outline-offset:2px}
</style>
<script>
(function () {
  var inFrame = window.self !== window.top;

  /* --- stretch the component frame to the height of the browser window --- */
  function fit() {
    try {
      var fe = window.frameElement;
      if (!fe) return;
      var vh = window.parent.innerHeight || 800;
      var top = fe.getBoundingClientRect().top;
      var h = Math.max(420, Math.floor(vh - top - 14));
      if (fe.style.height !== h + 'px') {
        fe.style.height = h + 'px';
        var box = fe.parentElement;
        if (box) box.style.height = h + 'px';
        window.dispatchEvent(new Event('resize'));
      }
    } catch (e) { /* cross-origin host: keep the fixed height */ }
  }

  if (inFrame) {
    fit();
    window.addEventListener('resize', fit);
    try { window.parent.addEventListener('resize', fit); } catch (e) {}
    setTimeout(fit, 250);
    setTimeout(fit, 1000);
    setTimeout(fit, 2500);
  }

  /* --- escape hatch: a top-level window, where the mouse can be captured --- */
  if (inFrame) {
    var btn = document.createElement('button');
    btn.id = 'gy-tab';
    btn.type = 'button';
    btn.textContent = 'EIGENER TAB · ECHTE MAUS';
    btn.title = 'Öffnet dasselbe Spiel in einem eigenen Fenster, in dem der ' +
                'Browser die Maus einfangen darf.';
    btn.addEventListener('click', function () {
      // The frame's srcdoc still holds the pristine page, before the running
      // game mutated the DOM. Wrap it in a real document so the new window
      // parses in standards mode, then hand it over as a blob: navigation —
      // document.write() of ~900 KB stalls the parser for seconds.
      var src = null;
      try { src = window.frameElement.getAttribute('srcdoc'); } catch (e) {}
      if (!src) { btn.textContent = 'NICHT MÖGLICH'; return; }
      var doc = '<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">' +
        '<meta name="viewport" content="width=device-width, initial-scale=1, ' +
        'maximum-scale=1, user-scalable=no, viewport-fit=cover">' +
        '<title>GÜLYABANI</title></head><body>' + src + '</body></html>';
      var url;
      try {
        url = URL.createObjectURL(new Blob([doc], { type: 'text/html' }));
      } catch (e) { btn.textContent = 'NICHT MÖGLICH'; return; }
      var w = window.open(url, '_blank');
      if (!w) { btn.textContent = 'POPUP ERLAUBEN'; return; }
      btn.textContent = 'IM EIGENEN TAB GEÖFFNET';
      setTimeout(function () { URL.revokeObjectURL(url); }, 120000);
    });
    document.body.appendChild(btn);
  }
})();
</script>
"""

components.html(GAME_HTML + HOST_SCRIPT, height=760, scrolling=False)
