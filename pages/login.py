"""Anmelden & Registrieren."""

import streamlit as st

from services import auth
from ui import session, theme

theme.logo_hero("Essen tracken. Ohne Aufwand. Ohne Schuldgefühle.")

tab_login, tab_register = st.tabs(["Anmelden", "Konto erstellen"])

with tab_login:
    with st.form("login", border=False):
        email = st.text_input("E-Mail", autocomplete="email", placeholder="du@beispiel.de")
        password = st.text_input("Passwort", type="password", autocomplete="current-password")
        remember = st.checkbox("Angemeldet bleiben", value=True, help="Speichert ein Anmelde-Cookie für 30 Tage auf diesem Gerät.")
        submitted = st.form_submit_button("Anmelden", type="primary", width="stretch")
    if submitted:
        try:
            uid = auth.login(email, password)
        except auth.AuthError as exc:
            st.info(str(exc), icon=":material/lock:")
        else:
            session.sign_in(uid, remember)
            st.rerun()

with tab_register:
    with st.form("register", border=False):
        r_email = st.text_input("E-Mail", key="r_email", autocomplete="email", placeholder="du@beispiel.de")
        r_pw = st.text_input("Passwort", type="password", key="r_pw", autocomplete="new-password",
                             help="Mindestens 8 Zeichen, Buchstaben und Zahlen/Sonderzeichen.")
        r_pw2 = st.text_input("Passwort wiederholen", type="password", key="r_pw2", autocomplete="new-password")
        r_remember = st.checkbox("Angemeldet bleiben", value=True, key="r_remember")
        r_submit = st.form_submit_button("Konto erstellen", type="primary", width="stretch")
    if r_submit:
        if r_pw != r_pw2:
            st.info("Die Passwörter stimmen nicht überein.", icon=":material/info:")
        else:
            try:
                uid = auth.register(r_email, r_pw)
            except auth.AuthError as exc:
                st.info(str(exc), icon=":material/info:")
            else:
                session.sign_in(uid, r_remember)
                st.rerun()

st.html(
    '<p class="kano-small" style="text-align:center;margin-top:2rem">'
    "KANO ersetzt keine medizinische oder ernährungstherapeutische Beratung.<br>"
    "Deine Daten gehören dir – Export und vollständiges Löschen jederzeit im Profil.</p>"
)
