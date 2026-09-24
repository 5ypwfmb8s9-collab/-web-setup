"""Fortschritt: Gewichtstrend, Energiebedarf, flexible Woche, Wohlbefinden und Kraftwerte."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from core import clock, safety, trend
from core.clock import WEEKDAYS_SHORT
from db import repo
from services import energy
from ui import charts
from ui import components as ui
from ui import session, theme

uid = session.uid()
profile = session.profile()
hide = session.hide_numbers()
today = clock.today()

theme.page_title("Fortschritt", "Trends statt Tageswerte – und mehr als nur die Waage.")

tab_weight, tab_energy, tab_week, tab_well, tab_strength = st.tabs(["Gewicht", "Bedarf", "Woche", "Wohlbefinden", "Kraft"])

# ================================================================ Gewicht
with tab_weight:
    latest = repo.latest_weight(uid)
    with st.form("weight_form", border=False, clear_on_submit=False):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            w_date = st.date_input("Datum", value=today, max_value=today, format="DD.MM.YYYY")
            w_value = st.number_input("Gewicht (kg)", min_value=30.0, max_value=300.0,
                                      value=float(latest["weight_kg"]) if latest else 75.0, step=0.1, format="%.1f")
        if st.form_submit_button("Gewicht speichern", type="primary", width="stretch", icon=":material/monitor_weight:"):
            repo.upsert_weight(uid, w_date, w_value)
            st.session_state.pop(f"_safety_{today.isoformat()}", None)
            st.toast("Gespeichert", icon=":material/check_circle:")
            st.rerun()

    all_weights = repo.list_weights(uid)
    if len(all_weights) < 2:
        ui.note("Wiege dich am besten morgens nach dem Aufstehen, 3–7× pro Woche. "
                "KANO zeigt dir daraus einen geglätteten Trend – einzelne Ausreißer spielen dann keine Rolle.")
    if all_weights:
        series = trend.ema_series([(r["date"], r["weight_kg"]) for r in all_weights])
        rate = trend.weekly_rate(series)
        ch7 = trend.change_over(series, 7)
        ch30 = trend.change_over(series, 30)

        def signed(v):
            return "–" if v is None else (("+" if v > 0 else "") + ui.fmt_num(v, 1) + " kg")

        if hide:
            if rate is None:
                verbal = "Noch zu wenige Messungen für einen Trend."
            elif abs(rate) < 0.1:
                verbal = "Dein Trend ist stabil."
            else:
                verbal = f"Dein Trend ist leicht {'fallend' if rate < 0 else 'steigend'}."
            ui.card("Trend", f"<p class='kano-muted'>{verbal}</p>", glow=True)
        else:
            ui.stats([
                ui.Stat(ui.fmt_num(series[-1].trend) + " kg", "Trend aktuell"),
                ui.Stat(signed(ch7), "7 Tage"),
                ui.Stat(signed(ch30), "30 Tage"),
            ])
            if rate is not None:
                st.caption(f"Tempo: {signed(rate)} pro Woche (Trend der letzten 3 Wochen)")

        span = st.segmented_control("Zeitraum", ["30", "90", "365", "alle"], format_func={"30": "30 T", "90": "90 T", "365": "1 J", "alle": "Alle"}.get,
                                    default="90", required=True, key="w_span", label_visibility="collapsed", width="stretch")
        cutoff = None if span == "alle" else today - timedelta(days=int(span))
        df = pd.DataFrame([{"date": p.date, "weight": p.weight, "trend": p.trend} for p in series if cutoff is None or p.date >= cutoff])
        if len(df) >= 2:
            st.altair_chart(charts.weight_chart(df, show_numbers=not hide), width="stretch")
        hint = safety.rapid_loss_hint([(r["date"], r["weight_kg"]) for r in all_weights])
        if hint:
            ui.note(hint, care=True)

        with st.expander("Einträge bearbeiten", icon=":material/edit:"):
            for r in reversed(all_weights[-30:]):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"{clock.format_date_short(r['date'])} · **{ui.fmt_num(r['weight_kg'])} kg**" + (" · importiert" if r["source"] == "import" else ""))
                    if st.button("", key=f"wdel_{r['id']}", icon=":material/delete:", type="tertiary", help="Löschen"):
                        repo.delete_weight(uid, r["id"])
                        st.rerun()

# ================================================================ Energiebedarf
with tab_energy:
    current = energy.ensure_current(uid, profile)
    if hide:
        ui.card("Dein Bedarf", "<p class='kano-muted'>Zahlen sind ausgeblendet. KANO passt deinen Bedarf trotzdem "
                "jede Woche anhand deiner Daten an, damit Pläne und Vorschläge stimmen.</p>", glow=True)
    else:
        method = "Adaptiv – aus deinen Daten" if current.method == "adaptiv" else "Startwert – Formel"
        ui.stats([
            ui.Stat(ui.fmt_int(current.tdee), "Verbrauch/Tag"),
            ui.Stat(ui.fmt_int(current.target_kcal), "Ziel/Tag"),
            ui.Stat(f"{int(current.confidence * 100)} %", "Datensicherheit"),
        ])
        ui.card(method, f"<p class='kano-muted'>{ui.esc(current.explanation)}</p>", glow=current.method == "adaptiv")

        targets = repo.list_targets(uid)
        if len(targets) >= 2:
            hist = pd.DataFrame(
                [{"date": t["week_start"], "serie": "Verbrauch", "wert": t["tdee"]} for t in targets]
                + [{"date": t["week_start"], "serie": "Ziel", "wert": t["target_kcal"]} for t in targets]
            )
            st.altair_chart(charts.lines_chart(hist), width="stretch")

    with st.expander("Wie berechnet KANO deinen Bedarf?", icon=":material/help:"):
        st.markdown(
            """
**Start:** Grundumsatz nach Mifflin-St-Jeor × Aktivitätsfaktor.

**Ab 2–3 Wochen Daten:** KANO vergleicht, was du gegessen hast, mit der Veränderung deines
*Trend*gewichts. Wer im Schnitt 2.000 kcal isst und dabei pro Woche 0,35 kg verliert, verbraucht
etwa 2.000 + 0,35 × 7.700 / 7 ≈ 2.385 kcal.

**Vorsichtig angepasst:** Die neue Schätzung wird nur schrittweise übernommen (max. ±150 kcal pro
Woche) und nur, wenn genug Daten vorliegen (≥ 10 vollständig getrackte Tage, ≥ 4 Wägungen über
≥ 14 Tage). Tage mit auffällig wenig Einträgen gelten als unvollständig und zählen nicht.

**Sicherheitsgrenzen:** Das Ziel liegt nie unter dem Mindestwert und das Defizit nie über 1 % deines
Körpergewichts pro Woche bzw. 25 % deines Verbrauchs.
"""
        )
    if st.button("Jetzt neu berechnen", icon=":material/refresh:", width="stretch"):
        energy.ensure_current(uid, profile, force=True)
        st.toast("Bedarf neu berechnet", icon=":material/check_circle:")
        st.rerun()

# ================================================================ Flexible Woche
with tab_week:
    current, wb = energy.week_budget(uid, profile, today)
    week = clock.week_days(today)
    totals = repo.daily_totals(uid, week[0], week[-1])

    if hide:
        ui.note("Markiere besondere Tage (Geburtstag, Essen gehen …) – KANO verteilt das still im Hintergrund, ohne Zahlen zu zeigen.")
    else:
        ui.stats([
            ui.Stat(ui.fmt_int(wb.total), "Wochenbudget"),
            ui.Stat(ui.fmt_int(sum(v["kcal"] for v in totals.values())), "bisher gegessen"),
            ui.Stat(ui.fmt_int(sum(d.target for d in wb.days if d.date >= today) - (totals.get(today, {}).get("kcal") or 0)), "noch offen"),
        ])
        df = pd.DataFrame([
            {"tag": WEEKDAYS_SHORT[d.date.weekday()] + ("★" if d.exception else ""), "gegessen": round(totals.get(d.date, {}).get("kcal") or 0), "ziel": d.target}
            for d in wb.days
        ])
        st.altair_chart(charts.intake_chart(df), width="stretch")
        rows = []
        for d in wb.days:
            label = clock.format_date_short(d.date) + (f" · {d.note}" if d.note else "") + (" (heute)" if d.date == today else "")
            extra = "" if not d.delta else f" ({'+' if d.delta > 0 else '−'}{ui.fmt_int(abs(d.delta))})"
            rows.append((label, f"{ui.fmt_int(d.target)} kcal{extra}"))
        ui.card("Tagesziele dieser Woche", ui.item_rows(rows))
    for n in wb.notes:
        ui.note(n)

    ui.label("Besonderen Tag planen")
    with st.form("exception_form", border=False, clear_on_submit=True):
        ex_date = st.date_input("Tag", value=today + timedelta(days=1), min_value=week[0], max_value=week[-1] + timedelta(days=7), format="DD.MM.YYYY")
        ex_note = st.text_input("Anlass", placeholder="z. B. Geburtstag, Essen mit Freunden")
        if hide:
            ex_kcal = current.target_kcal * 1.5
            st.caption("KANO plant für diesen Tag großzügig mehr ein.")
        else:
            ex_kcal = st.number_input("Geplante Energie an diesem Tag (kcal)", min_value=500, max_value=6000,
                                      value=int(round(current.target_kcal * 1.5, -1)), step=50)
        if st.form_submit_button("Tag einplanen", type="primary", width="stretch", icon=":material/celebration:"):
            repo.upsert_exception(uid, ex_date, float(ex_kcal), ex_note.strip())
            st.rerun()
    exceptions = repo.list_exceptions(uid, week[0], week[-1] + timedelta(days=7))
    for e in exceptions:
        with st.container(horizontal=True, vertical_alignment="center"):
            txt = f"{clock.format_date_short(e['date'])} · {e['note'] or 'Ausnahmetag'}" + ("" if hide else f" · {ui.fmt_int(e['planned_kcal'])} kcal")
            st.markdown(txt)
            if st.button("", key=f"exdel_{e['id']}", icon=":material/delete:", type="tertiary", help="Entfernen"):
                repo.delete_exception(uid, e["id"])
                st.rerun()

# ================================================================ Wohlbefinden
with tab_well:
    st.caption("Ziele über die Waage hinaus: Wie geht es dir heute?")
    existing = repo.get_wellbeing(uid, today) or {}
    with st.form("wellbeing_form", border=False):
        energy_v = st.slider("Energie", 1, 10, int(existing.get("energy") or 6))
        mood_v = st.slider("Wohlbefinden", 1, 10, int(existing.get("mood") or 6))
        hunger_v = st.slider("Hunger im Alltag", 1, 10, int(existing.get("hunger") or 5), help="1 = kaum Hunger, 10 = ständig hungrig")
        sleep_h = st.slider("Schlaf (Stunden)", 0.0, 12.0, float(existing.get("sleep_hours") or 7.0), step=0.5)
        sleep_q = st.slider("Schlafqualität", 1, 10, int(existing.get("sleep_quality") or 6))
        waist = st.number_input("Taillenumfang (cm, optional)", min_value=0.0, max_value=250.0, value=float(existing.get("waist_cm") or 0.0), step=0.5, format="%.1f")
        note_v = st.text_input("Notiz (optional)", value=existing.get("note") or "", placeholder="z. B. viel Stress, gut geschlafen")
        if st.form_submit_button("Speichern", type="primary", width="stretch", icon=":material/favorite:"):
            repo.upsert_wellbeing(uid, today, energy=energy_v, mood=mood_v, hunger=hunger_v, sleep_hours=sleep_h,
                                  sleep_quality=sleep_q, waist_cm=waist or None, note=note_v.strip() or None)
            if note_v and safety.warning_signs_in_text(note_v):
                st.session_state.care_hint = True
            st.toast("Danke fürs Eintragen", icon=":material/favorite:")
            st.rerun()
    if st.session_state.get("care_hint"):
        ui.note(safety.SUPPORT_HTML, care=True)

    rows = repo.list_wellbeing(uid, since=today - timedelta(days=60))
    if len(rows) >= 2:
        long = []
        for r in rows:
            for key, name in (("energy", "Energie"), ("mood", "Wohlbefinden"), ("sleep_quality", "Schlafqualität")):
                if r.get(key) is not None:
                    long.append({"date": r["date"], "serie": name, "wert": r[key]})
        if long:
            st.altair_chart(charts.lines_chart(pd.DataFrame(long), domain=[1, 10]), width="stretch")
        waist_rows = [{"date": r["date"], "serie": "Taille (cm)", "wert": r["waist_cm"]} for r in rows if r.get("waist_cm")]
        if len(waist_rows) >= 2:
            st.altair_chart(charts.lines_chart(pd.DataFrame(waist_rows), height=160), width="stretch")
    else:
        ui.note("Nach ein paar Einträgen siehst du hier, wie sich Energie, Schlaf und Wohlbefinden entwickeln – "
                "oft verändern sie sich früher als die Waage.")

# ================================================================ Kraft
with tab_strength:
    entries = repo.list_strength(uid)
    known = sorted({e["exercise"] for e in entries})
    with st.form("strength_form", border=False, clear_on_submit=True):
        choice = st.selectbox("Übung", options=known + ["Neue Übung …"], index=0 if known else None,
                              placeholder="Übung wählen") if known else "Neue Übung …"
        new_ex = st.text_input("Neue Übung", placeholder="z. B. Kniebeuge, Liegestütze") if choice == "Neue Übung …" or not known else ""
        with st.container(horizontal=True):
            s_weight = st.number_input("Gewicht (kg)", min_value=0.0, max_value=500.0, value=0.0, step=2.5)
            s_reps = st.number_input("Wiederholungen", min_value=1, max_value=100, value=8, step=1)
        if st.form_submit_button("Satz speichern", type="primary", width="stretch", icon=":material/fitness_center:"):
            name = (new_ex or (choice if choice != "Neue Übung …" else "")).strip()
            if name:
                repo.add_strength(uid, today, name, s_weight or None, int(s_reps))
                st.rerun()
            else:
                st.info("Bitte eine Übung angeben.")
    if entries:
        # Geschätztes 1-Wiederholungs-Maximum (Epley) als vergleichbarer Kraftwert
        long = []
        for e in entries:
            load = e["weight_kg"] or 0
            value = load * (1 + (e["reps"] or 1) / 30) if load else float(e["reps"] or 0)
            long.append({"date": e["date"], "serie": e["exercise"], "wert": round(value, 1)})
        df = pd.DataFrame(long).groupby(["date", "serie"], as_index=False)["wert"].max()
        if len(df) >= 2:
            st.altair_chart(charts.lines_chart(df, y_title="Kraftwert"), width="stretch")
            st.caption("Kraftwert = geschätztes Maximalgewicht für 1 Wiederholung (Epley); ohne Gewicht: Wiederholungen.")
        with st.expander("Letzte Sätze", icon=":material/list:"):
            for e in reversed(entries[-20:]):
                with st.container(horizontal=True, vertical_alignment="center"):
                    load = f"{ui.fmt_num(e['weight_kg'])} kg × " if e["weight_kg"] else ""
                    st.markdown(f"{clock.format_date_short(e['date'])} · {e['exercise']} · {load}{e['reps']}")
                    if st.button("", key=f"sdel_{e['id']}", icon=":material/delete:", type="tertiary", help="Löschen"):
                        repo.delete_strength(uid, e["id"])
                        st.rerun()
    else:
        ui.note("Kraft wächst oft, während sich die Waage kaum bewegt. Trag ein paar Sätze ein, um das zu sehen.")

