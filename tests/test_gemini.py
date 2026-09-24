"""Google-Gemini-Anbindung: Anbieterwahl, Anfrageform und Fehlerübersetzung (Client simuliert)."""

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from services import ai, ai_gemini
from services.ai_schemas import FoodEstimate, MealEstimate


@pytest.fixture
def gemini(monkeypatch):
    """Gemini als einzigen Anbieter einrichten und den Google-Client durch eine Attrappe ersetzen."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    calls = {"generate": [], "stream": []}
    state = {"parsed": None, "text": "", "chunks": [], "raise": None}

    def generate_content(model, contents, config):
        calls["generate"].append({"model": model, "contents": contents, "config": config})
        if state["raise"]:
            raise state["raise"]
        return SimpleNamespace(parsed=state["parsed"], text=state["text"], prompt_feedback=None,
                               candidates=[SimpleNamespace(finish_reason="FinishReason.STOP")])

    def generate_content_stream(model, contents, config):
        calls["stream"].append({"model": model, "contents": contents, "config": config})
        return iter(SimpleNamespace(text=t) for t in state["chunks"])

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content, generate_content_stream=generate_content_stream))
    monkeypatch.setattr(ai_gemini, "get_client", lambda key: fake)
    return calls, state


def test_provider_selection(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AI_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert ai.provider() is None and not ai.is_configured()
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert ai.provider() == "gemini" and ai.model() == "gemini-flash-latest"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert ai.provider() == "anthropic"  # Claude hat Vorrang …
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert ai.provider() == "gemini"  # … außer es wird ausdrücklich Gemini gewählt
    assert "Google" in ai.privacy_note()


def test_text_estimate_uses_schema(gemini):
    calls, state = gemini
    state["parsed"] = MealEstimate(items=[FoodEstimate(name="Vollkornbrot", grams=100, size_label="mittel", kcal=216,
                                                        protein=7.5, carbs=38, fat=1.5, confidence="hoch")],
                                   meal_guess="fruehstueck", note="")
    est = ai.estimate_from_text("2 Scheiben Vollkornbrot")
    assert est.items[0].name == "Vollkornbrot"
    call = calls["generate"][0]
    assert call["model"] == "gemini-flash-latest"
    assert call["config"].response_schema is MealEstimate
    assert call["config"].response_mime_type == "application/json"
    assert "Ernährungsfachkraft" in call["config"].system_instruction
    assert "Vollkornbrot" in call["contents"][0].parts[0].text


def test_text_estimate_falls_back_to_json_text(gemini):
    _, state = gemini
    state["text"] = '{"items": [], "meal_guess": "snack", "note": ""}'
    assert ai.estimate_from_text("Apfel").meal_guess == "snack"


def test_photo_is_sent_as_jpeg_part(gemini):
    calls, state = gemini
    state["text"] = '{"items": [], "meal_guess": "mittag", "note": ""}'
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), (10, 200, 30)).save(buf, format="PNG")
    ai.estimate_from_photo(buf.getvalue(), "mit Soße")
    parts = calls["generate"][0]["contents"][0].parts
    assert parts[0].inline_data.mime_type == "image/jpeg"
    assert "mit Soße" in parts[1].text


def test_coach_stream_maps_roles(gemini):
    calls, state = gemini
    state["chunks"] = ["Schön, ", "dass du fragst!"]
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hallo!"}, {"role": "user", "content": "Tipp?"}]
    out = "".join(ai.coach_stream(history, "Zusammenfassung", hide_numbers=True))
    assert out == "Schön, dass du fragst!"
    call = calls["stream"][0]
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]
    assert "KEINE Kalorien" in call["config"].system_instruction


def test_quota_error_is_translated(gemini):
    from google.genai import errors

    _, state = gemini
    state["raise"] = errors.ClientError(429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    with pytest.raises(ai.AIError, match="kostenlose Gemini-Kontingent"):
        ai.estimate_from_text("Apfel")


def test_invalid_key_is_translated(gemini):
    from google.genai import errors

    _, state = gemini
    state["raise"] = errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}})
    with pytest.raises(ai.AIError, match="Gemini-API-Schlüssel ist ungültig"):
        ai.weekly_review("x", False, __import__("datetime").date(2026, 9, 21))
