"""Heute: Fortschrittsring, Makros, Mahlzeiten, Vorschläge und Tagesstruktur."""

from collections import defaultdict
from datetime import timedelta

import streamlit as st

from core import clock, patterns, schedule
from core.meals import MEAL_ORDER, MEALS, guess_meal
from db import repo
from services import energy, safety_service, schedule_service
from ui import components as ui
from ui import session, theme

uid = session.uid()
profile = session.profile()
hide = session.hide_numbers()
today = clock.today()
pages = st.session_state.get("_pages", {})

current, wb = energy.week_budget(uid, profile, today)
day_budget = wb.for_day(today)
target = day_budget.target if day_budget else current.target_kcal

entries = repo.get_entries(uid, today)
eaten = sum(e["kcal"] for e in entries)
protein = sum(e["protein"] or 0 for e in entries)
carbs = sum(e["carbs"] or 0 for e in entries)
fat = sum(e["fat"] or 0 for e in entries)

name = profile.get("name")
theme.page_title(f"{clock.greeting()}{', ' + name if name else ''}")

# ---------------------------------------------------------------- Ring & Makros
if hide:
    meals_logged = len({e["meal"] for e in entries})
    ui.card(
        "Heute",
        f"<p class='kano-muted'>{meals_logged} von 4 Mahlzeiten eingetragen. "
        "Hör auf deinen Hunger – KANO kümmert sich um die Zahlen im Hintergrund.</p>",
        glow=True,
    )
else:
    remaining = target - eaten
    if remaining >= 0:
        ui.ring(eaten, target, center_value=ui.fmt_int(remaining), unit="kcal übrig", sub=f"{ui.fmt_int(eaten)} von {ui.fmt_int(target)}")
    else:
        ui.ring(eaten, target, center_value=ui.fmt_int(eaten), unit="kcal heute", sub=f"Tagesziel {ui.fmt_int(target)} erreicht")
    if day_budget and day_budget.exception:
        ui.note(f"Heute ist ein geplanter Ausnahmetag{': ' + ui.esc(day_budget.note) if day_budget.note else ''}. Genieß es!")
    elif day_budget and day_budget.delta:
        ui.note(f"Dein Ziel ist heute wegen deiner flexiblen Woche um {ui.fmt_int(abs(day_budget.delta))} kcal {'niedriger' if day_budget.delta < 0 else 'höher'}.")
    m = current.macros
    ui.bars([
        ui.bar("Protein", protein, m.protein_g),
        ui.bar("Kohlenhydrate", carbs, m.carbs_g),
        ui.bar("Fett", fat, m.fat_g),
    ])

for hint in safety_service.hints(uid, profile):
    ui.note(hint, care=True)

# ---------------------------------------------------------------- Vorschlag für die aktuelle Mahlzeit
meal_times = schedule_service.meal_times_for(uid, profile, today)
now_meal = guess_meal(clock.now(), meal_times)
recent = repo.get_entries(uid, today - timedelta(days=35), today)
suggestions = patterns.suggest(recent, today, now_meal, limit=2)
if suggestions:
    ui.label(f"Schnell eintragen · {MEALS[now_meal]}")
    for i, sug in enumerate(suggestions):
        label = f"{sug.reason}  ·  {sug.title}" + ("" if hide else f"  ·  {ui.fmt_int(sug.kcal)} kcal")
        if st.button(label, key=f"today_sug_{i}", width="stretch", icon=":material/history:"):
            repo.add_entries(uid, today, now_meal, sug.items, "favorit")
            st.toast(f"{MEALS[now_meal]} eingetragen", icon=":material/check_circle:")
            st.rerun()

if "tracken" in pages:
    with st.container(key="cta_track"):
        st.page_link(pages["tracken"], label="Essen eintragen", icon=":material/add:", width="stretch")

# ---------------------------------------------------------------- Tagesstruktur bei Schichtarbeit
if meal_times:
    shift = schedule_service.shift_on(uid, profile, today)
    times = sorted(meal_times.items(), key=lambda kv: (kv[1].hour - 12) % 24 if shift == "nacht" else kv[1].hour * 60 + kv[1].minute)
    ui.card(
        f"Tagesstruktur · {schedule.SHIFT_SHORT[shift]}",
        ui.item_rows([(MEALS[slot], t.strftime("%H:%M")) for slot, t in times])
        + (f"<p class='kano-small' style='margin-top:8px'>{ui.esc(schedule.MEAL_HINTS[shift])}</p>" if schedule.MEAL_HINTS[shift] else ""),
    )

# ---------------------------------------------------------------- Mahlzeiten des Tages
by_meal: dict[str, list[dict]] = defaultdict(list)
for e in entries:
    by_meal[e["meal"]].append(e)

if not entries:
    ui.card(None, "<p class='kano-muted'>Noch nichts eingetragen. Tipp auf „Essen eintragen“ – "
                  "ein Satz wie „Müsli mit Banane“ reicht.</p>")

for meal in MEAL_ORDER:
    items = by_meal.get(meal)
    if not items:
        continue
    total = sum(i["kcal"] for i in items)
    head = f'<div class="kano-meal-head"><span class="t">{MEALS[meal]}</span>' + (
        "" if hide else f'<span class="k">{ui.fmt_int(total)} kcal</span>'
    ) + "</div>"
    rows = []
    for i in items:
        if hide:
            detail = {"klein": "klein", "mittel": "mittel", "gross": "groß"}.get(i["size_label"] or "", "")
        else:
            detail = f"{ui.fmt_int(i['kcal'])} kcal"
        rows.append((i["name"], detail))
    st.html(head + f'<div class="kano-card" style="padding:4px 16px">{ui.item_rows(rows)}</div>')
    with st.expander("Bearbeiten", icon=":material/edit:"):
        for i in items:
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"{ui.esc(i['name'])}")
                if st.button("", key=f"del_{i['id']}", icon=":material/delete:", type="tertiary", help="Eintrag löschen"):
                    repo.delete_entry(uid, i["id"])
                    st.rerun()
        with st.form(f"fav_form_{meal}", border=False):
            fav_name = st.text_input("Als Favorit merken", placeholder=f"z. B. Mein {MEALS[meal]}", key=f"favname_{meal}")
            if st.form_submit_button("Merken", icon=":material/star:", width="stretch") and fav_name.strip():
                repo.add_favorite(uid, fav_name.strip(), meal, items)
                st.toast("Als Favorit gespeichert", icon=":material/star:")
