"""Heute – Tagesübersicht (Phase 1: Kalorienziel)."""

from services import energy
from ui import components as ui
from ui import session, theme

profile = session.profile()
target = energy.ensure_current(session.uid(), profile)
name = profile.get("name")
theme.page_title(f"Hallo{', ' + name if name else ''}")
if session.hide_numbers():
    ui.card("Heute", "<p class='kano-muted'>Noch keine Mahlzeiten eingetragen.</p>", glow=True)
else:
    ui.ring(0, target.target_kcal, center_value=ui.fmt_int(target.target_kcal), unit="kcal übrig", sub=f"Ziel {ui.fmt_int(target.target_kcal)}")
