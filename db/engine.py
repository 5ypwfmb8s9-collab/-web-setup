"""Datenbankverbindung.

Lokal: SQLite-Datei `data/kano.db`.
Produktion: `DATABASE_URL` (z. B. Supabase/PostgreSQL) in `st.secrets` oder als Umgebungsvariable.

Weil alle Zugriffe über SQLAlchemy Core laufen, ist der Wechsel nur eine Konfigurationsfrage.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from db.schema import metadata

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = f"sqlite:///{ROOT / 'data' / 'kano.db'}"

_engine: Engine | None = None


def _configured_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            import streamlit as st

            url = st.secrets.get("DATABASE_URL")  # type: ignore[assignment]
        except Exception:  # keine secrets.toml vorhanden
            url = None
    return url or DEFAULT_SQLITE


def make_engine(url: str | None = None) -> Engine:
    """Erzeugt eine Engine und legt fehlende Tabellen an."""
    url = url or _configured_url()
    if url.startswith("sqlite"):
        if ":memory:" not in url:
            Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # nötig für ON DELETE CASCADE
            cur.execute("PRAGMA journal_mode=WAL")  # parallele Lesezugriffe
            cur.close()
    else:
        # pool_pre_ping verhindert Fehler durch vom Server geschlossene Verbindungen
        engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    metadata.create_all(engine)
    return engine


def get_engine() -> Engine:
    """Prozessweit geteilte Engine (Streamlit führt Skripte in Threads desselben Prozesses aus)."""
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def set_engine(engine: Engine) -> None:
    """Für Tests: eigene (z. B. In-Memory-)Datenbank setzen."""
    global _engine
    _engine = engine
