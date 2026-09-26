"""Google-Gemini-Anbindung (kostenloses Kontingent möglich).

Wird von services/ai.py genutzt, wenn `GEMINI_API_KEY` gesetzt ist (und kein Claude-Schlüssel
bzw. `AI_PROVIDER = "gemini"`). Die Funktionen nehmen dieselben Bausteine entgegen wie die
Claude-Variante, damit die Seiten nichts vom Anbieter wissen müssen.

* Modell per `GEMINI_MODEL` änderbar, Standard `gemini-flash-latest` (Alias auf das aktuelle Flash-Modell).
* Strukturierte Antworten über `response_schema` + Pydantic.
"""

from __future__ import annotations

import base64
from typing import Iterator, TypeVar

from pydantic import BaseModel

DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT_MS = 120_000

T = TypeVar("T", bound=BaseModel)

_client = None
_client_key: str | None = None


def get_client(key: str):
    """Client erst bei Bedarf laden (spart Startzeit)."""
    global _client, _client_key
    if _client is None or _client_key != key:
        from google import genai
        from google.genai import types

        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        _client_key = key
    return _client


def _parts(content: list | str) -> list:
    """Claude-förmige Inhalte (Text bzw. Bild-/Textblöcke) in Gemini-Parts umwandeln."""
    from google.genai import types

    if isinstance(content, str):
        return [types.Part.from_text(text=content)]
    parts = []
    for block in content:
        if block.get("type") == "image":
            src = block["source"]
            parts.append(types.Part.from_bytes(data=base64.b64decode(src["data"]), mime_type=src["media_type"]))
        elif block.get("type") == "text":
            parts.append(types.Part.from_text(text=block["text"]))
    return parts


def _blocked(resp) -> bool:
    """Antwort wurde von Googles Sicherheitsfiltern blockiert oder ist leer."""
    try:
        if resp.prompt_feedback and resp.prompt_feedback.block_reason:
            return True
        cand = resp.candidates[0] if resp.candidates else None
        reason = str(getattr(cand, "finish_reason", "") or "")
        return cand is None or any(r in reason for r in ("SAFETY", "PROHIBITED", "BLOCKLIST", "RECITATION"))
    except (AttributeError, IndexError):
        return False


class Blocked(Exception):
    pass


class Truncated(Exception):
    pass


def parse(client, model: str, system: str, content: list | str, schema: type[T], max_tokens: int) -> T:
    from google.genai import types

    resp = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=_parts(content))],
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=max_tokens,
        ),
    )
    if _blocked(resp):
        raise Blocked()
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    reason = str(getattr(resp.candidates[0], "finish_reason", "") if resp.candidates else "")
    if "MAX_TOKENS" in reason:
        raise Truncated()
    return schema.model_validate_json(resp.text or "")


def _history(history: list[dict]) -> list:
    from google.genai import types

    return [
        types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part.from_text(text=m["content"])])
        for m in history
    ]


def stream_text(client, model: str, system: str, history: list[dict], max_tokens: int) -> Iterator[str]:
    from google.genai import types

    got_text = False
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=_history(history),
        config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
    ):
        text = getattr(chunk, "text", None)
        if text:
            got_text = True
            yield text
    if not got_text:
        yield "Dazu kann ich leider nichts sagen – magst du es anders formulieren?"


def text(client, model: str, system: str, prompt: str, max_tokens: int) -> str:
    from google.genai import types

    resp = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
    )
    if _blocked(resp) or not resp.text:
        raise Blocked()
    return resp.text.strip()


def translate(exc: Exception, model: str) -> str | None:
    """Gemini-Fehler → deutsche Meldung (None, wenn es kein Gemini-Fehler ist)."""
    try:
        from google.genai import errors
    except ImportError:  # pragma: no cover
        return None
    if isinstance(exc, errors.ClientError):
        code = getattr(exc, "code", None)
        msg = str(exc).lower()
        if code == 429:
            return ("Das kostenlose Gemini-Kontingent ist gerade ausgeschöpft. "
                    "Bitte in ein paar Minuten (oder morgen) nochmal versuchen.")
        if code in (401, 403) or "api key" in msg or "api_key" in msg:
            return "Der Gemini-API-Schlüssel ist ungültig. Bitte GEMINI_API_KEY in den Secrets prüfen."
        if code == 404:
            return f"Das Gemini-Modell „{model}“ ist nicht verfügbar. Bitte GEMINI_MODEL prüfen."
        return "Die Anfrage konnte nicht verarbeitet werden. Versuch es mit etwas anderen Angaben."
    if isinstance(exc, errors.ServerError):
        return "Gemini ist vorübergehend nicht erreichbar. Bitte später erneut versuchen."
    if isinstance(exc, errors.APIError):
        return "Bei der Gemini-Anfrage ist etwas schiefgelaufen."
    return None
