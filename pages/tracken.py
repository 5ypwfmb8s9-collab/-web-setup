"""Tracken: Freitext, Suche, Barcode, Foto, Favoriten – alles landet in einer Mahlzeit zum Bestätigen."""

from datetime import timedelta

import streamlit as st

from core import basic_foods, clock, patterns
from core.meals import MEALS, MEALS_SHORT, guess_meal
from db import repo
from services import ai, barcode, openfoodfacts, schedule_service
from ui import components as ui
from ui import food_forms as ff
from ui import session, theme

uid = session.uid()
approx = session.approx_mode()
hide = session.hide_numbers()

theme.page_title("Tracken", "Schreib einfach, was du gegessen hast – den Rest schätzt KANO.")

# ---------------------------------------------------------------- Datum & Mahlzeit
today = clock.today()
day_choice = st.segmented_control(
    "Tag", options=["heute", "gestern", "anderer"], format_func={"heute": "Heute", "gestern": "Gestern", "anderer": "Datum …"}.get,
    default="heute", required=True, key="track_day", label_visibility="collapsed", width="stretch",
)
if day_choice == "gestern":
    day = today - timedelta(days=1)
elif day_choice == "anderer":
    day = st.date_input("Datum", value=today, max_value=today, format="DD.MM.YYYY", key="track_date")
else:
    day = today

meal_times = schedule_service.meal_times_for(uid, session.profile(), day)
if "track_meal" not in st.session_state:
    st.session_state.track_meal = guess_meal(clock.now(), meal_times)
meal = st.segmented_control(
    "Mahlzeit", options=list(MEALS), format_func=MEALS_SHORT.get, required=True, key="track_meal",
    label_visibility="collapsed", width="stretch",
)

ff.pending_card(day, meal)

ai_ready = ai.is_configured() and session.ai_allowed()


def ai_unavailable_note() -> None:
    if not session.ai_allowed():
        ui.note("KI-Funktionen sind in deinem Profil ausgeschaltet. Du kannst sie unter <b>Profil → Einstellungen</b> aktivieren – oder die Suche und den Barcode nutzen.")
    else:
        ui.note("Die KI ist gerade nicht eingerichtet. Suche, Barcode und Favoriten funktionieren trotzdem.")


tab_text, tab_search, tab_code, tab_photo, tab_fav = st.tabs(["Text", "Suche", "Barcode", "Foto", "Favoriten"])

# ---------------------------------------------------------------- Freitext
with tab_text:
    if not ai_ready:
        ai_unavailable_note()
    with st.form("freetext", border=False, clear_on_submit=True):
        text = st.text_area(
            "Was hast du gegessen?",
            placeholder="z. B. 2 Scheiben Vollkornbrot mit Käse und ein Kaffee mit Milch",
            height=110,
            label_visibility="collapsed",
            disabled=not ai_ready,
        )
        st.caption("Tipp: Mit dem Mikrofon deiner Handytastatur kannst du auch einfach diktieren.")
        go = st.form_submit_button("Erkennen", type="primary", width="stretch", icon=":material/auto_awesome:", disabled=not ai_ready)
    if go and text.strip():
        with st.spinner("Schätze Mengen und Nährwerte …"):
            try:
                est = ai.estimate_from_text(text, approx=approx)
            except ai.AIError as exc:
                st.info(str(exc), icon=":material/cloud_off:")
            else:
                items = [i.model_dump() for i in est.items if i.name]
                if items:
                    ff.add_pending(items, "freitext", est.note, text=text)
                    st.rerun()
                st.info("Ich konnte darin kein Essen erkennen – magst du es anders formulieren?")

# ---------------------------------------------------------------- Suche
with tab_search:
    with st.form("search", border=False):
        query = st.text_input("Lebensmittel suchen", placeholder="z. B. Haferflocken, Skyr, Banane", label_visibility="collapsed")
        searched = st.form_submit_button("Suchen", width="stretch", icon=":material/search:")
    if searched:
        st.session_state.search_query = query.strip()
        st.session_state.pop("search_pick", None)
    q = st.session_state.get("search_query", "")
    if q:
        results: list[dict] = [f.as_food() for f in basic_foods.search(q, limit=6)]
        results += repo.search_foods_local(q, uid, limit=10)
        online_error = None
        if len(results) < 12:
            try:
                results += openfoodfacts.search(q)
            except openfoodfacts.OFFError as exc:
                online_error = str(exc)
        seen, unique = set(), []
        for r in results:
            k = (r["name"].lower(), (r.get("brand") or "").lower())
            if k not in seen:
                seen.add(k)
                unique.append(r)
        if online_error:
            st.caption(f"{online_error} Es werden nur gespeicherte Treffer angezeigt.")
        if not unique:
            st.info("Nichts gefunden. Versuch einen allgemeineren Begriff – oder trag es unten manuell ein.")
        for idx, food in enumerate(unique[:18]):
            label = food["name"] + (f" · {food['brand']}" if food.get("brand") else "")
            if not hide:
                label += f"  —  {ui.fmt_int(food['kcal_100g'])} kcal/100 g"
            if st.button(label, key=f"res_{idx}", width="stretch"):
                st.session_state.search_pick = food
        pick = st.session_state.get("search_pick")
        if pick:
            item = ff.amount_picker(pick, "search")
            if item:
                ff.add_pending([item], "suche")
                st.session_state.pop("search_pick", None)
                st.rerun()

    with st.expander("Manuell eintragen"):
        with st.form("manual", border=False, clear_on_submit=True):
            m_name = st.text_input("Was?", placeholder="z. B. Stück Kuchen beim Bäcker")
            m_kcal = st.number_input("kcal (geschätzt)", min_value=0, max_value=5000, value=0, step=10)
            if st.form_submit_button("Hinzufügen", width="stretch") and m_name.strip():
                ff.add_pending([{"name": m_name.strip(), "grams": None, "size_label": "mittel", "kcal": m_kcal,
                                 "protein": 0, "carbs": 0, "fat": 0}], "manuell")
                st.rerun()

# ---------------------------------------------------------------- Barcode
with tab_code:
    mode = st.segmented_control(
        "Quelle", ["foto", "kamera", "nummer"], format_func={"foto": "Foto", "kamera": "Kamera", "nummer": "Nummer"}.get,
        default="foto", required=True, key="code_mode", label_visibility="collapsed", width="stretch",
    )
    code = None
    if mode == "nummer":
        with st.form("code_form", border=False):
            typed = st.text_input("Barcode-Nummer", placeholder="z. B. 4000417025005", max_chars=14)
            if st.form_submit_button("Produkt suchen", width="stretch", icon=":material/search:"):
                code = "".join(ch for ch in typed if ch.isdigit())
    else:
        if mode == "kamera":
            img = st.camera_input("Barcode fotografieren", key="code_cam", label_visibility="collapsed")
        else:
            img = st.file_uploader("Foto vom Barcode", type=["jpg", "jpeg", "png", "webp"], key="code_upload",
                                   help="Auf dem Handy öffnet sich direkt die Kamera.")
        if img is not None:
            data = img.getvalue()
            sig = hash(data)
            if st.session_state.get("code_sig") != sig:
                st.session_state.code_sig = sig
                found = barcode.decode(data)
                if not found and ai_ready:
                    with st.spinner("Lese die Ziffern …"):
                        try:
                            found = ai.read_barcode_digits(data) or None
                        except ai.AIError:
                            found = None
                if found and barcode.valid_ean(found):
                    code = found
                else:
                    st.info("Kein Barcode erkannt. Halte die Kamera näher und gerade – oder gib die Nummer ein.")
    if code:
        st.session_state.code_value = code
        st.session_state.pop("code_food", None)
        try:
            st.session_state.code_food = openfoodfacts.lookup_barcode(code, uid)
        except openfoodfacts.OFFError as exc:
            st.info(str(exc), icon=":material/cloud_off:")
            st.session_state.code_food = None
    code_value = st.session_state.get("code_value")
    if code_value:
        food = st.session_state.get("code_food")
        if food:
            item = ff.amount_picker(food, "code")
            if item:
                ff.add_pending([item], "barcode")
                for k in ("code_value", "code_food"):
                    st.session_state.pop(k, None)
                st.rerun()
        else:
            st.caption(f"Barcode {code_value}: Produkt nicht gefunden. Leg es einmal an – danach kennt KANO es.")
            created = ff.custom_food_form("code", barcode=code_value)
            if created:
                st.session_state.code_food = created
                st.rerun()

# ---------------------------------------------------------------- Foto
with tab_photo:
    if not ai_ready:
        ai_unavailable_note()
    else:
        p_mode = st.segmented_control(
            "Quelle", ["foto", "kamera"], format_func={"foto": "Foto wählen/aufnehmen", "kamera": "Live-Kamera"}.get,
            default="foto", required=True, key="photo_mode", label_visibility="collapsed", width="stretch",
        )
        if p_mode == "kamera":
            meal_img = st.camera_input("Mahlzeit fotografieren", key="meal_cam", label_visibility="collapsed")
        else:
            meal_img = st.file_uploader("Foto der Mahlzeit", type=["jpg", "jpeg", "png", "webp"], key="meal_upload")
        note = st.text_input("Zusatzinfo (optional)", placeholder="z. B. „mit Sahnesoße“, „halbe Portion gegessen“", key="meal_note")
        if meal_img is not None and st.button("Foto analysieren", type="primary", width="stretch", icon=":material/photo_camera:"):
            with st.spinner("Erkenne Gericht und Portionen …"):
                try:
                    est = ai.estimate_from_photo(meal_img.getvalue(), note, approx=approx)
                except ai.AIError as exc:
                    st.info(str(exc), icon=":material/cloud_off:")
                else:
                    items = [i.model_dump() for i in est.items if i.name]
                    if items:
                        ff.add_pending(items, "foto", est.note, text=f"Foto: {', '.join(i['name'] for i in items)}. {note}")
                        st.rerun()
                    st.info("Auf dem Foto konnte ich kein Essen erkennen.")
        st.caption("Das Foto wird nur zur Erkennung an die KI gesendet und nicht gespeichert.")

# ---------------------------------------------------------------- Favoriten & Muster
with tab_fav:
    recent_entries = repo.get_entries(uid, today - timedelta(days=35), today)
    suggestions = patterns.suggest(recent_entries, day, meal)
    if suggestions:
        ui.label("Vorschläge")
        for i, sug in enumerate(suggestions):
            label = f"{sug.reason}  ·  {sug.title}" + ("" if hide else f"  ·  {ui.fmt_int(sug.kcal)} kcal")
            if st.button(label, key=f"sug_{i}", width="stretch", icon=":material/history:"):
                repo.add_entries(uid, day, meal, sug.items, "favorit")
                st.toast(f"{MEALS[meal]} eingetragen", icon=":material/check_circle:")
                st.rerun()

    favs = repo.list_favorites(uid)
    ui.label("Favoriten")
    if not favs:
        st.caption("Noch keine Favoriten. Beim Eintragen einfach „Als Favorit merken“ aktivieren.")
    for fav in favs:
        kcal = sum(i.get("kcal") or 0 for i in fav["items"])
        with st.container(horizontal=True, vertical_alignment="center"):
            label = fav["name"] + ("" if hide else f"  ·  {ui.fmt_int(kcal)} kcal")
            if st.button(label, key=f"fav_{fav['id']}", width="stretch", icon=":material/star:"):
                repo.add_entries(uid, day, meal, fav["items"], "favorit")
                repo.touch_favorite(uid, fav["id"])
                st.toast(f"„{fav['name']}“ eingetragen", icon=":material/check_circle:")
                st.rerun()
            if st.button("", key=f"favdel_{fav['id']}", icon=":material/delete:", type="tertiary", help="Favorit löschen"):
                repo.delete_favorite(uid, fav["id"])
                st.rerun()

    recent = repo.recent_items(uid, limit=8)
    if recent:
        ui.label("Zuletzt gegessen")
        for r in recent:
            label = r["name"] + ("" if hide else f"  ·  {ui.fmt_int(r['kcal'])} kcal")
            if st.button(label, key=f"recent_{r['id']}", width="stretch"):
                ff.add_pending([{k: r.get(k) for k in ("name", "grams", "size_label", "kcal", "protein", "carbs", "fat", "food_id")}], "favorit")
                st.rerun()
