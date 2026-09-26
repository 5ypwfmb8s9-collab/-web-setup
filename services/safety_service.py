"""Sicherheits-Hinweise für die Tagesübersicht (einmal pro Sitzung und Tag berechnet)."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from core import clock, safety
from db import repo


def hints(user_id: int, profile: dict) -> list[str]:
    today = clock.today()
    cache_key = f"_safety_{today.isoformat()}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    out: list[str] = []
    weights = [(r["date"], r["weight_kg"]) for r in repo.list_weights(user_id, since=today - timedelta(days=35))]
    rapid = safety.rapid_loss_hint(weights)
    if rapid:
        out.append(rapid)
    totals = repo.daily_totals(user_id, today - timedelta(days=7), today - timedelta(days=1))
    low = safety.low_intake_hint({d: v["kcal"] for d, v in totals.items()})
    if low:
        out.append(low)
    st.session_state[cache_key] = out
    return out
