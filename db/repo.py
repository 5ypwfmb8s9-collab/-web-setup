"""Datenzugriffsschicht.

Alle Seiten und Services lesen und schreiben ausschließlich über diese Funktionen.
Upserts sind bewusst als „erst lesen, dann einfügen/ändern“ implementiert, damit der Code
ohne dialektspezifisches SQL auf SQLite *und* PostgreSQL läuft.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterable, Iterator

from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.engine import Connection

from db import schema as s
from db.engine import get_engine

Row = dict[str, Any]


@contextmanager
def _tx() -> Iterator[Connection]:
    with get_engine().begin() as conn:
        yield conn


def _rows(result) -> list[Row]:
    return [dict(r._mapping) for r in result]


def _one(result) -> Row | None:
    r = result.first()
    return dict(r._mapping) if r else None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- Nutzer


def create_user(email: str, password_hash: str) -> int:
    with _tx() as c:
        res = c.execute(insert(s.users).values(email=email, password_hash=password_hash))
        user_id = res.inserted_primary_key[0]
        c.execute(insert(s.profiles).values(user_id=user_id))
        return user_id


def get_user(user_id: int) -> Row | None:
    with _tx() as c:
        return _one(c.execute(select(s.users).where(s.users.c.id == user_id)))


def get_user_by_email(email: str) -> Row | None:
    with _tx() as c:
        return _one(c.execute(select(s.users).where(func.lower(s.users.c.email) == email.lower())))


def set_login_state(user_id: int, failed_logins: int, locked_until: datetime | None) -> None:
    with _tx() as c:
        c.execute(
            update(s.users)
            .where(s.users.c.id == user_id)
            .values(failed_logins=failed_logins, locked_until=locked_until)
        )


def update_password(user_id: int, password_hash: str) -> None:
    with _tx() as c:
        c.execute(update(s.users).where(s.users.c.id == user_id).values(password_hash=password_hash))


def set_tier(user_id: int, tier: str) -> None:
    with _tx() as c:
        c.execute(update(s.users).where(s.users.c.id == user_id).values(tier=tier))


def delete_user(user_id: int) -> None:
    """Löscht das Konto samt aller Daten (explizit – unabhängig davon, ob die DB CASCADE erzwingt)."""
    with _tx() as c:
        for table in s.USER_TABLES:
            c.execute(delete(table).where(table.c.user_id == user_id))
        c.execute(delete(s.foods).where(s.foods.c.owner_id == user_id))
        c.execute(delete(s.profiles).where(s.profiles.c.user_id == user_id))
        c.execute(delete(s.users).where(s.users.c.id == user_id))


# --------------------------------------------------------------------------- Login-Token


def add_token(user_id: int, token_hash: str, expires_at: datetime) -> None:
    with _tx() as c:
        c.execute(insert(s.auth_tokens).values(user_id=user_id, token_hash=token_hash, expires_at=expires_at))


def user_id_for_token(token_hash: str) -> int | None:
    with _tx() as c:
        row = _one(c.execute(select(s.auth_tokens).where(s.auth_tokens.c.token_hash == token_hash)))
    if not row:
        return None
    expires = row["expires_at"]
    if expires.tzinfo is None:  # SQLite speichert ohne Zeitzone
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _utcnow():
        delete_token(token_hash)
        return None
    return row["user_id"]


def delete_token(token_hash: str) -> None:
    with _tx() as c:
        c.execute(delete(s.auth_tokens).where(s.auth_tokens.c.token_hash == token_hash))


# --------------------------------------------------------------------------- Profil


def get_profile(user_id: int) -> Row | None:
    with _tx() as c:
        return _one(c.execute(select(s.profiles).where(s.profiles.c.user_id == user_id)))


def update_profile(user_id: int, **fields: Any) -> None:
    allowed = {c.name for c in s.profiles.columns} - {"user_id"}
    values = {k: v for k, v in fields.items() if k in allowed}
    if not values:
        return
    with _tx() as c:
        exists = c.execute(select(s.profiles.c.user_id).where(s.profiles.c.user_id == user_id)).first()
        if exists:
            c.execute(update(s.profiles).where(s.profiles.c.user_id == user_id).values(**values))
        else:
            c.execute(insert(s.profiles).values(user_id=user_id, **values))


# --------------------------------------------------------------------------- Lebensmittel


FOOD_FIELDS = ("name", "brand", "kcal_100g", "protein_100g", "carbs_100g", "fat_100g", "fiber_100g", "serving_g")


def upsert_off_food(food: Row) -> int:
    """Speichert ein Open-Food-Facts-Produkt im Cache (oder aktualisiert es)."""
    values = {k: food.get(k) for k in FOOD_FIELDS}
    values["fetched_at"] = _utcnow()
    with _tx() as c:
        existing = _one(
            c.execute(
                select(s.foods.c.id).where(
                    and_(s.foods.c.source == "off", s.foods.c.barcode == food["barcode"], s.foods.c.owner_id.is_(None))
                )
            )
        )
        if existing:
            c.execute(update(s.foods).where(s.foods.c.id == existing["id"]).values(**values))
            return existing["id"]
        res = c.execute(insert(s.foods).values(source="off", barcode=food["barcode"], **values))
        return res.inserted_primary_key[0]


def add_custom_food(user_id: int, food: Row) -> int:
    values = {k: food.get(k) for k in FOOD_FIELDS}
    with _tx() as c:
        res = c.execute(
            insert(s.foods).values(source="custom", barcode=food.get("barcode"), owner_id=user_id, **values)
        )
        return res.inserted_primary_key[0]


def get_food(food_id: int) -> Row | None:
    with _tx() as c:
        return _one(c.execute(select(s.foods).where(s.foods.c.id == food_id)))


def get_food_by_barcode(barcode: str, user_id: int | None = None) -> Row | None:
    """Eigenes Produkt des Nutzers hat Vorrang vor dem OFF-Cache."""
    with _tx() as c:
        if user_id is not None:
            own = _one(
                c.execute(
                    select(s.foods).where(and_(s.foods.c.barcode == barcode, s.foods.c.owner_id == user_id))
                )
            )
            if own:
                return own
        return _one(
            c.execute(
                select(s.foods).where(
                    and_(s.foods.c.barcode == barcode, s.foods.c.source == "off", s.foods.c.owner_id.is_(None))
                )
            )
        )


def search_foods_local(query: str, user_id: int, limit: int = 15) -> list[Row]:
    """Sucht im Cache und in eigenen Produkten (Teilstring, ohne Groß-/Kleinschreibung)."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return []
    conds = [func.lower(s.foods.c.name + " " + func.coalesce(s.foods.c.brand, "")).contains(w) for w in words]
    with _tx() as c:
        return _rows(
            c.execute(
                select(s.foods)
                .where(and_(*conds))
                .where(or_(s.foods.c.owner_id.is_(None), s.foods.c.owner_id == user_id))
                .order_by(s.foods.c.owner_id.desc(), func.length(s.foods.c.name))
                .limit(limit)
            )
        )


# --------------------------------------------------------------------------- Tagebuch

LOG_FIELDS = ("name", "grams", "size_label", "kcal", "protein", "carbs", "fat", "food_id")


def add_entries(
    user_id: int, day: date, meal: str, items: Iterable[Row], source: str, group_id: str | None = None
) -> str:
    """Trägt mehrere Lebensmittel als eine Mahlzeit ein und gibt die Gruppen-ID zurück."""
    group_id = group_id or str(uuid.uuid4())
    rows = []
    for item in items:
        row = {k: item.get(k) for k in LOG_FIELDS}
        for k in ("kcal", "protein", "carbs", "fat"):
            row[k] = float(row[k] or 0)
        rows.append({**row, "user_id": user_id, "date": day, "meal": meal, "source": source, "group_id": group_id})
    if rows:
        with _tx() as c:
            c.execute(insert(s.food_log), rows)
    return group_id


def get_entries(user_id: int, start: date, end: date | None = None) -> list[Row]:
    end = end or start
    with _tx() as c:
        return _rows(
            c.execute(
                select(s.food_log)
                .where(and_(s.food_log.c.user_id == user_id, s.food_log.c.date.between(start, end)))
                .order_by(s.food_log.c.date, s.food_log.c.created_at, s.food_log.c.id)
            )
        )


def update_entry(user_id: int, entry_id: int, **fields: Any) -> None:
    values = {k: v for k, v in fields.items() if k in LOG_FIELDS or k in ("meal", "date")}
    with _tx() as c:
        c.execute(
            update(s.food_log).where(and_(s.food_log.c.id == entry_id, s.food_log.c.user_id == user_id)).values(**values)
        )


def delete_entry(user_id: int, entry_id: int) -> None:
    with _tx() as c:
        c.execute(delete(s.food_log).where(and_(s.food_log.c.id == entry_id, s.food_log.c.user_id == user_id)))


def daily_totals(user_id: int, start: date, end: date) -> dict[date, Row]:
    """Summen je Tag: kcal, protein, carbs, fat, entries."""
    with _tx() as c:
        res = c.execute(
            select(
                s.food_log.c.date,
                func.sum(s.food_log.c.kcal).label("kcal"),
                func.sum(s.food_log.c.protein).label("protein"),
                func.sum(s.food_log.c.carbs).label("carbs"),
                func.sum(s.food_log.c.fat).label("fat"),
                func.count().label("entries"),
            )
            .where(and_(s.food_log.c.user_id == user_id, s.food_log.c.date.between(start, end)))
            .group_by(s.food_log.c.date)
        )
        return {r.date: dict(r._mapping) for r in res}


def meal_totals(user_id: int, start: date, end: date) -> dict[date, dict[str, float]]:
    """kcal je Tag und Mahlzeit – Grundlage für die Mustererkennung."""
    out: dict[date, dict[str, float]] = defaultdict(dict)
    with _tx() as c:
        res = c.execute(
            select(s.food_log.c.date, s.food_log.c.meal, func.sum(s.food_log.c.kcal).label("kcal"))
            .where(and_(s.food_log.c.user_id == user_id, s.food_log.c.date.between(start, end)))
            .group_by(s.food_log.c.date, s.food_log.c.meal)
        )
        for r in res:
            out[r.date][r.meal] = float(r.kcal or 0)
    return dict(out)


def recent_items(user_id: int, limit: int = 12) -> list[Row]:
    """Zuletzt gegessene, eindeutige Lebensmittel (für „Schnell wieder eintragen“)."""
    with _tx() as c:
        rows = _rows(
            c.execute(
                select(s.food_log)
                .where(s.food_log.c.user_id == user_id)
                .order_by(s.food_log.c.id.desc())
                .limit(200)
            )
        )
    seen: set[str] = set()
    out = []
    for r in rows:
        key = r["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- Favoriten


def add_favorite(user_id: int, name: str, meal: str | None, items: list[Row]) -> int:
    clean = [{k: i.get(k) for k in LOG_FIELDS} for i in items]
    with _tx() as c:
        res = c.execute(insert(s.favorites).values(user_id=user_id, name=name, meal=meal, items=clean))
        return res.inserted_primary_key[0]


def list_favorites(user_id: int) -> list[Row]:
    with _tx() as c:
        return _rows(
            c.execute(
                select(s.favorites)
                .where(s.favorites.c.user_id == user_id)
                .order_by(s.favorites.c.use_count.desc(), s.favorites.c.name)
            )
        )


def touch_favorite(user_id: int, fav_id: int) -> None:
    with _tx() as c:
        c.execute(
            update(s.favorites)
            .where(and_(s.favorites.c.id == fav_id, s.favorites.c.user_id == user_id))
            .values(use_count=s.favorites.c.use_count + 1, last_used=_utcnow())
        )


def delete_favorite(user_id: int, fav_id: int) -> None:
    with _tx() as c:
        c.execute(delete(s.favorites).where(and_(s.favorites.c.id == fav_id, s.favorites.c.user_id == user_id)))


# --------------------------------------------------------------------------- Gewicht & Körper


def upsert_weight(user_id: int, day: date, weight_kg: float, source: str = "manuell") -> None:
    with _tx() as c:
        existing = c.execute(
            select(s.weights.c.id).where(and_(s.weights.c.user_id == user_id, s.weights.c.date == day))
        ).first()
        if existing:
            c.execute(update(s.weights).where(s.weights.c.id == existing.id).values(weight_kg=weight_kg, source=source))
        else:
            c.execute(insert(s.weights).values(user_id=user_id, date=day, weight_kg=weight_kg, source=source))


def list_weights(user_id: int, since: date | None = None) -> list[Row]:
    q = select(s.weights).where(s.weights.c.user_id == user_id)
    if since:
        q = q.where(s.weights.c.date >= since)
    with _tx() as c:
        return _rows(c.execute(q.order_by(s.weights.c.date)))


def latest_weight(user_id: int) -> Row | None:
    with _tx() as c:
        return _one(
            c.execute(select(s.weights).where(s.weights.c.user_id == user_id).order_by(s.weights.c.date.desc()).limit(1))
        )


def delete_weight(user_id: int, weight_id: int) -> None:
    with _tx() as c:
        c.execute(delete(s.weights).where(and_(s.weights.c.id == weight_id, s.weights.c.user_id == user_id)))


def add_activities(user_id: int, rows: list[Row]) -> int:
    if not rows:
        return 0
    with _tx() as c:
        c.execute(insert(s.activities), [{**r, "user_id": user_id} for r in rows])
    return len(rows)


def list_activities(user_id: int, since: date | None = None) -> list[Row]:
    q = select(s.activities).where(s.activities.c.user_id == user_id)
    if since:
        q = q.where(s.activities.c.date >= since)
    with _tx() as c:
        return _rows(c.execute(q.order_by(s.activities.c.date)))


WELLBEING_FIELDS = ("energy", "sleep_hours", "sleep_quality", "mood", "hunger", "waist_cm", "note")


def upsert_wellbeing(user_id: int, day: date, **fields: Any) -> None:
    values = {k: v for k, v in fields.items() if k in WELLBEING_FIELDS}
    with _tx() as c:
        existing = c.execute(
            select(s.wellbeing.c.id).where(and_(s.wellbeing.c.user_id == user_id, s.wellbeing.c.date == day))
        ).first()
        if existing:
            c.execute(update(s.wellbeing).where(s.wellbeing.c.id == existing.id).values(**values))
        else:
            c.execute(insert(s.wellbeing).values(user_id=user_id, date=day, **values))


def get_wellbeing(user_id: int, day: date) -> Row | None:
    with _tx() as c:
        return _one(
            c.execute(select(s.wellbeing).where(and_(s.wellbeing.c.user_id == user_id, s.wellbeing.c.date == day)))
        )


def list_wellbeing(user_id: int, since: date | None = None) -> list[Row]:
    q = select(s.wellbeing).where(s.wellbeing.c.user_id == user_id)
    if since:
        q = q.where(s.wellbeing.c.date >= since)
    with _tx() as c:
        return _rows(c.execute(q.order_by(s.wellbeing.c.date)))


def add_strength(user_id: int, day: date, exercise: str, weight_kg: float | None, reps: int | None) -> None:
    with _tx() as c:
        c.execute(
            insert(s.strength).values(user_id=user_id, date=day, exercise=exercise.strip(), weight_kg=weight_kg, reps=reps)
        )


def list_strength(user_id: int) -> list[Row]:
    with _tx() as c:
        return _rows(
            c.execute(select(s.strength).where(s.strength.c.user_id == user_id).order_by(s.strength.c.date))
        )


def delete_strength(user_id: int, row_id: int) -> None:
    with _tx() as c:
        c.execute(delete(s.strength).where(and_(s.strength.c.id == row_id, s.strength.c.user_id == user_id)))


# --------------------------------------------------------------------------- Energieziele


def upsert_target(user_id: int, week_start: date, **values: Any) -> None:
    with _tx() as c:
        existing = c.execute(
            select(s.energy_targets.c.id).where(
                and_(s.energy_targets.c.user_id == user_id, s.energy_targets.c.week_start == week_start)
            )
        ).first()
        if existing:
            c.execute(update(s.energy_targets).where(s.energy_targets.c.id == existing.id).values(**values))
        else:
            c.execute(insert(s.energy_targets).values(user_id=user_id, week_start=week_start, **values))


def target_for_week(user_id: int, week_start: date) -> Row | None:
    """Gültiges Ziel für eine Woche = letzter Eintrag mit week_start ≤ gefragter Woche."""
    with _tx() as c:
        return _one(
            c.execute(
                select(s.energy_targets)
                .where(and_(s.energy_targets.c.user_id == user_id, s.energy_targets.c.week_start <= week_start))
                .order_by(s.energy_targets.c.week_start.desc())
                .limit(1)
            )
        )


def list_targets(user_id: int) -> list[Row]:
    with _tx() as c:
        return _rows(
            c.execute(
                select(s.energy_targets)
                .where(s.energy_targets.c.user_id == user_id)
                .order_by(s.energy_targets.c.week_start)
            )
        )


# --------------------------------------------------------------------------- Flexible Woche & Schichten


def upsert_exception(user_id: int, day: date, planned_kcal: float, note: str = "") -> None:
    with _tx() as c:
        existing = c.execute(
            select(s.day_exceptions.c.id).where(
                and_(s.day_exceptions.c.user_id == user_id, s.day_exceptions.c.date == day)
            )
        ).first()
        vals = {"planned_kcal": planned_kcal, "note": note}
        if existing:
            c.execute(update(s.day_exceptions).where(s.day_exceptions.c.id == existing.id).values(**vals))
        else:
            c.execute(insert(s.day_exceptions).values(user_id=user_id, date=day, **vals))


def list_exceptions(user_id: int, start: date, end: date) -> list[Row]:
    with _tx() as c:
        return _rows(
            c.execute(
                select(s.day_exceptions)
                .where(and_(s.day_exceptions.c.user_id == user_id, s.day_exceptions.c.date.between(start, end)))
                .order_by(s.day_exceptions.c.date)
            )
        )


def delete_exception(user_id: int, exc_id: int) -> None:
    with _tx() as c:
        c.execute(
            delete(s.day_exceptions).where(and_(s.day_exceptions.c.id == exc_id, s.day_exceptions.c.user_id == user_id))
        )


def set_shift(user_id: int, day: date, shift: str | None) -> None:
    """Setzt die Schicht für ein Datum; None entfernt die Ausnahme (→ Wochenmuster gilt)."""
    with _tx() as c:
        c.execute(delete(s.shift_days).where(and_(s.shift_days.c.user_id == user_id, s.shift_days.c.date == day)))
        if shift:
            c.execute(insert(s.shift_days).values(user_id=user_id, date=day, shift=shift))


def get_shifts(user_id: int, start: date, end: date) -> dict[date, str]:
    with _tx() as c:
        res = c.execute(
            select(s.shift_days.c.date, s.shift_days.c.shift).where(
                and_(s.shift_days.c.user_id == user_id, s.shift_days.c.date.between(start, end))
            )
        )
        return {r.date: r.shift for r in res}


# --------------------------------------------------------------------------- Pläne & Einkauf


def save_plan(user_id: int, week_start: date, params: Row, plan: Row) -> int:
    with _tx() as c:
        res = c.execute(insert(s.meal_plans).values(user_id=user_id, week_start=week_start, params=params, plan=plan))
        return res.inserted_primary_key[0]


def latest_plan(user_id: int) -> Row | None:
    with _tx() as c:
        return _one(
            c.execute(
                select(s.meal_plans).where(s.meal_plans.c.user_id == user_id).order_by(s.meal_plans.c.id.desc()).limit(1)
            )
        )


def update_plan(user_id: int, plan_id: int, plan: Row, params: Row | None = None) -> None:
    values: Row = {"plan": plan}
    if params is not None:
        values["params"] = params
    with _tx() as c:
        c.execute(
            update(s.meal_plans)
            .where(and_(s.meal_plans.c.id == plan_id, s.meal_plans.c.user_id == user_id))
            .values(**values)
        )


def replace_shopping(user_id: int, plan_id: int | None, items: list[Row]) -> None:
    """Ersetzt die generierten Einträge; eigene Einträge bleiben erhalten."""
    with _tx() as c:
        c.execute(
            delete(s.shopping_items).where(
                and_(s.shopping_items.c.user_id == user_id, s.shopping_items.c.custom.is_(False))
            )
        )
        if items:
            c.execute(
                insert(s.shopping_items),
                [
                    {
                        "user_id": user_id,
                        "plan_id": plan_id,
                        "name": i["name"],
                        "qty": i.get("qty"),
                        "unit": i.get("unit"),
                        "section": i["section"],
                        "checked": False,
                        "custom": False,
                    }
                    for i in items
                ],
            )


def list_shopping(user_id: int) -> list[Row]:
    with _tx() as c:
        return _rows(
            c.execute(
                select(s.shopping_items)
                .where(s.shopping_items.c.user_id == user_id)
                .order_by(s.shopping_items.c.section, s.shopping_items.c.name)
            )
        )


def add_shopping_item(user_id: int, name: str, section: str, qty: float | None = None, unit: str | None = None) -> None:
    with _tx() as c:
        c.execute(
            insert(s.shopping_items).values(
                user_id=user_id, name=name, section=section, qty=qty, unit=unit, custom=True, checked=False
            )
        )


def set_shopping_checked(user_id: int, item_id: int, checked: bool) -> None:
    with _tx() as c:
        c.execute(
            update(s.shopping_items)
            .where(and_(s.shopping_items.c.id == item_id, s.shopping_items.c.user_id == user_id))
            .values(checked=checked)
        )


def clear_shopping(user_id: int, only_checked: bool = True) -> None:
    q = delete(s.shopping_items).where(s.shopping_items.c.user_id == user_id)
    if only_checked:
        q = q.where(s.shopping_items.c.checked.is_(True))
    with _tx() as c:
        c.execute(q)


def list_prices(user_id: int) -> list[Row]:
    with _tx() as c:
        return _rows(c.execute(select(s.prices).where(s.prices.c.user_id == user_id).order_by(s.prices.c.section, s.prices.c.item)))


def replace_prices(user_id: int, rows: list[Row]) -> None:
    with _tx() as c:
        c.execute(delete(s.prices).where(s.prices.c.user_id == user_id))
        if rows:
            c.execute(
                insert(s.prices),
                [
                    {
                        "user_id": user_id,
                        "item": r["item"],
                        "unit": r["unit"],
                        "pack_qty": float(r["pack_qty"]),
                        "price_eur": float(r["price_eur"]),
                        "section": r["section"],
                    }
                    for r in rows
                ],
            )


# --------------------------------------------------------------------------- Coach


def add_coach_message(user_id: int, role: str, content: str) -> None:
    with _tx() as c:
        c.execute(insert(s.coach_messages).values(user_id=user_id, role=role, content=content))


def list_coach_messages(user_id: int, limit: int = 40) -> list[Row]:
    with _tx() as c:
        rows = _rows(
            c.execute(
                select(s.coach_messages)
                .where(s.coach_messages.c.user_id == user_id)
                .order_by(s.coach_messages.c.id.desc())
                .limit(limit)
            )
        )
    return list(reversed(rows))


def clear_coach_messages(user_id: int) -> None:
    with _tx() as c:
        c.execute(delete(s.coach_messages).where(s.coach_messages.c.user_id == user_id))


def save_report(user_id: int, week_start: date, content: str) -> None:
    with _tx() as c:
        c.execute(
            delete(s.coach_reports).where(
                and_(s.coach_reports.c.user_id == user_id, s.coach_reports.c.week_start == week_start)
            )
        )
        c.execute(insert(s.coach_reports).values(user_id=user_id, week_start=week_start, content=content))


def get_report(user_id: int, week_start: date) -> Row | None:
    with _tx() as c:
        return _one(
            c.execute(
                select(s.coach_reports).where(
                    and_(s.coach_reports.c.user_id == user_id, s.coach_reports.c.week_start == week_start)
                )
            )
        )


# --------------------------------------------------------------------------- Export


def export_user_data(user_id: int) -> dict[str, list[Row]]:
    """Alle Daten eines Nutzers, tabellenweise (ohne Passwort-Hash und Tokens)."""
    out: dict[str, list[Row]] = {}
    with _tx() as c:
        user = _one(c.execute(select(s.users.c.email, s.users.c.tier, s.users.c.created_at).where(s.users.c.id == user_id)))
        out["konto"] = [user] if user else []
        out["profil"] = _rows(c.execute(select(s.profiles).where(s.profiles.c.user_id == user_id)))
        for table in s.USER_TABLES:
            if table is s.auth_tokens:
                continue
            out[table.name] = _rows(c.execute(select(table).where(table.c.user_id == user_id)))
        out["eigene_produkte"] = _rows(c.execute(select(s.foods).where(s.foods.c.owner_id == user_id)))
    return out
