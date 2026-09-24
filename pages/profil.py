"""Profil: Körperdaten & Ziel, Einstellungen, Import/Export, Konto & Datenschutz."""

from datetime import timedelta

import streamlit as st

from core import clock, features, nutrition
from db import repo
from services import ai, auth, energy, exporter, importer
from ui import components as ui
from ui import session, theme

uid = session.uid()
profile = session.profile()
user = session.user_row()
today = clock.today()

theme.page_title(profile.get("name") or "Profil", user.get("email"))
tab_profile, tab_settings, tab_data, tab_account = st.tabs(["Profil", "Einstellungen", "Daten", "Konto"])

# ================================================================ Profil & Ziel
with tab_profile:
    with st.form("profile_form", border=False):
        name = st.text_input("Name (optional)", value=profile.get("name") or "", max_chars=40)
        sex = st.segmented_control("Geschlecht", list(nutrition.SEX_LABELS), format_func=nutrition.SEX_LABELS.get,
                                   default=profile.get("sex") or "d", required=True, width="stretch")
        with st.container(horizontal=True):
            birth_year = st.number_input("Geburtsjahr", min_value=today.year - 100, max_value=today.year - 12,
                                         value=int(profile.get("birth_year") or 1990), step=1)
            height = st.number_input("Größe (cm)", min_value=120.0, max_value=230.0, value=float(profile.get("height_cm") or 170), step=1.0, format="%.0f")
        activity = st.selectbox("Aktivität im Alltag", list(nutrition.ACTIVITY_LEVELS),
                                format_func=lambda k: nutrition.ACTIVITY_LEVELS[k][0],
                                index=list(nutrition.ACTIVITY_LEVELS).index(profile.get("activity") or "leicht"))
        care = bool(profile.get("care_flag"))
        goal_options = ["halten", "aufbauen"] if care or today.year - int(birth_year) < 18 else list(nutrition.GOALS)
        current_goal = profile.get("goal") if profile.get("goal") in goal_options else goal_options[0]
        goal = st.segmented_control("Ziel", goal_options, format_func=nutrition.GOALS.get, default=current_goal, required=True, width="stretch")
        pace_key = next((k for k, (_, v) in nutrition.PACES.items() if v == profile.get("pace_kg_week")), "normal")
        pace = st.radio("Tempo beim Abnehmen", list(nutrition.PACES), format_func=lambda k: nutrition.PACES[k][0],
                        index=list(nutrition.PACES).index(pace_key), horizontal=False)
        goal_weight = st.number_input("Zielgewicht (kg, 0 = keins)", min_value=0.0, max_value=300.0,
                                      value=float(profile.get("goal_weight_kg") or 0), step=0.5, format="%.1f")
        diet = st.selectbox("Ernährungsform", list(nutrition.DIET_TYPES), format_func=nutrition.DIET_TYPES.get,
                            index=list(nutrition.DIET_TYPES).index(profile.get("diet_type") or "ausgewogen"))
        dislikes = st.text_input("Abneigungen", value=profile.get("dislikes") or "", placeholder="z. B. Pilze, Koriander")
        submitted = st.form_submit_button("Speichern & Ziel neu berechnen", type="primary", width="stretch")
    if care:
        ui.note("Du hast angegeben, dass eine besondere Situation zutrifft (z. B. Schwangerschaft oder Essstörung). "
                "Deshalb plant KANO kein Defizit. Das kannst du unter <b>Einstellungen</b> ändern.", care=True)
    if submitted:
        weight_now = session.current_weight() or 70.0
        issues = nutrition.goal_weight_issues(goal, height, weight_now, goal_weight or None) if goal == "abnehmen" else []
        if issues:
            for i in issues:
                ui.note(i, care=True)
        else:
            session.update_profile(
                name=name.strip() or None, sex=sex, birth_year=int(birth_year), height_cm=float(height), activity=activity,
                goal=goal, pace_kg_week=nutrition.PACES[pace][1], goal_weight_kg=goal_weight or None,
                diet_type=diet, dislikes=dislikes.strip(),
            )
            energy.ensure_current(uid, session.profile(), force=True)
            st.toast("Profil gespeichert – Ziel neu berechnet", icon=":material/check_circle:")
            st.rerun()

# ================================================================ Einstellungen
with tab_settings:

    def setting(field: str, label: str, help_text: str) -> None:
        def save():
            session.update_profile(**{field: st.session_state[f"set_{field}"]})

        st.toggle(label, value=bool(profile.get(field)), key=f"set_{field}", help=help_text, on_change=save)

    setting("hide_numbers", "Zahlen ausblenden", "Tracking ohne Kalorienanzeige – nur Mahlzeiten und Wohlbefinden.")
    setting("approx_mode", "Ungefähr tracken", "Portionen als klein/mittel/groß statt in Gramm.")
    setting("ai_consent", "KI-Funktionen nutzen",
            "Freitext, Foto, Wochenplan und Coach senden die nötigen Angaben an die Anthropic API (Claude).")
    if profile.get("ai_consent") and not ai.is_configured():
        st.caption("Hinweis: Auf diesem Server ist noch kein API-Schlüssel hinterlegt.")
    setting("care_flag", "Besondere Situation (kein Defizit)",
            "Schwangerschaft/Stillzeit, (frühere) Essstörung oder ärztlich begleitete Ernährung. KANO plant dann kein Kaloriendefizit.")
    if st.session_state.get("set_care_flag") and profile.get("goal") == "abnehmen":
        session.update_profile(goal="halten")
        energy.ensure_current(uid, session.profile(), force=True)
        st.rerun()
    st.divider()
    with st.form("household", border=False):
        hh = st.number_input("Personen im Haushalt (Einkaufsliste)", min_value=1, max_value=8, value=int(profile.get("household_size") or 1))
        budget = st.number_input("Wochenbudget für Lebensmittel (€, 0 = keins)", min_value=0.0, max_value=1000.0,
                                 value=float(profile.get("weekly_budget_eur") or 0), step=5.0)
        if st.form_submit_button("Speichern", width="stretch"):
            session.update_profile(household_size=int(hh), weekly_budget_eur=budget or None)
            st.toast("Gespeichert", icon=":material/check_circle:")

# ================================================================ Daten: Import & Export
with tab_data:
    ui.label("Importieren")
    st.caption("Gewicht und Aktivität aus Apple Health (export.xml), Google Fit, Garmin, Withings, Fitbit oder "
               "einer smarten Waage – als CSV-Export. KANO erkennt die Spalten automatisch.")
    up = st.file_uploader("CSV oder Apple-Health-XML", type=["csv", "txt", "xml"], key="import_file", label_visibility="collapsed")
    if up is not None:
        result = importer.parse(up.name, up.getvalue())
        for w in result.warnings:
            ui.note(ui.esc(w))
        if result.detected:
            st.caption("Erkannt: " + ", ".join(f"{k} = „{v}“" for k, v in result.detected.items()))
        if result.weights or result.activities:
            ui.stats([ui.Stat(str(len(result.weights)), "Gewichtswerte"), ui.Stat(str(len(result.activities)), "Aktivitätstage")])
            if result.weights:
                first, last = result.weights[0], result.weights[-1]
                st.caption(f"Zeitraum Gewicht: {first[0].strftime('%d.%m.%Y')} – {last[0].strftime('%d.%m.%Y')}")
            overwrite = st.checkbox("Vorhandene Gewichtswerte an gleichen Tagen überschreiben", value=False)
            if st.button("Importieren", type="primary", width="stretch", icon=":material/upload:"):
                existing = {w["date"] for w in repo.list_weights(uid)}
                n = 0
                for d, kg in result.weights:
                    if overwrite or d not in existing:
                        repo.upsert_weight(uid, d, kg, source="import")
                        n += 1
                known_acts = {(a["date"], a["kind"]) for a in repo.list_activities(uid)}
                new_acts = [a for a in result.activities if (a["date"], a["kind"]) not in known_acts]
                repo.add_activities(uid, new_acts)
                energy.ensure_current(uid, session.profile(), force=True)
                st.success(f"{n} Gewichtswerte und {len(new_acts)} Aktivitätstage importiert.", icon=":material/check_circle:")

    st.divider()
    ui.label("Exportieren")
    st.caption("Für dich, deine Ernährungsberatung oder deine Arztpraxis.")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        rep_start = st.date_input("Von", value=today - timedelta(days=27), max_value=today, format="DD.MM.YYYY")
        rep_end = st.date_input("Bis", value=today, max_value=today, format="DD.MM.YYYY")
    if session.hide_numbers():
        st.caption("Hinweis: Der Bericht enthält Zahlen (Kalorien, Gewicht), auch wenn sie in der App ausgeblendet sind.")
    if st.button("PDF-Bericht erstellen", width="stretch", icon=":material/picture_as_pdf:"):
        st.session_state.pdf_bytes = exporter.pdf_report(uid, profile, rep_start, rep_end)
    if st.session_state.get("pdf_bytes"):
        st.download_button("PDF herunterladen", st.session_state.pdf_bytes, file_name=f"KANO-Bericht-{rep_end.isoformat()}.pdf",
                           mime="application/pdf", type="primary", width="stretch", icon=":material/download:")
    st.download_button("Ernährungstagebuch (CSV)", exporter.diary_csv(uid, rep_start, rep_end), file_name=f"KANO-Tagebuch-{rep_end.isoformat()}.csv",
                       mime="text/csv", width="stretch", icon=":material/table:")
    if st.button("Alle meine Daten exportieren (ZIP)", width="stretch", icon=":material/folder_zip:"):
        st.session_state.zip_bytes = exporter.csv_zip(uid)
    if st.session_state.get("zip_bytes"):
        st.download_button("ZIP herunterladen", st.session_state.zip_bytes, file_name=f"KANO-Daten-{today.isoformat()}.zip",
                           mime="application/zip", type="primary", width="stretch", icon=":material/download:")

# ================================================================ Konto
with tab_account:
    tier = user.get("tier") or "free"
    ui.card(f"KANO {features.LABELS.get(tier, tier)}",
            "<p class='kano-muted'>Aktuell sind alle Funktionen freigeschaltet. Tracking, Tagesübersicht und "
            "Gewichtstrend bleiben auch in Zukunft dauerhaft kostenlos.</p>")

    with st.expander("Passwort ändern", icon=":material/key:"):
        with st.form("pw_form", border=False, clear_on_submit=True):
            old_pw = st.text_input("Aktuelles Passwort", type="password", autocomplete="current-password")
            new_pw = st.text_input("Neues Passwort", type="password", autocomplete="new-password")
            if st.form_submit_button("Passwort ändern", width="stretch"):
                try:
                    auth.change_password(uid, old_pw, new_pw)
                except auth.AuthError as exc:
                    st.info(str(exc))
                else:
                    st.success("Passwort geändert.")

    with st.expander("Datenschutz & Hinweise", icon=":material/shield:"):
        st.markdown(
            """
- **Deine Gesundheitsdaten** (Gewicht, Essen, Wohlbefinden) werden nur für deine Auswertungen gespeichert.
- **Passwörter** werden nur als sicherer Hash (scrypt) gespeichert, nie im Klartext.
- **KI-Funktionen** sind freiwillig. Wenn aktiv, gehen nur die jeweils nötigen Angaben an die Anthropic API:
  dein Text/Foto zur Erkennung bzw. eine *Zusammenfassung* deiner Werte für Coach und Pläne – nie E-Mail,
  Passwort oder Name. Fotos werden nicht gespeichert.
- **Lebensmitteldaten** stammen von Open Food Facts (offene Datenbank); dabei wird nur der Suchbegriff bzw. Barcode übertragen.
- **Export & Löschen:** Du kannst jederzeit alle Daten exportieren und dein Konto vollständig löschen.
- KANO ist **kein Medizinprodukt** und ersetzt keine ärztliche oder ernährungstherapeutische Beratung.
"""
        )

    if st.button("Abmelden", width="stretch", icon=":material/logout:"):
        session.sign_out()
        st.rerun()

    with st.expander("Konto löschen", icon=":material/delete_forever:"):
        st.markdown("Das löscht **dein Konto und alle Daten unwiderruflich** – Tagebuch, Gewicht, Pläne, Chat, alles. "
                    "Tipp: Exportiere vorher deine Daten.")
        with st.form("delete_form", border=False):
            confirm = st.text_input("Zur Bestätigung „LÖSCHEN“ eingeben")
            pw = st.text_input("Passwort", type="password", autocomplete="current-password")
            if st.form_submit_button("Konto endgültig löschen", width="stretch"):
                if confirm.strip().upper() != "LÖSCHEN":
                    st.info("Bitte „LÖSCHEN“ eingeben.")
                elif not auth.verify_password(pw, user.get("password_hash", "")):
                    st.info("Das Passwort stimmt nicht.")
                else:
                    repo.delete_user(uid)
                    session.sign_out()
                    st.rerun()
