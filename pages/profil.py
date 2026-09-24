"""Profil & Einstellungen (Phase 1: Abmelden)."""

import streamlit as st

from ui import session, theme

theme.page_title("Profil")
if st.button("Abmelden", width="stretch"):
    session.sign_out()
    st.rerun()
