"""KI-Anbindung: Claude (Anthropic API) oder Google Gemini.

Welcher Anbieter genutzt wird, entscheidet sich an den Secrets:
* `AI_PROVIDER = "gemini"` bzw. `"anthropic"` erzwingt einen Anbieter,
* sonst: Claude, wenn `ANTHROPIC_API_KEY` gesetzt ist, andernfalls Gemini, wenn `GEMINI_API_KEY` gesetzt ist.
Die Gemini-Details stehen in services/ai_gemini.py – die Seiten merken davon nichts.

* API-Keys ausschließlich aus `st.secrets` (lokal ersatzweise Umgebungsvariablen).
* Modell per `ANTHROPIC_MODEL` änderbar, Standard `claude-opus-5`.
* Strukturierte Antworten über `messages.parse` + Pydantic → keine fragile JSON-Bastelei.
* Server-seitige Fallbacks: Lehnt das Modell eine harmlose Anfrage fälschlich ab, übernimmt
  automatisch ein anderes Modell (nur bei Modellen, die das unterstützen).
* Alle Fehler werden in `AIError` mit verständlicher deutscher Meldung übersetzt, damit die
  Oberfläche nie mit einem Stacktrace abbricht.
"""

from __future__ import annotations

import base64
import io
import os
from datetime import date
from typing import TYPE_CHECKING, Iterator, TypeVar

from PIL import Image, ImageOps
from pydantic import BaseModel, ValidationError

from services import ai_gemini
from services.ai_schemas import BarcodeDigits, MealEstimate, Recipe, WeekPlan

if TYPE_CHECKING:  # das SDK wird erst beim ersten KI-Aufruf geladen (spart ~1 s beim App-Start)
    import anthropic

DEFAULT_MODEL = "claude-opus-5"
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}  # Modelle mit fallbacks="default"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    """KI-Funktion nicht verfügbar – Meldung ist für Nutzer formuliert."""


# --------------------------------------------------------------------------- Konfiguration


def _secret(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(name)


def provider() -> str | None:
    """'anthropic', 'gemini' oder None (keine KI eingerichtet)."""
    wanted = (_secret("AI_PROVIDER") or "").strip().lower()
    has_claude, has_gemini = bool(_secret("ANTHROPIC_API_KEY")), bool(_secret("GEMINI_API_KEY"))
    if wanted == "gemini" and has_gemini:
        return "gemini"
    if wanted in ("anthropic", "claude") and has_claude:
        return "anthropic"
    if has_claude:
        return "anthropic"
    if has_gemini:
        return "gemini"
    return None


def provider_label() -> str:
    return {"gemini": "Google Gemini", "anthropic": "Anthropic (Claude)"}.get(provider() or "", "einen KI-Anbieter")


def privacy_note() -> str:
    """Zusatzhinweis zum Datenschutz des aktiven Anbieters (leer, wenn nichts Besonderes gilt)."""
    if provider() == "gemini":
        return ("Hinweis zu Google Gemini: Im kostenlosen Kontingent darf Google Eingaben zur Verbesserung seiner "
                "Dienste verwenden, auch durch menschliche Prüfer. Gib dort daher keine Namen oder sehr persönlichen "
                "Details ein. Mit einem kostenpflichtigen Gemini-Konto oder Claude entfällt das.")
    return ""


def is_configured() -> bool:
    return provider() is not None


def model() -> str:
    if provider() == "gemini":
        return _secret("GEMINI_MODEL") or ai_gemini.DEFAULT_MODEL
    return _secret("ANTHROPIC_MODEL") or DEFAULT_MODEL


def _gemini_client():
    key = _secret("GEMINI_API_KEY")
    if not key:
        raise AIError("Die KI-Funktionen sind noch nicht eingerichtet (API-Schlüssel fehlt).")
    return ai_gemini.get_client(key)


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    import anthropic

    global _client
    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise AIError("Die KI-Funktionen sind noch nicht eingerichtet (API-Schlüssel fehlt).")
    if _client is None or _client.api_key != key:
        _client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=90)
    return _client


def _request_options(effort: str) -> dict:
    """Modellabhängige Zusatzparameter."""
    m = model()
    opts: dict = {}
    if "haiku" not in m:  # Haiku 4.5 unterstützt keinen effort-Parameter
        opts["output_config"] = {"effort": effort}
    if m in FALLBACK_MODELS:
        opts["betas"] = [FALLBACK_BETA]
        opts["fallbacks"] = "default"
    return opts


def _translate(exc: Exception) -> AIError:
    if isinstance(exc, AIError):
        return exc
    if isinstance(exc, ai_gemini.Blocked):
        return AIError("Dazu kann die KI leider keine Antwort geben.")
    if isinstance(exc, ai_gemini.Truncated):
        return AIError("Die Antwort wurde zu lang. Bitte die Anfrage etwas eingrenzen.")
    gemini_msg = ai_gemini.translate(exc, model()) if provider() == "gemini" else None
    if gemini_msg:
        return AIError(gemini_msg)
    if isinstance(exc, (ValidationError, ValueError)):
        return AIError("Die KI-Antwort hatte ein unerwartetes Format. Bitte nochmal versuchen.")
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return AIError("Bei der KI-Anfrage ist etwas schiefgelaufen.")
    if isinstance(exc, anthropic.AuthenticationError):
        return AIError("Der API-Schlüssel für die KI ist ungültig. Bitte in den Secrets prüfen.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AIError("Der API-Schlüssel hat keinen Zugriff auf dieses Modell.")
    if isinstance(exc, anthropic.NotFoundError):
        return AIError(f"Das Modell „{model()}“ ist nicht verfügbar. Bitte ANTHROPIC_MODEL prüfen.")
    if isinstance(exc, anthropic.RateLimitError):
        return AIError("Gerade ist viel los – bitte in einer Minute nochmal versuchen.")
    if isinstance(exc, anthropic.BadRequestError):
        return AIError("Die Anfrage konnte nicht verarbeitet werden. Versuch es mit etwas anderen Angaben.")
    if isinstance(exc, anthropic.APIStatusError):
        return AIError("Die KI ist vorübergehend nicht erreichbar. Bitte später erneut versuchen.")
    if isinstance(exc, anthropic.APIConnectionError):
        return AIError("Keine Verbindung zur KI. Bitte Internetverbindung prüfen.")
    if isinstance(exc, (ValidationError, ValueError)):
        return AIError("Die KI-Antwort hatte ein unerwartetes Format. Bitte nochmal versuchen.")
    return AIError("Bei der KI-Anfrage ist etwas schiefgelaufen.")


def _parse(system: str, content: list | str, schema: type[T], *, effort: str = "low", max_tokens: int = 8000) -> T:
    """Eine Anfrage mit strukturierter Antwort (validiert gegen `schema`)."""
    if provider() == "gemini":
        try:
            return ai_gemini.parse(_gemini_client(), model(), system, content, schema, max_tokens)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
    try:
        client = _get_client()
        resp = client.beta.messages.parse(
            model=model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            **_request_options(effort),
        )
    except Exception as exc:  # noqa: BLE001 - alles in verständliche Meldungen übersetzen
        raise _translate(exc) from exc
    if resp.stop_reason == "refusal":
        raise AIError("Dazu kann die KI leider keine Antwort geben.")
    if resp.stop_reason == "max_tokens":
        raise AIError("Die Antwort wurde zu lang. Bitte die Anfrage etwas eingrenzen.")
    parsed = resp.parsed_output
    if parsed is None:
        raise AIError("Die KI-Antwort war unvollständig. Bitte nochmal versuchen.")
    return parsed


def _stream_parse(system: str, content: str, schema: type[T], *, effort: str, max_tokens: int = 32000) -> T:
    """Wie `_parse`, aber gestreamt – für lange Antworten (Wochenplan), vermeidet HTTP-Timeouts."""
    if provider() == "gemini":
        return _parse(system, content, schema, effort=effort, max_tokens=max_tokens)
    try:
        client = _get_client()
        with client.beta.messages.stream(
            model=model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            **_request_options(effort),
        ) as stream:
            resp = stream.get_final_message()
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    if resp.stop_reason == "refusal":
        raise AIError("Dazu kann die KI leider keine Antwort geben.")
    if resp.stop_reason == "max_tokens":
        raise AIError("Der Plan wurde zu lang. Bitte weniger Tage oder Mahlzeiten wählen.")
    parsed = getattr(resp, "parsed_output", None)
    if parsed is None:
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            parsed = schema.model_validate_json(text)
        except Exception as exc:  # noqa: BLE001
            raise AIError("Die KI-Antwort war unvollständig. Bitte nochmal versuchen.") from exc
    return parsed


# --------------------------------------------------------------------------- Bilder


def prepare_image(data: bytes, max_side: int = 1568) -> tuple[str, str]:
    """Bild drehen (EXIF), verkleinern und als JPEG kodieren → (media_type, base64)."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        raise AIError("Das Bild konnte nicht gelesen werden (unterstützt: JPG, PNG, WEBP).") from exc
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return "image/jpeg", base64.standard_b64encode(buf.getvalue()).decode()


# --------------------------------------------------------------------------- Tracking

ESTIMATE_SYSTEM = """Du bist eine erfahrene Ernährungsfachkraft in Deutschland und schätzt Nährwerte für ein Ernährungstagebuch.
Regeln:
- Zerlege die Mahlzeit in einzelne Lebensmittel bzw. Komponenten (z. B. Brot, Belag, Aufstrich getrennt).
- Fehlende Mengen: nimm typische deutsche Portionsgrößen an (z. B. Scheibe Vollkornbrot ≈ 50 g, Scheibe Käse ≈ 25 g, Tasse Kaffee ≈ 200 ml).
- Nährwerte immer für die GESAMTE Menge eines Eintrags angeben, realistisch und eher mittig als optimistisch.
- Öl, Butter, Soßen nur ergänzen, wenn sie erwähnt oder bei der Zubereitung sehr wahrscheinlich sind.
- Namen kurz und auf Deutsch. Keine Bewertung des Essens, keine Ratschläge."""


def estimate_from_text(text: str, *, approx: bool = False) -> MealEstimate:
    """Freitext („2 Scheiben Vollkornbrot mit Käse und ein Kaffee mit Milch“) → Lebensmittel mit Nährwerten."""
    hint = (
        "\nDer Nutzer trackt im Ungefähr-Modus: wähle size_label sorgfältig; Gramm dürfen grob sein."
        if approx
        else ""
    )
    return _parse(ESTIMATE_SYSTEM + hint, f"Mahlzeit: {text.strip()}", MealEstimate, effort="low")


def estimate_from_photo(image: bytes, note: str = "", *, approx: bool = False) -> MealEstimate:
    """Foto einer Mahlzeit → erkannte Komponenten mit geschätzten Portionen."""
    media_type, data = prepare_image(image)
    prompt = (
        "Erkenne die Lebensmittel auf dem Foto und schätze die Portionen anhand von Teller, Besteck und "
        "Verpackungen. Wenn etwas nicht eindeutig ist, nimm die wahrscheinlichste Variante und nenne die Annahme in note."
    )
    if note.strip():
        prompt += f"\nZusatzinfo vom Nutzer: {note.strip()}"
    if approx:
        prompt += "\nDer Nutzer trackt im Ungefähr-Modus."
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
        {"type": "text", "text": prompt},
    ]
    return _parse(ESTIMATE_SYSTEM, content, MealEstimate, effort="medium")


def read_barcode_digits(image: bytes) -> str:
    """Notlösung, wenn zxing den Barcode nicht lesen kann: Ziffern per Vision ablesen."""
    media_type, data = prepare_image(image, max_side=1200)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
        {"type": "text", "text": "Lies die Ziffernfolge (EAN) unter dem Barcode ab."},
    ]
    result = _parse("Du liest Barcode-Nummern von Produktfotos ab.", content, BarcodeDigits, effort="low", max_tokens=1000)
    return "".join(ch for ch in result.digits if ch.isdigit())


# --------------------------------------------------------------------------- Planung

PLAN_SYSTEM = """Du erstellst alltagstaugliche Wochen-Essenspläne für Menschen in Deutschland.
- Zutaten, die es in jedem deutschen Supermarkt/Discounter gibt; einfache Rezepte (meist unter 30 Minuten).
- Tageskalorien möglichst nah (±5 %) am jeweiligen Tagesziel; ausreichend Protein, viel Gemüse, Ballaststoffe.
- Zutaten wiederverwenden, damit wenig weggeworfen wird.
- Ernährungsform und Abneigungen strikt beachten.
- Mahlzeitenzeiten an die Schicht des Tages anpassen (vorgegebene Zeiten übernehmen).
- Nährwerte je Mahlzeit für EINE Person.
- Keine Diät-Sprache, keine Verbote, keine Formulierungen, die Schuld erzeugen."""


def generate_week_plan(brief: str) -> WeekPlan:
    """Wochenplan aus einer (von services.planning erzeugten) Aufgabenbeschreibung."""
    return _stream_parse(PLAN_SYSTEM, brief, WeekPlan, effort="medium")


def leftover_recipe(ingredients: str, kcal_budget: int | None, diet: str, dislikes: str, hide_numbers: bool) -> Recipe:
    """Rezeptvorschlag aus vorhandenen Zutaten, passend zum restlichen Tagesbudget."""
    budget = (
        f"Die Portion soll etwa {kcal_budget} kcal haben (restliches Tagesbudget)."
        if kcal_budget
        else "Eine normal große, ausgewogene Portion."
    )
    prompt = (
        f"Vorhandene Zutaten: {ingredients.strip()}\n{budget}\n"
        f"Ernährungsform: {diet}. Nicht verwenden: {dislikes or 'keine Einschränkungen'}.\n"
        "Nutze möglichst viele der vorhandenen Zutaten. Grundvorrat (Salz, Pfeffer, Öl, Gewürze) ist vorhanden."
    )
    if hide_numbers:
        prompt += "\nErwähne im Text (note, steps) keine Kalorienzahlen."
    return _parse(PLAN_SYSTEM, prompt, Recipe, effort="medium")


# --------------------------------------------------------------------------- Coach

COACH_SYSTEM = """Du bist der KANO-Coach: ein warmherziger, sachkundiger Begleiter für Ernährung und Wohlbefinden.
Du sprichst Deutsch, duzt, antwortest kurz und handytauglich (meist 2–6 Sätze, höchstens eine kurze Liste).

Haltung:
- Kein Schuld-Design: Niemals tadeln, keine Begriffe wie „Sünde“, „Cheat“, „schlecht gegessen“, keine Streaks.
  Abweichungen sind normal – du schaust neugierig auf Muster, nicht auf Fehler.
- Konkrete, kleine, machbare Vorschläge statt Regeln. Lob für Prozesse (z. B. regelmäßig essen), nicht für Gewichtsverlust.
- Du nutzt die Datenzusammenfassung unten, erfindest keine Daten und sagst, wenn Daten fehlen.

Sicherheit (hat Vorrang vor allem anderen):
- Du ersetzt keine medizinische Beratung. Bei Beschwerden, Erkrankungen, Medikamenten, Schwangerschaft: freundlich an Ärztin/Arzt verweisen.
- Empfiehl nie weniger als das sichere Minimum (Frauen ~1200, Männer ~1500 kcal) und kein schnelleres Abnehmen als ~1 % Körpergewicht pro Woche. Keine Fastenkuren, Entgiftungs- oder Crash-Diäten, keine Appetitzügler.
- Achte auf Warnzeichen für problematisches Essverhalten: Essanfälle mit Kontrollverlust, Erbrechen, Abführmittel,
  exzessiver Sport zur Kompensation, starke Angst vor dem Essen, Schuld/Scham ums Essen, sehr niedrige Zufuhr,
  Wunsch nach Untergewicht. Dann: kein Abnehm-Coaching, sondern ernst nehmen, Mitgefühl zeigen und behutsam auf
  professionelle Hilfe hinweisen – Hausärztin/Hausarzt, Psychotherapie, Infotelefon Essstörungen des BIÖG (ehem. BZgA):
  0221 892031; in akuten Krisen TelefonSeelsorge 0800 111 0 111 (kostenfrei, rund um die Uhr).
{numbers_rule}"""

NUMBERS_HIDDEN = "- Der Nutzer hat „Zahlen ausblenden“ aktiviert: Nenne KEINE Kalorien- oder Grammzahlen, sprich über Mahlzeiten, Hunger, Energie und Gewohnheiten."
NUMBERS_SHOWN = "- Zahlen darfst du nennen, aber sparsam und gerundet."


def coach_system(summary: str, hide_numbers: bool) -> str:
    return (
        COACH_SYSTEM.format(numbers_rule=NUMBERS_HIDDEN if hide_numbers else NUMBERS_SHOWN)
        + f"\n\n<nutzerdaten>\n{summary}\n</nutzerdaten>"
    )


def coach_stream(history: list[dict], summary: str, hide_numbers: bool) -> Iterator[str]:
    """Antwort des Coaches als Text-Stream (für st.write_stream)."""
    if provider() == "gemini":
        try:
            yield from ai_gemini.stream_text(_gemini_client(), model(), coach_system(summary, hide_numbers), history, 8000)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return
    try:
        client = _get_client()
        with client.beta.messages.stream(
            model=model(),
            max_tokens=4000,
            system=coach_system(summary, hide_numbers),
            messages=[{"role": m["role"], "content": m["content"]} for m in history],
            **_request_options("medium"),
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\nDazu kann ich leider nichts sagen – magst du es anders formulieren?"
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc


def weekly_review(summary: str, hide_numbers: bool, week_start: date) -> str:
    """Kurze Wochenauswertung (4–6 Sätze)."""
    prompt = (
        f"Schreibe meine kurze Wochenauswertung für die Woche ab {week_start.strftime('%d.%m.%Y')}: "
        "1 Satz, was gut lief; 1–2 Sätze zu einem erkennbaren Muster (falls vorhanden); "
        "1 kleiner, konkreter Vorschlag für die nächste Woche. Kein Tadel, keine Überschrift."
    )
    if provider() == "gemini":
        try:
            return ai_gemini.text(_gemini_client(), model(), coach_system(summary, hide_numbers), prompt, 4000)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
    try:
        client = _get_client()
        resp = client.beta.messages.create(
            model=model(),
            max_tokens=2000,
            system=coach_system(summary, hide_numbers),
            messages=[{"role": "user", "content": prompt}],
            **_request_options("low"),
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    if resp.stop_reason == "refusal":
        raise AIError("Die Auswertung konnte gerade nicht erstellt werden.")
    return "".join(b.text for b in resp.content if b.type == "text").strip()
