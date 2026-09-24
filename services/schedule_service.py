"""Schichten aus Profil (Wochenmuster) und Einzeltagen zusammenführen."""

from __future__ import annotations

from datetime import date, time, timedelta

from core import schedule
from db import repo


def shift_on(user_id: int, profile: dict, day: date) -> str:
    overrides = repo.get_shifts(user_id, day, day)
    return schedule.shift_for_day(day.weekday(), profile.get("shift_pattern"), overrides, day)


def shifts_between(user_id: int, profile: dict, start: date, days: int) -> dict[date, str]:
    end = start + timedelta(days=days - 1)
    overrides = repo.get_shifts(user_id, start, end)
    return {
        start + timedelta(days=i): schedule.shift_for_day((start + timedelta(days=i)).weekday(), profile.get("shift_pattern"), overrides, start + timedelta(days=i))
        for i in range(days)
    }


def meal_times_for(user_id: int, profile: dict, day: date) -> dict[str, time] | None:
    """Mahlzeitenzeiten des Tages – None, wenn keine Schichtarbeit eingerichtet ist."""
    if not profile.get("shift_pattern") and not repo.get_shifts(user_id, day, day):
        return None
    return schedule.meal_times(shift_on(user_id, profile, day))
