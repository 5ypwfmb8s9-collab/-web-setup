"""KANO – Einstiegspunkt.

Startet mit:  streamlit run app.py

Ablauf pro Skriptlauf:
1. Seitenkonfiguration + Design-System laden
2. Anmeldung prüfen (Sitzung oder „Angemeldet bleiben“-Cookie)
3. Nicht angemeldet → Login, Onboarding offen → Onboarding, sonst → App mit Navigation unten
"""

from pathlib import Path

import streamlit as st

from core import clock
from db.engine import get_engine
from ui import components, session, theme

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="KANO",
    page_icon=str(ROOT / "static" / "kano-icon-192.png"),
    layout="centered",
    initial_sidebar_state="collapsed",
)

theme.inject_css()
theme.inject_head()
get_engine()  # legt beim ersten Start die Tabellen an

session.restore_login()
session.flush_cookie()

PAGES = {
    "heute": st.Page("pages/heute.py", title="Heute", icon=":material/today:", url_path="heute", default=True),
    "tracken": st.Page("pages/tracken.py", title="Tracken", icon=":material/add_circle:", url_path="tracken"),
    "plan": st.Page("pages/plan.py", title="Plan", icon=":material/restaurant_menu:", url_path="plan"),
    "fortschritt": st.Page("pages/fortschritt.py", title="Fortschritt", icon=":material/monitoring:", url_path="fortschritt"),
    "coach": st.Page("pages/coach.py", title="Coach", icon=":material/forum:", url_path="coach"),
    "profil": st.Page("pages/profil.py", title="Profil", icon=":material/person:", url_path="profil"),
}

if not session.user_id():
    st.navigation([st.Page("pages/login.py", title="Anmelden", default=True)], position="hidden").run()
elif not session.profile().get("onboarding_done"):
    st.navigation([st.Page("pages/onboarding.py", title="Willkommen", default=True)], position="hidden").run()
else:
    current = st.navigation(list(PAGES.values()), position="hidden")
    active = next(k for k, p in PAGES.items() if p.url_path == current.url_path)
    st.session_state["_pages"] = PAGES
    theme.top_bar(clock.format_date_long(clock.today()))
    components.bottom_nav(PAGES, active)
    current.run()
