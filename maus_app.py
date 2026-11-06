"""
Maus-Makro als Streamlit-App.

Start:  streamlit run maus_app.py
(oder einfach start_windows.bat / start_mac_linux.sh doppelklicken)

WICHTIG: Die App steuert die Maus des Computers, auf dem sie läuft.
Sie muss also lokal auf deinem PC laufen, nicht auf einem Server.

NOTAUS: Maus in die linke obere Bildschirmecke schieben.
"""

import json
import time
from pathlib import Path

import streamlit as st

try:
    import pyautogui
except Exception as e:  # z.B. kein Bildschirm vorhanden
    st.error(f"pyautogui konnte nicht geladen werden: {e}")
    st.stop()

pyautogui.FAILSAFE = True
MAKRO_ORDNER = Path(__file__).parent / "makros"
MAKRO_ORDNER.mkdir(exist_ok=True)

AKTIONEN = ["linksklick", "rechtsklick", "doppelklick", "bewegen", "warten"]

st.set_page_config(page_title="Maus-Makro", page_icon="🖱️")
st.title("🖱️ Maus-Makro")
st.caption("Notaus: Maus schnell in die **linke obere Bildschirmecke** schieben.")

if "schritte" not in st.session_state:
    st.session_state.schritte = []
schritte = st.session_state.schritte

# ---------------------------------------------------------------- Aufnehmen
st.header("1. Schritte aufnehmen")
spalte1, spalte2 = st.columns(2)
aktion = spalte1.selectbox("Aktion", AKTIONEN)
countdown = spalte2.number_input("Countdown (Sek.)", 1, 30, 3,
                                 help="Zeit, um die Maus an die Zielstelle zu bewegen")

if aktion == "warten":
    sek = st.number_input("Wartezeit (Sek.)", 0.1, 3600.0, 1.0, step=0.5)
    if st.button("➕ Pause hinzufügen"):
        schritte.append({"aktion": "warten", "sekunden": sek})
        st.rerun()
else:
    if st.button(f"🎯 Position aufnehmen (in {countdown} Sek.)", type="primary"):
        anzeige = st.empty()
        for i in range(countdown, 0, -1):
            anzeige.warning(f"Maus jetzt an die Zielstelle bewegen … {i}")
            time.sleep(1)
        x, y = pyautogui.position()
        schritte.append({"aktion": aktion, "x": int(x), "y": int(y)})
        anzeige.success(f"{aktion} bei ({x}, {y}) gespeichert")
        time.sleep(0.8)
        st.rerun()

    with st.expander("Position manuell eingeben"):
        mx = st.number_input("X", 0, 10000, 0)
        my = st.number_input("Y", 0, 10000, 0)
        if st.button("➕ Hinzufügen"):
            schritte.append({"aktion": aktion, "x": int(mx), "y": int(my)})
            st.rerun()

# ---------------------------------------------------------------- Liste
st.header("2. Ablauf")
if not schritte:
    st.info("Noch keine Schritte aufgenommen.")
for i, s in enumerate(schritte):
    c1, c2, c3, c4 = st.columns([6, 1, 1, 1])
    text = (f"⏱️ warten {s['sekunden']} s" if s["aktion"] == "warten"
            else f"{s['aktion']} bei ({s['x']}, {s['y']})")
    c1.write(f"**{i + 1}.** {text}")
    if c2.button("⬆️", key=f"hoch{i}", disabled=i == 0):
        schritte[i - 1], schritte[i] = schritte[i], schritte[i - 1]
        st.rerun()
    if c3.button("⬇️", key=f"runter{i}", disabled=i == len(schritte) - 1):
        schritte[i + 1], schritte[i] = schritte[i], schritte[i + 1]
        st.rerun()
    if c4.button("🗑️", key=f"weg{i}"):
        schritte.pop(i)
        st.rerun()

if schritte and st.button("Alle löschen"):
    schritte.clear()
    st.rerun()

# ---------------------------------------------------------------- Speichern / Laden
with st.expander("💾 Speichern / Laden"):
    name = st.text_input("Name", "makro")
    a, b = st.columns(2)
    if a.button("Speichern", disabled=not schritte):
        (MAKRO_ORDNER / f"{name}.json").write_text(
            json.dumps(schritte, indent=2, ensure_ascii=False), encoding="utf-8")
        st.success(f"Gespeichert als makros/{name}.json")
    vorhanden = sorted(p.stem for p in MAKRO_ORDNER.glob("*.json"))
    if vorhanden:
        wahl = b.selectbox("Gespeicherte Makros", vorhanden)
        if b.button("Laden"):
            st.session_state.schritte = json.loads(
                (MAKRO_ORDNER / f"{wahl}.json").read_text(encoding="utf-8"))
            st.rerun()

# ---------------------------------------------------------------- Abspielen
st.header("3. Abspielen")
c1, c2 = st.columns(2)
runden = c1.number_input("Wiederholungen (0 = endlos)", 0, 100000, 1)
start = c2.number_input("Startverzögerung (Sek.)", 0, 60, 3)
c3, c4 = st.columns(2)
dauer = c3.slider("Dauer je Mausbewegung (Sek.)", 0.0, 2.0, 0.3, 0.05)
pause = c4.slider("Pause nach jedem Schritt (Sek.)", 0.0, 5.0, 0.5, 0.1)

if st.button("▶️ Start", type="primary", disabled=not schritte):
    status = st.empty()
    for i in range(start, 0, -1):
        status.warning(f"Start in {i} … (Notaus: Maus in Ecke oben links)")
        time.sleep(1)
    runde = 0
    try:
        while runden == 0 or runde < runden:
            runde += 1
            status.info(f"Durchlauf {runde}/{'∞' if runden == 0 else runden} läuft …")
            for s in schritte:
                if s["aktion"] == "warten":
                    time.sleep(s["sekunden"])
                    continue
                pyautogui.moveTo(s["x"], s["y"], duration=dauer)
                if s["aktion"] == "linksklick":
                    pyautogui.click()
                elif s["aktion"] == "rechtsklick":
                    pyautogui.rightClick()
                elif s["aktion"] == "doppelklick":
                    pyautogui.doubleClick()
                time.sleep(pause)
        status.success(f"Fertig – {runde} Durchläufe.")
    except pyautogui.FailSafeException:
        status.error(f"Notaus ausgelöst in Durchlauf {runde}.")
