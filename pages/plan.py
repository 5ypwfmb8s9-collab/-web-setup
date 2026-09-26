"""Plan: Wochenplan, Einkaufsliste, Resteverwertung, Tagesstruktur (Schichten) und Preise."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import clock, pricing, schedule, shopping
from core.meals import MEALS
from core.nutrition import DIET_TYPES
from db import repo
from services import ai, energy, planning
from ui import components as ui
from ui import session, theme

uid = session.uid()
profile = session.profile()
hide = session.hide_numbers()
today = clock.today()
ai_ready = ai.is_configured() and session.ai_allowed()

theme.page_title("Plan", "Essen, das in deinen echten Alltag passt.")
tab_week, tab_shop, tab_left, tab_shift, tab_price = st.tabs(["Woche", "Einkauf", "Reste", "Schichten", "Preise"])


def ai_note() -> None:
    if not session.ai_allowed():
        ui.note("Pläne und Rezepte erstellt die KI. Du kannst sie unter <b>Profil → Einstellungen</b> aktivieren.")
    else:
        ui.note("Die KI ist gerade nicht eingerichtet – Pläne können erst mit API-Schlüssel erstellt werden.")


# ================================================================ Wochenplan
with tab_week:
    plan_row = repo.latest_plan(uid)

    with st.expander("Neuen Plan erstellen", expanded=plan_row is None, icon=":material/auto_awesome:"):
        if not ai_ready:
            ai_note()
        start = st.date_input("Start", value=today, min_value=today, max_value=today + timedelta(days=14), format="DD.MM.YYYY", key="plan_start")
        days = st.segmented_control("Tage", [3, 5, 7], default=7, required=True, key="plan_days", format_func=lambda d: f"{d} Tage", width="stretch")
        persons = st.number_input("Für wie viele Personen einkaufen?", min_value=1, max_value=8, value=int(profile.get("household_size") or 1), step=1)
        st.caption(f"Ernährungsform: {DIET_TYPES.get(profile.get('diet_type') or 'ausgewogen')} · "
                   f"ohne: {profile.get('dislikes') or '–'} (änderbar im Profil)")
        budget_on = st.toggle("Budget-Modus", value=bool(profile.get("weekly_budget_eur")))
        budget = None
        if budget_on:
            budget = st.number_input("Wochenbudget für alle Personen (€)", min_value=10.0, max_value=500.0,
                                     value=float(profile.get("weekly_budget_eur") or 50.0), step=5.0)
        prep = st.toggle("Meal Prep", help="z. B. „Ich koche am Sonntag für 3 Tage vor“")
        prep_day, prep_portions, prep_meal = None, 3, "mittag"
        if prep:
            plan_dates = [start + timedelta(days=i) for i in range(days)]
            prep_day = st.selectbox("Kochtag", plan_dates, format_func=clock.format_date_short, index=0)
            prep_portions = st.segmented_control("Für wie viele Tage?", [2, 3, 4], default=3, required=True, width="stretch")
            prep_meal = st.segmented_control("Welche Mahlzeit?", ["mittag", "abend"], format_func=MEALS.get, default="mittag", required=True, width="stretch")
        extra = st.text_input("Wünsche (optional)", placeholder="z. B. schnelle Frühstücke, einmal Fisch, viel Gemüse")
        if st.button("Plan erstellen", type="primary", width="stretch", icon=":material/auto_awesome:", disabled=not ai_ready):
            if budget_on and budget != profile.get("weekly_budget_eur"):
                session.update_profile(weekly_budget_eur=budget)
            if persons != profile.get("household_size"):
                session.update_profile(household_size=int(persons))
            req = planning.PlanRequest(start, int(days), int(persons), budget if budget_on else None, prep, prep_day,
                                       int(prep_portions), prep_meal, extra)
            with st.status("Plane deine Woche …", expanded=False) as status:
                try:
                    planning.generate(uid, profile, req)
                except ai.AIError as exc:
                    status.update(label=str(exc), state="error")
                else:
                    status.update(label="Plan fertig!", state="complete")
                    st.rerun()

    if plan_row:
        plan = plan_row["plan"]
        params = plan_row["params"]
        plan_days = plan.get("days", [])
        if plan.get("tips"):
            ui.note(ui.esc(plan["tips"]))
        if plan.get("prep_notes"):
            ui.card("Meal Prep", f"<p class='kano-muted'>{ui.esc(plan['prep_notes'])}</p>", glow=True)

        options = list(range(len(plan_days)))

        def day_label(i: int) -> str:
            try:
                return clock.WEEKDAYS_SHORT[date.fromisoformat(plan_days[i]["date"]).weekday()]
            except (ValueError, KeyError):
                return f"Tag {i + 1}"

        today_idx = next((i for i, d in enumerate(plan_days) if d.get("date") == today.isoformat()), 0)
        sel = st.segmented_control("Tag", options, format_func=day_label, default=today_idx, required=True,
                                   key=f"plan_day_{plan_row['id']}", label_visibility="collapsed", width="stretch")
        day = plan_days[sel] if plan_days else None
        if day:
            try:
                d_date = date.fromisoformat(day["date"])
                head = clock.format_date_long(d_date)
            except ValueError:
                d_date, head = today, day.get("date", "")
            total = sum(m.get("kcal") or 0 for m in day.get("meals", []))
            sub = schedule.SHIFTS.get(day.get("shift", ""), day.get("shift", ""))
            st.html(f'<div class="kano-meal-head"><span class="t">{ui.esc(head)}</span>'
                    f'<span class="k">{ui.esc(sub)}{"" if hide else " · " + ui.fmt_int(total) + " kcal"}</span></div>')
            for mi, meal in enumerate(sorted(day.get("meals", []), key=lambda m: m.get("time", ""))):
                with st.container(key=f"card_meal_{sel}_{mi}"):
                    kcal_txt = "" if hide else f" · {ui.fmt_int(meal.get('kcal'))} kcal"
                    st.html(f'<div class="kano-label">{ui.esc(meal.get("time", ""))} · {ui.esc(MEALS.get(meal.get("slot"), ""))}{kcal_txt}</div>'
                            f'<div style="font-weight:700;font-size:1.05rem;margin:4px 0 2px 0">{ui.esc(meal.get("name", ""))}</div>'
                            + (f'<span class="kano-chip active">{ui.esc(meal["prep"])}</span>' if meal.get("prep") else ""))
                    with st.expander("Zutaten & Zubereitung"):
                        if meal.get("ingredients"):
                            st.html(ui.item_rows([(i["name"], shopping.format_qty(i.get("qty"), i.get("unit"))) for i in meal["ingredients"]]))
                        if meal.get("instructions"):
                            st.caption(meal["instructions"])
                        if not hide:
                            st.caption(f"P {ui.fmt_int(meal.get('protein'))} g · KH {ui.fmt_int(meal.get('carbs'))} g · F {ui.fmt_int(meal.get('fat'))} g")
                    log_day = d_date if d_date <= today else today
                    if st.button(f"Gegessen – {'heute' if log_day == today else clock.format_date_short(log_day)} eintragen",
                                 key=f"logplan_{plan_row['id']}_{sel}_{mi}", width="stretch", icon=":material/check:"):
                        repo.add_entries(uid, log_day, meal.get("slot") or "mittag", [{
                            "name": meal.get("name", "Mahlzeit"), "grams": None, "size_label": "mittel",
                            "kcal": meal.get("kcal") or 0, "protein": meal.get("protein") or 0,
                            "carbs": meal.get("carbs") or 0, "fat": meal.get("fat") or 0,
                        }], "plan")
                        st.toast("Eingetragen", icon=":material/check_circle:")
        if params.get("budget_eur") and plan.get("estimated_cost_eur"):
            st.caption(f"Geschätzte Kosten laut Plan: ≈ {plan['estimated_cost_eur']:.2f} € pro Person".replace(".", ","))
    elif ai_ready:
        ui.note("Noch kein Plan. Öffne „Neuen Plan erstellen“ – in etwa einer Minute steht deine Woche.")

# ================================================================ Einkaufsliste
with tab_shop:
    items = sorted(repo.list_shopping(uid), key=lambda i: (
        shopping.SECTION_ORDER.index(i["section"]) if i["section"] in shopping.SECTION_ORDER else 99, i["name"].lower()))
    plan_row = repo.latest_plan(uid)
    if plan_row:
        persons_now = int(plan_row["params"].get("persons") or 1)
        with st.container(horizontal=True, vertical_alignment="bottom"):
            new_persons = st.number_input("Personen", min_value=1, max_value=8, value=persons_now, step=1, key="shop_persons")
            if st.button("Neu berechnen", icon=":material/refresh:", width="stretch"):
                repo.update_plan(uid, plan_row["id"], plan_row["plan"], {**plan_row["params"], "persons": int(new_persons)})
                planning.rebuild_shopping(uid, plan_row["id"], plan_row["plan"], int(new_persons))
                st.rerun()
    if not items:
        ui.note("Die Einkaufsliste entsteht automatisch aus deinem Wochenplan. Eigene Artikel kannst du unten ergänzen.")
    else:
        est = planning.cost(uid, [i for i in items if not i["checked"]])
        open_count = sum(1 for i in items if not i["checked"])
        st.caption(f"{open_count} von {len(items)} offen · ≈ {est.at_checkout:.2f} € an der Kasse (ganze Packungen), "
                   f"≈ {est.proportional:.2f} € anteilig verbraucht".replace(".", ","))
        current = None
        for it in items:
            if it["section"] != current:
                current = it["section"]
                ui.label(current)
            qty = shopping.format_qty(it["qty"], it["unit"])
            label = it["name"] + (f"  ·  {qty}" if qty else "")

            def toggle(item_id=it["id"]):
                repo.set_shopping_checked(uid, item_id, st.session_state[f"shop_{item_id}"])

            st.checkbox(label, value=bool(it["checked"]), key=f"shop_{it['id']}", on_change=toggle)
        with st.container(horizontal=True):
            if st.button("Erledigte entfernen", width="stretch", icon=":material/done_all:"):
                repo.clear_shopping(uid, only_checked=True)
                st.rerun()
        with st.expander("Liste teilen", icon=":material/share:"):
            st.code(shopping.as_text(items), language=None)
            st.caption("Antippen → kopieren → in WhatsApp, Notizen o. Ä. einfügen.")
    with st.form("add_shop", border=False, clear_on_submit=True):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            new_item = st.text_input("Artikel hinzufügen", placeholder="z. B. Spülmittel")
            if st.form_submit_button("", icon=":material/add:") and new_item.strip():
                repo.add_shopping_item(uid, new_item.strip(), shopping.guess_section(new_item))
                st.rerun()

# ================================================================ Resteverwertung
with tab_left:
    if not ai_ready:
        ai_note()
    st.caption("Was ist noch da? KANO schlägt ein Gericht vor, das in dein heutiges Ziel passt.")
    with st.form("leftovers", border=False):
        have = st.text_area("Vorhandene Zutaten", placeholder="z. B. 2 Eier, halbe Zucchini, Feta, Reis von gestern", height=90, label_visibility="collapsed")
        go = st.form_submit_button("Rezept vorschlagen", type="primary", width="stretch", icon=":material/soup_kitchen:", disabled=not ai_ready)
    if go and have.strip():
        target = energy.day_target(uid, profile, today)
        eaten = sum(v["kcal"] for v in repo.daily_totals(uid, today, today).values())
        remaining = int(target - eaten)
        budget_kcal = max(300, min(remaining, 1000)) if remaining > 250 else None
        with st.spinner("Überlege, was sich daraus machen lässt …"):
            try:
                st.session_state.recipe = ai.leftover_recipe(have, budget_kcal, DIET_TYPES.get(profile.get("diet_type") or "ausgewogen"),
                                                              profile.get("dislikes") or "", hide).model_dump()
            except ai.AIError as exc:
                st.info(str(exc), icon=":material/cloud_off:")
    recipe = st.session_state.get("recipe")
    if recipe:
        meta = f"{recipe['time_minutes']} Min · {recipe['servings']} Portion(en)" + ("" if hide else f" · {ui.fmt_int(recipe['kcal_per_serving'])} kcal pro Portion")
        body = f"<p class='kano-small'>{ui.esc(meta)}</p>" + ui.item_rows([(i["name"], shopping.format_qty(i.get("qty"), i.get("unit"))) for i in recipe["ingredients"]])
        ui.card(recipe["name"], body, glow=True)
        for n, step in enumerate(recipe["steps"], 1):
            st.markdown(f"**{n}.** {step}")
        if recipe.get("note"):
            st.caption(recipe["note"])
        with st.container(horizontal=True):
            if recipe.get("missing") and st.button("Fehlendes auf die Liste", width="stretch", icon=":material/add_shopping_cart:"):
                for m in recipe["missing"]:
                    repo.add_shopping_item(uid, m, shopping.guess_section(m))
                st.toast("Zur Einkaufsliste hinzugefügt", icon=":material/check_circle:")
            if st.button("Gegessen eintragen", type="primary", width="stretch", icon=":material/check:"):
                from core.meals import guess_meal

                repo.add_entries(uid, today, guess_meal(clock.now()), [{
                    "name": recipe["name"], "grams": None, "size_label": "mittel", "kcal": recipe["kcal_per_serving"],
                    "protein": recipe["protein"], "carbs": recipe["carbs"], "fat": recipe["fat"],
                }], "plan")
                st.session_state.pop("recipe", None)
                st.toast("Eingetragen", icon=":material/check_circle:")
                st.rerun()

# ================================================================ Schichten / Tagesstruktur
with tab_shift:
    st.caption("Arbeitest du in Schichten? Dann passt KANO Mahlzeitenzeiten, Vorschläge und Pläne an.")
    pattern = dict(profile.get("shift_pattern") or {})
    with st.form("shift_pattern", border=False):
        new_pattern = {}
        for wd in range(7):
            new_pattern[str(wd)] = st.segmented_control(
                clock.WEEKDAYS_DE[wd], list(schedule.SHIFTS), format_func=schedule.SHIFT_SHORT.get,
                default=pattern.get(str(wd), "frei"), required=True, key=f"sp_{wd}", width="stretch",
            )
        if st.form_submit_button("Wochenmuster speichern", type="primary", width="stretch"):
            has_shifts = any(v != "frei" for v in new_pattern.values())
            session.update_profile(shift_pattern=new_pattern if has_shifts else None)
            st.toast("Gespeichert", icon=":material/check_circle:")
            st.rerun()

    ui.label("Einzelne Tage abweichend")
    with st.form("shift_day", border=False, clear_on_submit=True):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            sd = st.date_input("Tag", value=today, min_value=today - timedelta(days=7), max_value=today + timedelta(days=60), format="DD.MM.YYYY")
            ss = st.selectbox("Schicht", list(schedule.SHIFTS), format_func=schedule.SHIFT_SHORT.get)
        if st.form_submit_button("Festlegen", width="stretch"):
            repo.set_shift(uid, sd, ss)
            st.rerun()
    overrides = repo.get_shifts(uid, today - timedelta(days=1), today + timedelta(days=60))
    for d, s_ in sorted(overrides.items()):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"{clock.format_date_short(d)} · {schedule.SHIFTS[s_]}")
            if st.button("", key=f"shdel_{d.isoformat()}", icon=":material/delete:", type="tertiary", help="Entfernen"):
                repo.set_shift(uid, d, None)
                st.rerun()
    with st.expander("Mahlzeitenzeiten je Schicht", icon=":material/schedule:"):
        for key, name in schedule.SHIFTS.items():
            times = sorted(schedule.meal_times(key).items(), key=lambda kv: kv[1])
            st.markdown(f"**{name}** – " + " · ".join(f"{MEALS[s]} {t.strftime('%H:%M')}" for s, t in times))
            if schedule.MEAL_HINTS[key]:
                st.caption(schedule.MEAL_HINTS[key])

# ================================================================ Preise
with tab_price:
    st.caption("Grundlage für den Budget-Modus. Standard sind typische Discounter-Preise – passe sie an deinen Markt an.")
    rows = repo.list_prices(uid)
    data = rows if rows else [p.__dict__ for p in pricing.DEFAULT_PRICES]
    df = pd.DataFrame([{k: r[k] for k in ("item", "unit", "pack_qty", "price_eur", "section")} for r in data])
    edited = st.data_editor(
        df, num_rows="dynamic", hide_index=True, width="stretch", key="price_editor",
        column_config={
            "item": st.column_config.TextColumn("Artikel", required=True),
            "unit": st.column_config.SelectboxColumn("Einheit", options=["g", "ml", "Stk"], required=True, width="small"),
            "pack_qty": st.column_config.NumberColumn("Packung", min_value=1, required=True, width="small"),
            "price_eur": st.column_config.NumberColumn("Preis €", min_value=0.0, format="%.2f", required=True, width="small"),
            "section": st.column_config.SelectboxColumn("Bereich", options=shopping.SECTION_ORDER, required=True),
        },
    )
    with st.container(horizontal=True):
        if st.button("Preise speichern", type="primary", width="stretch"):
            clean = edited.dropna(subset=["item", "unit", "pack_qty", "price_eur"]).fillna({"section": "Sonstiges"})
            repo.replace_prices(uid, clean.to_dict("records"))
            st.toast("Preise gespeichert", icon=":material/check_circle:")
        if rows and st.button("Standard wiederherstellen", width="stretch"):
            repo.replace_prices(uid, [])
            st.rerun()
