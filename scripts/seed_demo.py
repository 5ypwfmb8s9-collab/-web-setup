"""Legt ein Demo-Konto mit ~5 Wochen realistischer Daten an (zum Ausprobieren und für Screenshots).

Aufruf:  python scripts/seed_demo.py [email] [passwort]
Standard: demo@kano.app / demo1234
"""

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import clock  # noqa: E402
from db import repo  # noqa: E402
from services import auth, energy, planning  # noqa: E402

EMAIL = sys.argv[1] if len(sys.argv) > 1 else "demo@kano.app"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "demo1234"
DAYS = 36

MEALS = {
    "fruehstueck": [
        [("Haferflocken", 60, 222, 8, 35, 4), ("Banane", 120, 112, 1, 24, 0), ("Milch 1,5 %", 200, 94, 7, 10, 3)],
        [("Vollkornbrot", 100, 216, 7.5, 38, 1.5), ("Gouda", 30, 107, 7.5, 0, 8.4), ("Kaffee mit Milch", 250, 40, 2, 3, 2)],
        [("Skyr natur", 250, 158, 27, 10, 0.5), ("Heidelbeeren", 100, 57, 1, 11, 0.3), ("Müsli (ohne Zuckerzusatz)", 40, 144, 4, 24, 3)],
    ],
    "mittag": [
        [("Vollkornnudeln (gekocht)", 250, 350, 14, 65, 3), ("Tomatensoße", 150, 90, 3, 12, 3), ("Parmesan", 15, 60, 5, 0, 4)],
        [("Hähnchenbrust (gegart)", 150, 225, 45, 0, 4.5), ("Reis (gekocht)", 180, 234, 5, 50, 0.5), ("Brokkoli", 200, 68, 6, 6, 1)],
        [("Linsensuppe", 400, 360, 20, 50, 7), ("Brötchen (Weizen)", 55, 149, 5, 29, 1)],
        [("Döner Kebab", 350, 750, 42, 70, 35)],
    ],
    "abend": [
        [("Vollkornbrot", 100, 216, 7.5, 38, 1.5), ("Kochschinken", 40, 44, 7, 0, 1.6), ("Gurke", 100, 12, 0.6, 2, 0.1), ("Frischkäse", 30, 75, 2, 1, 7)],
        [("Lachs (gegart)", 150, 300, 33, 0, 18), ("Kartoffeln (gekocht)", 250, 180, 5, 38, 0.3), ("Blattsalat", 80, 12, 1, 1, 0)],
        [("Pizza Margherita", 350, 875, 35, 105, 32)],
        [("Omelett mit Gemüse", 300, 380, 25, 8, 27)],
    ],
    "snack": [
        [("Apfel", 150, 78, 0.5, 18, 0.3)],
        [("Mandeln", 30, 180, 6, 2, 16)],
        [("Vollmilchschokolade", 30, 162, 2, 17, 9)],
        [("Proteinriegel", 55, 198, 18, 19, 7)],
    ],
}


def _ing(name, qty, unit, section):
    return {"name": name, "qty": qty, "unit": unit, "section": section}


def demo_plan(start):
    """Statischer Beispielplan (so sieht eine Claude-Antwort aus) – nur für die Demo."""
    breakfast = {"slot": "fruehstueck", "time": "07:30", "name": "Overnight Oats mit Beeren", "kcal": 390, "protein": 22,
                 "carbs": 52, "fat": 9, "instructions": "Haferflocken mit Skyr und Milch verrühren, über Nacht kühlen, Beeren darauf.",
                 "prep": "", "ingredients": [_ing("Haferflocken", 50, "g", "Trockenware"), _ing("Skyr", 150, "g", "Kühlregal"),
                                             _ing("Milch 1,5 %", 100, "ml", "Kühlregal"), _ing("Beerenmischung TK", 80, "g", "Tiefkühl")]}
    prep_lunch = {"slot": "mittag", "time": "12:30", "name": "Linsen-Gemüse-Curry mit Reis", "kcal": 560, "protein": 24,
                  "carbs": 80, "fat": 14, "instructions": "Zwiebel und Gemüse anbraten, Linsen, Tomaten und Kokosmilch dazu, 20 Min köcheln.",
                  "prep": "Meal-Prep: für 3 Tage kochen",
                  "ingredients": [_ing("Rote Linsen", 240, "g", "Trockenware"), _ing("Reis", 210, "g", "Trockenware"),
                                  _ing("Kokosmilch", 400, "ml", "Konserven & Gläser"), _ing("Tomaten gehackt (Dose)", 400, "g", "Konserven & Gläser"),
                                  _ing("Zwiebeln", 150, "g", "Obst & Gemüse"), _ing("Karotten", 300, "g", "Obst & Gemüse"),
                                  _ing("Spinat TK", 300, "g", "Tiefkühl")]}
    reheat = {**prep_lunch, "prep": "vorgekocht", "ingredients": []}
    dinners = [
        ("Ofengemüse mit Feta", [_ing("Paprika", 150, "g", "Obst & Gemüse"), _ing("Zucchini", 200, "g", "Obst & Gemüse"), _ing("Feta", 75, "g", "Kühlregal"), _ing("Kartoffeln", 250, "g", "Obst & Gemüse")], 520),
        ("Vollkornbrot mit Hüttenkäse & Gurke", [_ing("Vollkornbrot", 100, "g", "Brot & Backwaren"), _ing("Hüttenkäse", 150, "g", "Kühlregal"), _ing("Gurke", 0.5, "Stk", "Obst & Gemüse")], 430),
        ("Hähnchen-Wraps mit Salat", [_ing("Tortilla-Wraps", 2, "Stk", "Brot & Backwaren"), _ing("Hähnchenbrustfilet", 150, "g", "Fleisch & Fisch"), _ing("Eisbergsalat", 0.25, "Stk", "Obst & Gemüse"), _ing("Joghurt natur", 50, "g", "Kühlregal")], 580),
    ]
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        dn, ings, kcal = dinners[i % 3]
        lunch = prep_lunch if i in (0, 3) else (reheat if i in (1, 2, 4, 5) else {**prep_lunch, "name": "Nudeln mit Tomatensoße", "prep": "", "ingredients": [_ing("Vollkornnudeln", 90, "g", "Trockenware"), _ing("Passierte Tomaten", 200, "g", "Konserven & Gläser")]})
        days.append({"date": d.isoformat(), "shift": "frei", "meals": [
            breakfast, lunch,
            {"slot": "snack", "time": "15:30", "name": "Apfel & Mandeln", "kcal": 180, "protein": 5, "carbs": 20, "fat": 9,
             "instructions": "", "prep": "", "ingredients": [_ing("Äpfel", 150, "g", "Obst & Gemüse"), _ing("Mandeln", 15, "g", "Trockenware")]},
            {"slot": "abend", "time": "18:30", "name": dn, "kcal": kcal, "protein": 30, "carbs": 45, "fat": 18,
             "instructions": "Einfach und in 20 Minuten fertig.", "prep": "", "ingredients": ings},
        ]})
    return {"days": days, "prep_notes": "Sonntag und Mittwoch das Linsen-Curry für je 3 Tage kochen und portioniert kühlen.",
            "estimated_cost_eur": 31.5, "tips": "Overnight Oats abends vorbereiten – morgens spart das Zeit."}


def main() -> None:
    random.seed(7)
    existing = repo.get_user_by_email(EMAIL)
    if existing:
        repo.delete_user(existing["id"])
    uid = auth.register(EMAIL, PASSWORD)
    repo.update_profile(
        uid, name="Alex", sex="w", birth_year=1991, height_cm=168, activity="leicht", goal="abnehmen",
        pace_kg_week=0.5, goal_weight_kg=68, diet_type="ausgewogen", dislikes="Pilze", ai_consent=True,
        household_size=2, weekly_budget_eur=70, onboarding_done=True, disclaimer_accepted_at=datetime.now(timezone.utc),
    )
    today = clock.today()
    start = today - timedelta(days=DAYS)
    weight = 78.4
    for i in range(DAYS + 1):
        d = start + timedelta(days=i)
        weight -= 0.055  # ~0,4 kg/Woche
        if random.random() < 0.75 or i in (0, DAYS):
            repo.upsert_weight(uid, d, round(weight + random.uniform(-0.6, 0.6), 1))
        if d == today:
            continue
        if random.random() < 0.85:
            light_lunch = d.weekday() in (1, 3) and random.random() < 0.8  # Muster: Di/Do wenig Mittag
            for meal, options in MEALS.items():
                if meal == "snack" and random.random() < 0.4:
                    continue
                pick = options[0] if (meal == "mittag" and light_lunch) else random.choice(options)
                items = [{"name": n, "grams": g, "size_label": "mittel", "kcal": k, "protein": p, "carbs": c, "fat": f} for n, g, k, p, c, f in pick]
                if meal == "mittag" and light_lunch:
                    items = [{**it, "kcal": it["kcal"] * 0.5, "grams": it["grams"] * 0.5} for it in items]
                if meal == "abend" and light_lunch:
                    items.append({"name": "Chips", "grams": 60, "size_label": "mittel", "kcal": 324, "protein": 4, "carbs": 30, "fat": 20})
                repo.add_entries(uid, d, meal, items, "freitext")
        repo.upsert_wellbeing(uid, d, energy=random.randint(5, 8), mood=random.randint(5, 9), hunger=random.randint(3, 7),
                              sleep_hours=random.choice([6, 6.5, 7, 7.5, 8]), sleep_quality=random.randint(5, 8),
                              waist_cm=round(88 - i * 0.06, 1) if i % 7 == 0 else None)
        if d.weekday() in (0, 3):
            repo.add_strength(uid, d, "Kniebeuge", 30 + i * 0.4, 8)
            repo.add_strength(uid, d, "Liegestütze", None, 8 + i // 6)
    # Heute: Frühstück schon eingetragen
    repo.add_entries(uid, today, "fruehstueck", [{"name": n, "grams": g, "size_label": "mittel", "kcal": k, "protein": p, "carbs": c, "fat": f}
                                               for n, g, k, p, c, f in MEALS["fruehstueck"][0]], "favorit")
    repo.add_favorite(uid, "Haferflocken-Frühstück", "fruehstueck", [{"name": n, "grams": g, "kcal": k, "protein": p, "carbs": c, "fat": f} for n, g, k, p, c, f in MEALS["fruehstueck"][0]])
    # Energieziele wöchentlich nachrechnen, als wäre die App die ganze Zeit genutzt worden
    profile = repo.get_profile(uid)
    week = clock.week_start(start)
    while week <= today:
        energy.ensure_current(uid, profile, on=week, force=True)
        week += timedelta(days=7)
    repo.upsert_exception(uid, clock.week_start(today) + timedelta(days=5), 2600, "Geburtstag von Sam")
    plan = demo_plan(today)
    plan_id = repo.save_plan(uid, clock.week_start(today), {"start": today.isoformat(), "days": 7, "persons": 2,
                                                            "budget_eur": 70, "meal_prep": True}, plan)
    planning.rebuild_shopping(uid, plan_id, plan, 2)
    print(f"Demo-Konto angelegt: {EMAIL} / {PASSWORD} (User-ID {uid})")


if __name__ == "__main__":
    main()
