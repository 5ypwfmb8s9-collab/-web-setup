"""Coach: lokale Muster, wöchentliche Kurzauswertung und Chat mit Claude."""

import streamlit as st

from core import clock, features, safety
from db import repo
from services import ai, coach_context
from ui import components as ui
from ui import session, theme

uid = session.uid()
profile = session.profile()
hide = session.hide_numbers()
today = clock.today()
week_start = clock.week_start(today)
tier = session.user_row().get("tier")
ai_ready = ai.is_configured() and session.ai_allowed() and features.enabled("coach", tier)

theme.page_title("Coach", "Neugierig auf Muster – nie mit erhobenem Zeigefinger.")

summary, found = coach_context.gather(uid, profile, today)

# ---------------------------------------------------------------- Wochenauswertung
report = repo.get_report(uid, week_start)
if report:
    ui.card("Deine Woche", f"<p>{ui.esc(report['content'])}</p>", glow=True)
elif ai_ready:
    if st.button("Kurze Wochenauswertung erstellen", icon=":material/insights:", width="stretch", type="primary"):
        with st.spinner("Schaue mir deine Woche an …"):
            try:
                text = ai.weekly_review(summary, hide, week_start)
            except ai.AIError as exc:
                st.info(str(exc), icon=":material/cloud_off:")
            else:
                repo.save_report(uid, week_start, text)
                st.rerun()

# ---------------------------------------------------------------- Lokale Muster (ohne KI)
if found:
    ui.label("Was KANO bemerkt hat")
    for ins in found:
        ui.card(ins.title, f"<p class='kano-muted'>{ui.esc(ins.text_plain if hide else ins.text)}</p>")
else:
    ui.note("Nach ein bis zwei Wochen Tracking erkennt KANO hier Muster – z. B. ob ein kleines Mittagessen "
            "zu mehr Hunger am Abend führt.")

# ---------------------------------------------------------------- Chat
ui.label("Frag deinen Coach")
if not ai.is_configured() or not session.ai_allowed():
    ui.note("Der Chat nutzt Claude. Aktiviere die KI-Funktionen unter <b>Profil → Einstellungen</b>"
            + ("" if ai.is_configured() else " (und hinterlege einen API-Schlüssel)") + ".")
elif not features.enabled("coach", tier):
    ui.note(features.locked_note("coach"))

history = repo.list_coach_messages(uid)
for msg in history:
    with st.chat_message(msg["role"], avatar=":material/person:" if msg["role"] == "user" else ":material/auto_awesome:"):
        st.markdown(msg["content"])

if st.session_state.get("coach_care"):
    ui.note(safety.SUPPORT_HTML, care=True)

starters = ["Wie war meine Woche?", "Idee für ein proteinreiches Abendessen", "Warum habe ich abends Heißhunger?"]
starter = None
if not history and ai_ready:
    with st.container(horizontal=True):
        for i, s_ in enumerate(starters):
            if st.button(s_, key=f"starter_{i}"):
                starter = s_

prompt = st.chat_input("Schreib deinem Coach …", disabled=not ai_ready, max_chars=2000) or starter
if prompt:
    if safety.warning_signs_in_text(prompt):
        st.session_state.coach_care = True
    repo.add_coach_message(uid, "user", prompt)
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(prompt)
    convo = [{"role": m["role"], "content": m["content"]} for m in history[-20:]] + [{"role": "user", "content": prompt}]
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        try:
            answer = st.write_stream(ai.coach_stream(convo, summary, hide))
        except ai.AIError as exc:
            answer = None
            st.info(str(exc), icon=":material/cloud_off:")
    if answer:
        repo.add_coach_message(uid, "assistant", answer if isinstance(answer, str) else "".join(answer))
    st.rerun()

if history:
    if st.button("Verlauf löschen", icon=":material/delete_sweep:", type="tertiary"):
        repo.clear_coach_messages(uid)
        st.session_state.pop("coach_care", None)
        st.rerun()

st.caption("Der Coach sieht nur eine Zusammenfassung deiner Werte (keine E-Mail, keinen Namen, keine Einzeleinträge). "
           "Er ersetzt keine ärztliche oder therapeutische Beratung.")
