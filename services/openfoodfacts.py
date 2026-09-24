"""Open Food Facts: Barcode-Abfrage und Produktsuche.

* Jedes gefundene Produkt wird in der Tabelle `foods` gecacht (30 Tage gültig) – spätere
  Suchen finden es lokal, auch wenn OFF nicht erreichbar ist.
* Suchergebnisse werden zusätzlich 24 h im Speicher gehalten, um OFF-Limits
  (≈ 10 Suchanfragen/Minute) einzuhalten.
* OFF erbittet einen aussagekräftigen User-Agent.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import requests

from db import repo

BASE = "https://world.openfoodfacts.org"
FIELDS = "code,product_name,product_name_de,generic_name_de,brands,nutriments,serving_quantity"
TIMEOUT = 8
CACHE_DAYS = 30
SEARCH_TTL = 24 * 3600

_search_cache: dict[str, tuple[float, list[dict]]] = {}


class OFFError(Exception):
    """Open Food Facts nicht erreichbar oder fehlerhafte Antwort."""


def _user_agent() -> str:
    contact = os.environ.get("OFF_CONTACT")
    if not contact:
        try:
            import streamlit as st

            contact = st.secrets.get("OFF_CONTACT")
        except Exception:
            contact = None
    return f"KANO/1.0 ({contact or 'ernaehrungs-app'})"


def _get(url: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": _user_agent()})
    except requests.RequestException as exc:
        raise OFFError("Open Food Facts ist gerade nicht erreichbar.") from exc
    if resp.status_code == 404:
        return {}
    if resp.status_code == 429:
        raise OFFError("Open Food Facts bremst gerade Anfragen – bitte gleich nochmal versuchen.")
    if resp.status_code >= 400:
        raise OFFError(f"Open Food Facts antwortet mit Fehler {resp.status_code}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise OFFError("Unerwartete Antwort von Open Food Facts.") from exc


def _num(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_product(p: dict) -> dict | None:
    """OFF-Produkt → einheitliches Lebensmittel-Dict (None, wenn Energie fehlt)."""
    n = p.get("nutriments") or {}
    kcal = _num(n.get("energy-kcal_100g"))
    if kcal is None:
        kj = _num(n.get("energy-kj_100g")) or _num(n.get("energy_100g"))
        kcal = kj / 4.184 if kj is not None else None
    name = (p.get("product_name_de") or p.get("product_name") or p.get("generic_name_de") or "").strip()
    if kcal is None or not name or not p.get("code"):
        return None
    brand = (p.get("brands") or "").split(",")[0].strip() or None
    return {
        "barcode": str(p["code"]),
        "name": name[:250],
        "brand": brand,
        "kcal_100g": round(kcal, 1),
        "protein_100g": _num(n.get("proteins_100g")),
        "carbs_100g": _num(n.get("carbohydrates_100g")),
        "fat_100g": _num(n.get("fat_100g")),
        "fiber_100g": _num(n.get("fiber_100g")),
        "serving_g": _num(p.get("serving_quantity")),
    }


def _fresh(food: dict) -> bool:
    fetched = food.get("fetched_at")
    if not fetched:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched < timedelta(days=CACHE_DAYS)


def lookup_barcode(code: str, user_id: int | None = None) -> dict | None:
    """Produkt zum Barcode – erst eigener Bestand/Cache, dann OFF. None = unbekannt."""
    code = "".join(ch for ch in code if ch.isdigit())
    if not code:
        return None
    cached = repo.get_food_by_barcode(code, user_id)
    if cached and (cached["source"] == "custom" or _fresh(cached)):
        return cached
    try:
        data = _get(f"{BASE}/api/v2/product/{code}.json", {"fields": FIELDS})
    except OFFError:
        if cached:  # veralteter Cache ist besser als nichts
            return cached
        raise
    if data.get("status") != 1 or not data.get("product"):
        return cached
    food = parse_product({**data["product"], "code": data["product"].get("code") or code})
    if not food:
        return cached
    food_id = repo.upsert_off_food(food)
    return repo.get_food(food_id)


def search(query: str, page_size: int = 20) -> list[dict]:
    """Produktsuche bei OFF (bevorzugt in Deutschland verkaufte Produkte)."""
    key = query.strip().lower()
    if len(key) < 2:
        return []
    hit = _search_cache.get(key)
    if hit and time.time() - hit[0] < SEARCH_TTL:
        return hit[1]
    data = _get(
        f"{BASE}/cgi/search.pl",
        {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": page_size,
            "fields": FIELDS,
            "sort_by": "unique_scans_n",
            "countries_tags_en": "germany",
            "lc": "de",
        },
    )
    results = []
    for p in data.get("products") or []:
        food = parse_product(p)
        if food:
            food_id = repo.upsert_off_food(food)
            results.append({**food, "id": food_id, "source": "off"})
    _search_cache[key] = (time.time(), results)
    return results
