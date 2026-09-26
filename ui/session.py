"""Sitzungszustand: angemeldeter Nutzer, Profil, An-/Abmelden."""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import clock
from db import repo
from services import auth
from ui import theme

COOKIE = "kano_auth"


def restore_login() -> None:
    """Stellt eine Anmeldung aus dem „Angemeldet bleiben“-Cookie wieder her."""
    if st.session_state.get("user_id") or st.session_state.get("logged_out"):
        return
    try:
        token = st.context.cookies.get(COOKIE)
    except Exception:
        token = None
    uid = auth.user_for_token(token)
    if uid and repo.get_user(uid):
        st.session_state.user_id = uid
        st.session_state.auth_token = token


def sign_in(user_id: int, remember: bool) -> None:
    st.session_state.user_id = user_id
    st.session_state.pop("logged_out", None)
    st.session_state.pop("_profile", None)
    if remember:
        issued = auth.issue_token(user_id)
        st.session_state.auth_token = issued.token
        # Cookie wird beim nächsten Lauf gesetzt (nach dem Rerun, der die Seite wechselt)
        st.session_state.pending_cookie = (issued.token, issued.max_age_seconds)


def flush_cookie() -> None:
    """Setzt bzw. löscht Cookies, die im vorherigen Lauf angefordert wurden."""
    pending = st.session_state.pop("pending_cookie", None)
    if pending:
        theme.set_cookie(COOKIE, pending[0], pending[1])
    if st.session_state.pop("pending_cookie_delete", False):
        theme.delete_cookie(COOKIE)


def sign_out() -> None:
    auth.revoke_token(st.session_state.get("auth_token"))
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.logged_out = True
    st.session_state.pending_cookie_delete = True


def user_id() -> int | None:
    return st.session_state.get("user_id")


def uid() -> int:
    """User-ID für Seiten, die nur angemeldet erreichbar sind."""
    value = st.session_state.get("user_id")
    if value is None:
        st.stop()
    return value


def profile() -> dict:
    """Profil des angemeldeten Nutzers (pro Sitzung gecacht, nach Änderungen `refresh_profile`)."""
    cached = st.session_state.get("_profile")
    if cached is None:
        cached = repo.get_profile(uid()) or {}
        st.session_state["_profile"] = cached
    return cached


def refresh_profile() -> None:
    st.session_state.pop("_profile", None)


def update_profile(**fields) -> None:
    repo.update_profile(uid(), **fields)
    refresh_profile()


def user_row() -> dict:
    return repo.get_user(uid()) or {}


def age(p: dict | None = None, on: date | None = None) -> int:
    p = p or profile()
    by = p.get("birth_year") or 1990
    return (on or clock.today()).year - by


def current_weight(p: dict | None = None) -> float | None:
    row = repo.latest_weight(uid())
    return row["weight_kg"] if row else None


def hide_numbers() -> bool:
    return bool(profile().get("hide_numbers"))


def approx_mode() -> bool:
    return bool(profile().get("approx_mode"))


def ai_allowed() -> bool:
    return bool(profile().get("ai_consent"))
