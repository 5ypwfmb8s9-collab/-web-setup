"""Planung: Einkaufsliste, Preise, Plan-Auftrag und Plan-Erzeugung (Claude gestreamt & gemockt)."""

import json
from datetime import date

import httpx2
import pytest

from core import pricing, schedule, shopping
from db import repo
from services import ai, planning

PLAN = {
    "days": [
        {"date": "2026-09-21", "shift": "frei", "meals": [
            {"slot": "mittag", "time": "12:30", "name": "Curry", "kcal": 500, "protein": 20, "carbs": 60, "fat": 15,
             "instructions": "", "prep": "Meal-Prep: für 3 Tage kochen",
             "ingredients": [{"name": "Rote Linsen", "qty": 240, "unit": "g", "section": "Trockenware"},
                             {"name": "Karotten", "qty": 300, "unit": "g", "section": "Obst & Gemüse"},
                             {"name": "Salz", "qty": 5, "unit": "g", "section": "Gewürze, Öle & Soßen"}]},
        ]},
        {"date": "2026-09-22", "shift": "frei", "meals": [
            {"slot": "mittag", "time": "12:30", "name": "Curry", "kcal": 500, "protein": 20, "carbs": 60, "fat": 15,
             "instructions": "", "prep": "vorgekocht", "ingredients": []},
            {"slot": "abend", "time": "18:30", "name": "Salat", "kcal": 400, "protein": 20, "carbs": 30, "fat": 20, "instructions": "", "prep": "",
             "ingredients": [{"name": "karotten", "qty": 100, "unit": "g", "section": "Obst & Gemüse"},
                             {"name": "Gurke", "qty": 0.5, "unit": "Stk", "section": "Obst & Gemüse"},
                             {"name": "Reis", "qty": 80, "unit": "g", "section": "Unbekannt"}]},
        ]},
    ],
    "prep_notes": "", "estimated_cost_eur": 12.0, "tips": "",
}


def test_aggregate_merges_scales_and_sorts():
    items = shopping.aggregate(PLAN, persons=2)
    by_name = {i["name"].lower(): i for i in items}
    assert by_name["karotten"]["qty"] == 800  # (300 + 100) × 2
    assert by_name["gurke"]["qty"] == 1  # 0,5 × 2 Stück
    assert "salz" not in by_name  # Grundvorrat
    assert by_name["reis"]["section"] == "Trockenware"  # ungültiger Bereich → erraten
    sections = [i["section"] for i in items]
    assert sections == sorted(sections, key=shopping.SECTION_ORDER.index)


def test_guess_section_does_not_confuse_reis_with_ei():
    assert shopping.guess_section("Reis") == "Trockenware"
    assert shopping.guess_section("Eier") == "Kühlregal"


def test_format_qty():
    assert shopping.format_qty(1500, "g") == "1,5 kg"
    assert shopping.format_qty(250, "ml") == "250 ml"
    assert shopping.format_qty(2, "Stk") == "2 Stk"


def test_price_matching_and_estimate():
    prices = pricing.DEFAULT_PRICES
    assert pricing.match_price("Karotte", prices).item == "Karotten"
    assert pricing.match_price("Hähnchenbrust", prices).item == "Hähnchenbrustfilet"
    assert pricing.match_price("rote Linsen (getrocknet)", prices).item == "Rote Linsen"
    est = pricing.estimate([{"name": "Rote Linsen", "qty": 750, "unit": "g"}, {"name": "Einhornfleisch", "qty": 1, "unit": "Stk"}], prices)
    assert est.at_checkout == pytest.approx(2 * 1.49)  # zwei 500-g-Packungen
    assert est.proportional == pytest.approx(750 / 500 * 1.49, abs=0.01)
    assert est.unmatched == ["Einhornfleisch"]


def test_brief_contains_shift_budget_and_mealprep(user_id):
    start = date(2026, 9, 21)
    repo.update_profile(user_id, shift_pattern={"0": "nacht", "1": "frueh"}, dislikes="Pilze", diet_type="vegetarisch")
    repo.upsert_weight(user_id, start, 70)
    profile = repo.get_profile(user_id)
    req = planning.PlanRequest(start, 3, 2, 60.0, True, start, 3, "mittag", "viel Gemüse")
    brief, params = planning.build_brief(user_id, profile, req)
    assert "Nachtschicht" in brief and "Frühschicht" in brief
    assert "Pilze" in brief and "Vegetarisch" in brief
    assert "Budget-Modus" in brief and "Haferflocken" in brief
    assert "Meal-Prep" in brief and "3 Tage" in brief
    assert params["persons"] == 2 and params["prep_day"] == "2026-09-21"


def _sse(message_text: str) -> bytes:
    msg = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5", "content": [],
           "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 1}}
    events = [
        ("message_start", {"type": "message_start", "message": msg}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": message_text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 50}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events).encode()


@pytest.fixture
def fake_stream(monkeypatch):
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    state = {"requests": [], "reply": ""}

    def handler(request):
        state["requests"].append(json.loads(request.content))
        return httpx2.Response(200, content=_sse(state["reply"]), headers={"content-type": "text/event-stream"})

    client = anthropic.Anthropic(api_key="test-key", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)
    monkeypatch.setattr(ai, "_client", client)
    return state


def test_generate_plan_saves_and_builds_shopping(user_id, fake_stream):
    fake_stream["reply"] = json.dumps(PLAN).replace('"Unbekannt"', '"Trockenware"')
    repo.upsert_weight(user_id, date(2026, 9, 20), 70)
    profile = repo.get_profile(user_id)
    req = planning.PlanRequest(date(2026, 9, 21), 2, 1, None, False, None, 3, "mittag", "")
    plan_id = planning.generate(user_id, profile, req)
    body = fake_stream["requests"][0]
    assert body["stream"] is True and body["output_config"]["effort"] == "medium"
    assert repo.latest_plan(user_id)["id"] == plan_id
    names = {i["name"].lower() for i in repo.list_shopping(user_id)}
    assert {"rote linsen", "karotten", "gurke", "reis"} <= names


def test_invalid_answer_gives_friendly_error(user_id, fake_stream):
    fake_stream["reply"] = json.dumps(PLAN)  # enthält einen ungültigen Bereich
    with pytest.raises(ai.AIError, match="unerwartetes Format"):
        ai.generate_week_plan("egal")


def test_coach_stream_yields_text(fake_stream):
    fake_stream["reply"] = "Schön, dass du regelmäßig frühstückst!"
    out = "".join(ai.coach_stream([{"role": "user", "content": "Wie war meine Woche?"}], "Zusammenfassung", hide_numbers=True))
    assert "frühstückst" in out
    system = fake_stream["requests"][0]["system"]
    assert "KEINE Kalorien" in system and "<nutzerdaten>" in system and "0221 892031" in system


def test_meal_times_cover_all_shifts():
    for shift in schedule.SHIFTS:
        assert set(schedule.meal_times(shift)) == {"fruehstueck", "mittag", "abend", "snack"}
    assert schedule.shift_for_day(0, {"0": "nacht"}) == "nacht"
    assert schedule.shift_for_day(0, {"0": "nacht"}, {date(2026, 9, 21): "frei"}, date(2026, 9, 21)) == "frei"
    assert schedule.shift_for_day(3, None) == "frei"
