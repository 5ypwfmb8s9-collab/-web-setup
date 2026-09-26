"""Gemeinsame Eingabemasken fürs Tracking.

Alle Wege (Freitext, Foto, Suche, Barcode, manuell) landen in einer „Mahlzeit in Arbeit“
(`st.session_state.pending`). Dort kann man mit einem Tipp korrigieren und dann alles
gemeinsam als eine Mahlzeit eintragen.
"""

from __future__ import annotations

import streamlit as st

from core import portions
from core.meals import MEALS
from db import repo
from ui import components as ui
from ui import session

PENDING = "pending"


# --------------------------------------------------------------------------- Mahlzeit in Arbeit


def pending() -> dict:
    return st.session_state.setdefault(PENDING, {"items": [], "sources": set(), "note": "", "text": "", "version": 0})


def add_pending(items: list[dict], source: str, note: str = "", text: str = "") -> None:
    p = pending()
    for it in items:
        p["items"].append({**it, "_source": source})
    p["sources"].add(source)
    p["version"] += 1
    if note:
        p["note"] = note
    if text:
        p["text"] = text


def clear_pending() -> None:
    st.session_state.pop(PENDING, None)


def _main_source(sources: set[str]) -> str:
    for s in ("foto", "freitext", "barcode", "suche", "favorit", "manuell"):
        if s in sources:
            return s
    return "manuell"


def pending_card(day, meal: str) -> None:
    """Bestätigen/Korrigieren der Mahlzeit in Arbeit und Eintragen.

    Pro Lebensmittel genügt ein Tipp zum Korrigieren: ± an der Menge bzw. klein/mittel/groß.
    Die Nährwerte werden aus der ursprünglichen Schätzung proportional mitgerechnet.
    """
    p = pending()
    if not p["items"]:
        return
    hide = session.hide_numbers()
    approx = session.approx_mode()
    v = p["version"]

    with st.container(key="glowcard_pending"):
        ui.label(f"{MEALS[meal]} · kurz prüfen")
        if p.get("note"):
            st.caption(p["note"])

        current: list[dict] = []
        for idx, it in enumerate(p["items"]):
            base_grams = float(it.get("grams") or 0)
            key = f"pi_{v}_{idx}"
            if base_grams <= 0:
                # z. B. manuell ohne Menge: direkt kcal anpassen
                kcal = float(st.session_state.get(f"{key}_k", it.get("kcal") or 0))
                item = {**it, "kcal": kcal}
            elif approx:
                base_size = it.get("size_label") or "mittel"
                size = st.session_state.get(f"{key}_s", base_size) or base_size
                grams = round(base_grams * portions.SIZE_FACTORS[size] / portions.SIZE_FACTORS[base_size])
                item = {**portions.scale_item(it, grams), "size_label": size}
            else:
                grams = float(st.session_state.get(f"{key}_g", base_grams))
                item = portions.scale_item(it, grams)
            current.append(item)

            detail = "" if hide else f"{ui.fmt_int(item.get('kcal'))} kcal"
            st.html(f'<div class="kano-item" style="border:none;padding:10px 0 2px 0"><span class="n"><b>{ui.esc(item["name"])}</b></span>'
                    f'<span class="d">{detail}</span></div>')
            with st.container(horizontal=True, vertical_alignment="bottom", key=f"pi_row_{v}_{idx}"):
                if base_grams <= 0:
                    if not hide:
                        st.number_input("kcal", min_value=0.0, max_value=5000.0, value=float(it.get("kcal") or 0), step=10.0,
                                        key=f"{key}_k", label_visibility="collapsed", width="stretch")
                    else:
                        st.caption("Menge unbekannt")
                elif approx:
                    st.segmented_control("Größe", options=list(portions.SIZES), format_func=portions.SIZES.get,
                                         default=it.get("size_label") or "mittel", required=True, key=f"{key}_s",
                                         label_visibility="collapsed", width="stretch")
                else:
                    step = 5.0 if base_grams < 60 else (10.0 if base_grams < 300 else 25.0)
                    st.number_input("Menge (g)", min_value=0.0, max_value=5000.0, value=base_grams, step=step,
                                    key=f"{key}_g", label_visibility="collapsed", width="stretch", format="%.0f",
                                    icon=":material/scale:")
                if st.button("", key=f"{key}_del", icon=":material/close:", type="tertiary", help="Entfernen"):
                    p["items"].pop(idx)
                    p["version"] += 1
                    st.rerun()

        if not hide:
            total = sum(i.get("kcal") or 0 for i in current)
            st.caption(f"Zusammen ≈ {ui.fmt_int(total)} kcal")

        # Nachbessern in einem Satz (nur für KI-Schätzungen)
        if p.get("text") and session.ai_allowed():
            with st.form(f"refine_{v}", border=False):
                fix = st.text_input("Nachbessern", placeholder="z. B. „nur 1 Scheibe Brot, Käse war Camembert“", label_visibility="collapsed")
                if st.form_submit_button("Mit KI korrigieren", icon=":material/auto_fix_high:", width="stretch") and fix.strip():
                    from services import ai

                    with st.spinner("Korrigiere …"):
                        try:
                            est = ai.estimate_from_text(f"{p['text']}\nKorrektur des Nutzers: {fix}", approx=approx)
                        except ai.AIError as exc:
                            st.info(str(exc), icon=":material/cloud_off:")
                        else:
                            others = [i for i in current if i.get("_source") not in ("freitext", "foto")]
                            text = p["text"]
                            clear_pending()
                            if others:
                                add_pending(others, "suche")
                            add_pending([x.model_dump() for x in est.items if x.name], "freitext", est.note,
                                        text=f"{text}\nKorrektur: {fix}")
                            st.rerun()

        save_fav = st.toggle("Als Favorit merken", key=f"pending_fav_{v}")
        fav_name = ""
        if save_fav:
            fav_name = st.text_input("Name des Favoriten", value=", ".join(i["name"] for i in current[:2]) or MEALS[meal],
                                     key=f"pending_fav_name_{v}")

        with st.container(horizontal=True):
            if st.button("Verwerfen", width="stretch", key="pending_discard"):
                clear_pending()
                st.rerun()
            if st.button("Eintragen", type="primary", width="stretch", key="pending_save", icon=":material/check:"):
                clean = [{k: val for k, val in i.items() if not k.startswith("_")} for i in current]
                repo.add_entries(session.uid(), day, meal, clean, _main_source(p["sources"]))
                if save_fav and fav_name.strip():
                    repo.add_favorite(session.uid(), fav_name.strip(), meal, clean)
                clear_pending()
                st.toast(f"{MEALS[meal]} eingetragen", icon=":material/check_circle:")
                st.rerun()


# --------------------------------------------------------------------------- Menge wählen


def amount_picker(food: dict, key: str) -> dict | None:
    """Menge für ein Lebensmittel wählen; gibt fertigen Eintrag zurück, sobald „Hinzufügen“ gedrückt wird."""
    hide = session.hide_numbers()
    title = food["name"] + (f" · {food['brand']}" if food.get("brand") else "")
    with st.container(key=f"card_amount_{key}"):
        st.markdown(f"**{title}**")
        if not hide:
            st.caption(
                f"je 100 g: {ui.fmt_int(food['kcal_100g'])} kcal · P {ui.fmt_num(food.get('protein_100g') or 0)} g · "
                f"KH {ui.fmt_num(food.get('carbs_100g') or 0)} g · F {ui.fmt_num(food.get('fat_100g') or 0)} g"
            )
        if session.approx_mode():
            size = st.segmented_control(
                "Größe", options=list(portions.SIZES), format_func=portions.SIZES.get, default="mittel",
                required=True, key=f"size_{key}", width="stretch",
            )
            grams = portions.grams_for_size(food, size)
            unit = food.get("unit")
            st.caption(f"≈ {ui.fmt_int(grams)} g" + (f" ({unit})" if unit else ""))
        else:
            default = float(food.get("serving_g") or 100)
            grams = st.number_input("Menge (g bzw. ml)", min_value=1.0, max_value=5000.0, value=default, step=10.0, key=f"grams_{key}")
            size = portions.size_from_grams(grams, food)
        n = portions.nutrients_for(food, grams)
        if not hide:
            st.caption(f"= {ui.fmt_int(n['kcal'])} kcal · P {ui.fmt_num(n['protein'])} g · KH {ui.fmt_num(n['carbs'])} g · F {ui.fmt_num(n['fat'])} g")
        if st.button("Hinzufügen", type="primary", width="stretch", key=f"add_{key}", icon=":material/add:"):
            return {
                "name": food["name"] if not food.get("brand") else f"{food['name']} ({food['brand']})",
                "grams": grams,
                "size_label": size,
                "food_id": food.get("id"),
                **n,
            }
    return None


def custom_food_form(key: str, barcode: str | None = None) -> dict | None:
    """Eigenes Produkt anlegen (z. B. wenn der Barcode unbekannt ist)."""
    with st.form(f"custom_{key}", border=False):
        name = st.text_input("Produktname")
        brand = st.text_input("Marke (optional)")
        kcal = st.number_input("kcal je 100 g", min_value=0.0, max_value=950.0, value=0.0, step=1.0)
        with st.container(horizontal=True):
            protein = st.number_input("Protein", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
            carbs = st.number_input("KH", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
            fat = st.number_input("Fett", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
        serving = st.number_input("Übliche Portion (g)", min_value=1.0, max_value=2000.0, value=100.0, step=5.0)
        if st.form_submit_button("Produkt speichern", type="primary", width="stretch"):
            if not name.strip() or kcal <= 0:
                st.info("Bitte mindestens Name und kcal angeben.")
                return None
            food = {
                "name": name.strip(), "brand": brand.strip() or None, "barcode": barcode,
                "kcal_100g": kcal, "protein_100g": protein, "carbs_100g": carbs, "fat_100g": fat,
                "serving_g": serving,
            }
            food_id = repo.add_custom_food(session.uid(), food)
            return repo.get_food(food_id)
    return None
