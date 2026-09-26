"""KANO – Einstiegspunkt.

Startet mit:  streamlit run app.py

Ablauf pro Skriptlauf:
1. Seitenkonfiguration + Design-System laden
2. Anmeldung prüfen (Sitzung oder „Angemeldet bleiben“-Cookie)
3. Nicht angemeldet → Login, Onboarding offen → Onboarding, sonst → App mit Navigation unten
"""

import logging
from pathlib import Path

import streamlit as st
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException

from core import clock
from db.engine import get_engine
from ui import components, session, theme

log = logging.getLogger("kano")

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="KANO",
    page_icon=str(ROOT / "static" / "kano-icon-192.png"),
    layout="centered",
    initial_sidebar_state="collapsed",
)

theme.inject_css()
theme.inject_head()


def friendly_error(exc: Exception) -> None:
    """Fehler abfangen, verständlich erklären – die App bleibt bedienbar (kein roter Stacktrace)."""
    if isinstance(exc, ScriptControlException):  # st.rerun()/st.stop() sind keine Fehler
        raise exc
    log.exception("Unerwarteter Fehler", exc_info=exc)
    if isinstance(exc, OperationalError):
        msg = "Die Datenbank ist gerade nicht erreichbar. Deine Daten sind sicher – bitte versuch es gleich noch einmal."
    elif isinstance(exc, SQLAlchemyError):
        msg = "Beim Speichern oder Laden ist etwas schiefgelaufen. Bitte versuch es noch einmal."
    else:
        msg = "Hier ist etwas schiefgelaufen. Lade die Seite neu – wenn es wieder passiert, hilft uns ein kurzer Hinweis."
    st.html(f'<div class="kano-note care">{msg}</div>')
    if st.button("Neu laden", icon=":material/refresh:", width="stretch"):
        st.rerun()


try:
    get_engine()  # legt beim ersten Start die Tabellen an
    session.restore_login()
except Exception as exc:  # noqa: BLE001
    friendly_error(exc)
    st.stop()
session.flush_cookie()

PAGES = {
    "heute": st.Page("pages/heute.py", title="Heute", icon=":material/today:", url_path="heute", default=True),
    "tracken": st.Page("pages/tracken.py", title="Tracken", icon=":material/add_circle:", url_path="tracken"),
    "plan": st.Page("pages/plan.py", title="Plan", icon=":material/restaurant_menu:", url_path="plan"),
    "fortschritt": st.Page("pages/fortschritt.py", title="Fortschritt", icon=":material/monitoring:", url_path="fortschritt"),
    "coach": st.Page("pages/coach.py", title="Coach", icon=":material/forum:", url_path="coach"),
    "profil": st.Page("pages/profil.py", title="Profil", icon=":material/person:", url_path="profil"),
}


def route() -> None:
    if not session.user_id():
        st.navigation([st.Page("pages/login.py", title="Anmelden", default=True)], position="hidden").run()
        return
    if not session.profile().get("onboarding_done"):
        st.navigation([st.Page("pages/onboarding.py", title="Willkommen", default=True)], position="hidden").run()
        return
    current = st.navigation(list(PAGES.values()), position="hidden")
    active = next(k for k, p in PAGES.items() if p.url_path == current.url_path)
    st.session_state["_pages"] = PAGES
    theme.top_bar(clock.format_date_long(clock.today()))
    components.bottom_nav(PAGES, active)
    current.run()


try:
    route()
except Exception as exc:  # noqa: BLE001
    friendly_error(exc)
