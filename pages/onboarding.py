"""Onboarding: Hinweise, Profil, Ziel, Ernährungsstil – am Ende das berechnete Startziel."""

from datetime import datetime, timezone

import streamlit as st

from core import clock, nutrition
from db import repo
from services import energy
from ui import components as ui
from ui import session, theme

STEPS = ["Willkommen", "Über dich", "Dein Ziel", "Dein Stil", "Dein Start"]

ob: dict = st.session_state.setdefault(
    "ob",
    {
        "step": 0,
        "name": "",
        "sex": "w",
        "birth_year": 1990,
        "height_cm": 170.0,
        "weight_kg": 75.0,
        "goal": "abnehmen",
        "goal_weight_kg": None,
        "pace": "normal",
        "activity": "leicht",
        "diet_type": "ausgewogen",
        "dislikes": "",
        "hide_numbers": False,
        "approx_mode": False,
        "ai_consent": True,
        "care_flag": False,
    },
)
step = ob["step"]


def go(delta: int) -> None:
    ob["step"] = max(0, min(len(STEPS) - 1, ob["step"] + delta))


theme.top_bar(f"Schritt {step + 1} von {len(STEPS)}")
st.html(
    '<div class="kano-bar" style="margin-top:0"><div class="track">'
    f'<div class="fill" style="width:{(step + 1) / len(STEPS) * 100:.0f}%"></div></div></div>'
)
theme.page_title(STEPS[step])

# ---------------------------------------------------------------- Schritt 0: Hinweise
if step == 0:
    ui.card(
        None,
        "<p>KANO hilft dir, mit wenig Aufwand im Blick zu behalten, was du isst – und passt sich "
        "deinem echten Alltag an. Kein Verzicht-Drama, keine Streaks, keine roten Zahlen.</p>",
        glow=True,
    )
    ui.card(
        "Wichtig vorab",
        "<p class='kano-muted'>KANO ist <b>kein Medizinprodukt</b> und ersetzt keine ärztliche oder "
        "ernährungstherapeutische Beratung. Alle Werte sind Schätzungen. Bei Schwangerschaft, Stillzeit, "
        "Erkrankungen, Medikamenteneinnahme oder einer (früheren) Essstörung sprich bitte vorher mit "
        "deiner Ärztin oder deinem Arzt.</p>",
    )
    accepted = st.checkbox("Verstanden – ich nutze KANO als Alltagshilfe, nicht als medizinische Beratung.")
    if st.button("Weiter", type="primary", width="stretch", disabled=not accepted):
        ob["disclaimer"] = True
        go(1)
        st.rerun()

# ---------------------------------------------------------------- Schritt 1: Körperdaten
elif step == 1:
    ob["name"] = st.text_input("Wie dürfen wir dich nennen? (optional)", value=ob["name"], max_chars=40, key="ob_name")
    ob["sex"] = st.segmented_control(
        "Geschlecht (für die Grundumsatz-Formel)",
        options=list(nutrition.SEX_LABELS),
        format_func=nutrition.SEX_LABELS.get,
        default=ob["sex"],
        required=True,
        width="stretch",
        key="ob_sex",
    )
    this_year = clock.today().year
    ob["birth_year"] = st.number_input("Geburtsjahr", min_value=this_year - 100, max_value=this_year - 12, value=int(ob["birth_year"]), step=1, key="ob_by")
    ob["height_cm"] = st.number_input("Größe (cm)", min_value=120.0, max_value=230.0, value=float(ob["height_cm"]), step=1.0, format="%.0f", key="ob_h")
    ob["weight_kg"] = st.number_input("Aktuelles Gewicht (kg)", min_value=30.0, max_value=300.0, value=float(ob["weight_kg"]), step=0.1, format="%.1f", key="ob_w")
    ob["care_flag"] = st.checkbox(
        "Eines davon trifft auf mich zu: Schwangerschaft/Stillzeit, (frühere) Essstörung, "
        "Erkrankung mit ärztlich begleiteter Ernährung",
        value=ob["care_flag"],
        key="ob_care",
    )
    if ob["care_flag"]:
        ui.note(
            "Danke für dein Vertrauen. KANO plant in diesem Fall <b>kein Kaloriendefizit</b> und blendet "
            "Zahlen standardmäßig aus. Ein Abnehmziel besprichst du am besten mit deiner Ärztin/deinem Arzt "
            "oder einer Ernährungsfachkraft.",
            care=True,
        )
    age = this_year - int(ob["birth_year"])
    if age < 18:
        ui.note("KANO ist für Erwachsene gedacht. Unter 18 planen wir kein Kaloriendefizit.", care=True)
    with st.container(horizontal=True):
        if st.button("Zurück", width="stretch"):
            go(-1)
            st.rerun()
        if st.button("Weiter", type="primary", width="stretch"):
            go(1)
            st.rerun()

# ---------------------------------------------------------------- Schritt 2: Ziel
elif step == 2:
    goal_options = list(nutrition.GOALS)
    if ob["care_flag"] or clock.today().year - int(ob["birth_year"]) < 18:
        goal_options = ["halten", "aufbauen"]
    if ob["goal"] not in goal_options:
        ob["goal"] = goal_options[0]
    ob["goal"] = st.segmented_control(
        "Was möchtest du erreichen?", options=goal_options, format_func=nutrition.GOALS.get,
        default=ob["goal"], required=True, width="stretch", key="ob_goal",
    )
    if ob["goal"] == "abnehmen":
        ob["pace"] = st.radio(
            "Tempo", options=list(nutrition.PACES), format_func=lambda k: nutrition.PACES[k][0],
            index=list(nutrition.PACES).index(ob["pace"]), key="ob_pace",
            help="KANO begrenzt das Tempo automatisch auf höchstens 1 % deines Körpergewichts pro Woche.",
        )
        gw = st.number_input(
            "Zielgewicht (kg, optional)", min_value=0.0, max_value=300.0,
            value=float(ob["goal_weight_kg"] or 0.0), step=0.5, format="%.1f", key="ob_gw",
            help="Hilft bei der Einschätzung – 0 lassen, wenn du kein festes Ziel hast.",
        )
        ob["goal_weight_kg"] = gw or None
        for issue in nutrition.goal_weight_issues(ob["goal"], ob["height_cm"], ob["weight_kg"], ob["goal_weight_kg"]):
            ui.note(issue, care=True)
    st.write("")
    ob["activity"] = st.radio(
        "Wie aktiv ist dein Alltag?", options=list(nutrition.ACTIVITY_LEVELS),
        format_func=lambda k: f"{nutrition.ACTIVITY_LEVELS[k][0]} – {nutrition.ACTIVITY_LEVELS[k][2]}",
        index=list(nutrition.ACTIVITY_LEVELS).index(ob["activity"]), key="ob_act",
    )
    blocked = bool(nutrition.goal_weight_issues(ob["goal"], ob["height_cm"], ob["weight_kg"], ob["goal_weight_kg"])) and ob["goal"] == "abnehmen"
    with st.container(horizontal=True):
        if st.button("Zurück", width="stretch"):
            go(-1)
            st.rerun()
        if st.button("Weiter", type="primary", width="stretch", disabled=blocked):
            go(1)
            st.rerun()

# ---------------------------------------------------------------- Schritt 3: Stil
elif step == 3:
    ob["diet_type"] = st.selectbox(
        "Ernährungsform", options=list(nutrition.DIET_TYPES), format_func=nutrition.DIET_TYPES.get,
        index=list(nutrition.DIET_TYPES).index(ob["diet_type"]), key="ob_diet",
    )
    ob["dislikes"] = st.text_input("Was isst du nicht? (optional)", value=ob["dislikes"], placeholder="z. B. Pilze, Koriander, Nüsse", key="ob_dis")
    ob["approx_mode"] = st.toggle(
        "Ungefähr tracken", value=ob["approx_mode"], key="ob_approx",
        help="Portionen als klein/mittel/groß statt in Gramm – schneller, etwas ungenauer.",
    )
    ob["hide_numbers"] = st.toggle(
        "Zahlen ausblenden", value=ob["hide_numbers"] or ob["care_flag"], key="ob_hide",
        help="Tracking ohne Kalorienanzeige – nur Mahlzeiten und Wohlbefinden. Jederzeit im Profil änderbar.",
    )
    ob["ai_consent"] = st.toggle("KI-Funktionen nutzen", value=ob["ai_consent"], key="ob_ai")
    st.html(
        "<p class='kano-small'>Für Freitext- und Foto-Erkennung, Wochenpläne und den Coach werden die jeweils "
        "nötigen Angaben (z. B. dein Text, dein Foto oder eine Zusammenfassung deiner Werte – nie E-Mail oder "
        "Passwort) an die Anthropic API (Claude) übertragen. Das ist freiwillig und im Profil jederzeit "
        "widerrufbar. Ohne KI funktionieren Suche, Barcode und alle Auswertungen weiterhin.</p>"
    )
    with st.container(horizontal=True):
        if st.button("Zurück", width="stretch"):
            go(-1)
            st.rerun()
        if st.button("Weiter", type="primary", width="stretch"):
            go(1)
            st.rerun()

# ---------------------------------------------------------------- Schritt 4: Ergebnis
else:
    age = clock.today().year - int(ob["birth_year"])
    pace = nutrition.PACES[ob["pace"]][1]
    goal = ob["goal"]
    tdee = nutrition.tdee_formula(ob["sex"], ob["weight_kg"], ob["height_cm"], age, ob["activity"])
    result = nutrition.safe_target(tdee, ob["weight_kg"], ob["sex"], goal, pace, height_cm=ob["height_cm"], age=age)
    macros = nutrition.macro_targets(result.target_kcal, ob["weight_kg"], ob["diet_type"], ob["goal_weight_kg"])

    if ob["hide_numbers"]:
        ui.card(
            "Alles bereit",
            "<p class='kano-muted'>Du hast „Zahlen ausblenden“ gewählt. KANO rechnet im Hintergrund weiter, "
            "damit Pläne passen – du siehst aber nur deine Mahlzeiten und dein Wohlbefinden.</p>",
            glow=True,
        )
    else:
        ui.ring(result.target_kcal, result.target_kcal, center_value=ui.fmt_int(result.target_kcal), unit="kcal pro Tag", sub="dein Startziel")
        ui.stats([
            ui.Stat(f"{macros.protein_g} g", "Protein"),
            ui.Stat(f"{macros.carbs_g} g", "Kohlenhydrate"),
            ui.Stat(f"{macros.fat_g} g", "Fett"),
        ])
        bmr = nutrition.bmr_mifflin(ob["sex"], ob["weight_kg"], ob["height_cm"], age)
        ui.card(
            "So entsteht die Zahl",
            ui.item_rows([
                ("Grundumsatz (Mifflin-St-Jeor)", f"{ui.fmt_int(bmr)} kcal"),
                (f"× Aktivität ({nutrition.activity_factor(ob['activity']):.3g})".replace(".", ","), f"{ui.fmt_int(result.tdee)} kcal"),
                ("Defizit" if result.deficit > 0 else ("Überschuss" if result.deficit < 0 else "Anpassung"),
                 f"{'−' if result.deficit > 0 else '+'}{ui.fmt_int(abs(result.deficit))} kcal"),
                ("Tagesziel", f"{ui.fmt_int(result.target_kcal)} kcal"),
            ]),
        )
    for n in result.notes:
        ui.note(n, care=True)
    ui.note(
        "Das ist ein Startwert. Nach 2–3 Wochen mit Gewicht und Tracking berechnet KANO deinen "
        "tatsächlichen Verbrauch und passt das Ziel wöchentlich behutsam an."
    )

    with st.container(horizontal=True):
        if st.button("Zurück", width="stretch"):
            go(-1)
            st.rerun()
        if st.button("Los geht's", type="primary", width="stretch"):
            uid = session.uid()
            repo.update_profile(
                uid,
                name=ob["name"].strip() or None,
                sex=ob["sex"],
                birth_year=int(ob["birth_year"]),
                height_cm=float(ob["height_cm"]),
                activity=ob["activity"],
                goal=goal,
                pace_kg_week=pace,
                goal_weight_kg=ob["goal_weight_kg"],
                diet_type=ob["diet_type"],
                dislikes=ob["dislikes"].strip(),
                hide_numbers=bool(ob["hide_numbers"]),
                approx_mode=bool(ob["approx_mode"]),
                ai_consent=bool(ob["ai_consent"]),
                care_flag=bool(ob["care_flag"]),
                disclaimer_accepted_at=datetime.now(timezone.utc),
                onboarding_done=True,
            )
            repo.upsert_weight(uid, clock.today(), float(ob["weight_kg"]), source="onboarding")
            session.refresh_profile()
            energy.ensure_current(uid, session.profile(), force=True)
            del st.session_state["ob"]
            st.rerun()
