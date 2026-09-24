"""Tracking: Portionen, Muster, Open Food Facts (gemockt), Barcode, Claude-Anfragen (gemockt)."""

import json
from datetime import date, datetime, timedelta

import httpx2
import pytest

from core import basic_foods, meals, patterns, portions
from db import repo
from services import ai, barcode, openfoodfacts


# ---------------------------------------------------------------- Portionen & Grundnahrungsmittel
def test_nutrients_and_scaling():
    food = basic_foods.get("Banane").as_food()
    n = portions.nutrients_for(food, 120)
    assert n["kcal"] == pytest.approx(111.6)
    scaled = portions.scale_item({"name": "X", "grams": 100, "kcal": 200, "protein": 10, "carbs": 20, "fat": 5}, 150)
    assert scaled["kcal"] == 300 and scaled["fat"] == 7.5
    assert portions.grams_for_size(food, "gross") == 150
    assert portions.grams_for_size({"serving_g": 100}, "klein") == 65


def test_basic_food_search():
    names = [f.name for f in basic_foods.search("vollkorn")]
    assert "Vollkornbrot" in names
    assert basic_foods.search("") == []


def test_guess_meal():
    at = lambda h, m=0: datetime(2026, 9, 24, h, m)  # noqa: E731
    assert meals.guess_meal(at(7)) == "fruehstueck"
    assert meals.guess_meal(at(12, 30)) == "mittag"
    assert meals.guess_meal(at(19)) == "abend"
    assert meals.guess_meal(at(23)) == "snack"
    from core import schedule
    # Nachtschicht: um 1:40 Uhr ist der Nacht-Snack dran
    assert meals.guess_meal(at(1, 40), schedule.meal_times("nacht")) == "snack"


# ---------------------------------------------------------------- Muster
def test_pattern_suggests_last_weekday(user_id):
    today = date(2026, 9, 22)  # Dienstag
    last_tuesday = today - timedelta(days=7)
    repo.add_entries(user_id, last_tuesday, "fruehstueck", [{"name": "Haferflocken", "kcal": 220}, {"name": "Banane", "kcal": 110}], "freitext")
    repo.add_entries(user_id, today - timedelta(days=3), "fruehstueck", [{"name": "Brötchen", "kcal": 150}], "freitext")
    entries = repo.get_entries(user_id, today - timedelta(days=30), today)
    sugg = patterns.suggest(entries, today, "fruehstueck")
    assert sugg[0].reason == "Wie letzten Dienstag?"
    assert sugg[0].kcal == 330
    # Schon heute eingetragen → wird nicht erneut vorgeschlagen
    repo.add_entries(user_id, today, "fruehstueck", [{"name": "Haferflocken", "kcal": 220}, {"name": "Banane", "kcal": 110}], "favorit")
    entries = repo.get_entries(user_id, today - timedelta(days=30), today)
    assert all(s.kcal != 330 for s in patterns.suggest(entries, today, "fruehstueck"))


# ---------------------------------------------------------------- Barcode
def test_ean_checksum():
    assert barcode.valid_ean("4000417025005")
    assert not barcode.valid_ean("4000417025006")
    assert barcode.valid_ean("96385074")  # EAN-8
    assert not barcode.valid_ean("abc")


def test_barcode_decode_from_generated_image():
    zx = pytest.importorskip("zxingcpp")
    import io
    img = zx.create_barcode("4000417025005", zx.BarcodeFormat.EAN13).to_image(scale=4) if hasattr(zx, "create_barcode") else None
    if img is None:
        pytest.skip("zxing-cpp ohne Barcode-Erzeugung")
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).convert("RGB").save(buf, format="PNG") if not isinstance(img, Image.Image) else img.save(buf, format="PNG")
    assert barcode.decode(buf.getvalue()) == "4000417025005"


# ---------------------------------------------------------------- Open Food Facts (gemockt)
OFF_PRODUCT = {
    "status": 1,
    "product": {
        "code": "4000417025005",
        "product_name_de": "Zartbitter Schokolade",
        "brands": "Ritter Sport, Alfred Ritter",
        "serving_quantity": "25",
        "nutriments": {"energy-kcal_100g": 537, "proteins_100g": 6.8, "carbohydrates_100g": 43, "fat_100g": 36},
    },
}


class FakeResponse:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


def test_parse_product_kj_fallback():
    p = {"code": "1", "product_name": "Test", "nutriments": {"energy-kj_100g": 418.4}}
    assert openfoodfacts.parse_product(p)["kcal_100g"] == 100
    assert openfoodfacts.parse_product({"code": "1", "product_name": "Ohne Energie", "nutriments": {}}) is None


def test_lookup_barcode_caches(monkeypatch, user_id):
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(url)
        assert headers["User-Agent"].startswith("KANO/")
        return FakeResponse(OFF_PRODUCT)

    monkeypatch.setattr(openfoodfacts.requests, "get", fake_get)
    food = openfoodfacts.lookup_barcode("4000417025005", user_id)
    assert food["name"] == "Zartbitter Schokolade" and food["brand"] == "Ritter Sport"
    again = openfoodfacts.lookup_barcode("4000417025005", user_id)
    assert again["id"] == food["id"] and len(calls) == 1  # zweiter Aufruf aus dem Cache
    assert repo.search_foods_local("zartbitter", user_id)


def test_lookup_barcode_offline_raises(monkeypatch):
    def boom(*a, **k):
        raise openfoodfacts.requests.ConnectionError("offline")

    monkeypatch.setattr(openfoodfacts.requests, "get", boom)
    with pytest.raises(openfoodfacts.OFFError):
        openfoodfacts.lookup_barcode("4000417025012")


# ---------------------------------------------------------------- Claude (gemockt)
def _message(text: str) -> dict:
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


@pytest.fixture
def fake_claude(monkeypatch):
    """Ersetzt den HTTP-Transport des Anthropic-Clients und protokolliert Anfragen."""
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    state = {"requests": [], "reply": ""}

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        state["requests"].append({"body": body, "headers": dict(request.headers)})
        return httpx2.Response(200, json=_message(state["reply"]))

    client = anthropic.Anthropic(api_key="test-key", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)
    monkeypatch.setattr(ai, "_client", client)
    return state


def test_estimate_from_text_request_and_parse(fake_claude):
    fake_claude["reply"] = json.dumps({
        "items": [
            {"name": "Vollkornbrot", "grams": 100, "size_label": "mittel", "kcal": 216, "protein": 7.5, "carbs": 38, "fat": 1.5, "confidence": "hoch"},
            {"name": "Gouda", "grams": 30, "size_label": "mittel", "kcal": 107, "protein": 7.5, "carbs": 0, "fat": 8.4, "confidence": "mittel"},
        ],
        "meal_guess": "fruehstueck",
        "note": "",
    })
    est = ai.estimate_from_text("2 Scheiben Vollkornbrot mit Käse")
    assert [i.name for i in est.items] == ["Vollkornbrot", "Gouda"]
    req = fake_claude["requests"][0]
    body = req["body"]
    assert body["model"] == "claude-opus-5"
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["headers"]["anthropic-beta"]
    assert "Vollkornbrot" in body["messages"][0]["content"]


def test_photo_is_downscaled_jpeg(fake_claude):
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), (200, 120, 50)).save(buf, format="PNG")
    fake_claude["reply"] = json.dumps({"items": [], "meal_guess": "mittag", "note": ""})
    ai.estimate_from_photo(buf.getvalue())
    img_block = fake_claude["requests"][0]["body"]["messages"][0]["content"][0]
    assert img_block["type"] == "image" and img_block["source"]["media_type"] == "image/jpeg"
    import base64
    decoded = Image.open(io.BytesIO(base64.b64decode(img_block["source"]["data"])))
    assert max(decoded.size) <= 1568


def test_ai_errors_are_translated(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai, "_client", None)
    with pytest.raises(ai.AIError, match="nicht eingerichtet"):
        ai.estimate_from_text("Apfel")


def test_other_model_skips_fallbacks(fake_claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    fake_claude["reply"] = json.dumps({"items": [], "meal_guess": "snack", "note": ""})
    ai.estimate_from_text("Apfel")
    body = fake_claude["requests"][0]["body"]
    assert "fallbacks" not in body and "effort" not in body.get("output_config", {})
