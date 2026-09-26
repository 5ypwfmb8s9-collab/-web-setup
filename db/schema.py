"""Tabellendefinitionen (SQLAlchemy Core, kompatibel mit SQLite und PostgreSQL)."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()


def _user_fk() -> Column:
    return Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("tier", String(20), nullable=False, server_default="free"),  # Feature-Flag free/premium
    Column("failed_logins", Integer, nullable=False, server_default="0"),
    Column("locked_until", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

auth_tokens = Table(
    "auth_tokens",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("token_hash", String(128), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

profiles = Table(
    "profiles",
    metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("name", String(80)),
    Column("sex", String(1)),
    Column("birth_year", Integer),
    Column("height_cm", Float),
    Column("activity", String(20), server_default="leicht"),
    Column("goal", String(20), server_default="abnehmen"),
    Column("pace_kg_week", Float, server_default="0.5"),
    Column("goal_weight_kg", Float),
    Column("diet_type", String(20), server_default="ausgewogen"),
    Column("dislikes", Text, server_default=""),
    Column("hide_numbers", Boolean, nullable=False, server_default="0"),
    Column("approx_mode", Boolean, nullable=False, server_default="0"),
    Column("ai_consent", Boolean, nullable=False, server_default="0"),
    Column("household_size", Integer, nullable=False, server_default="1"),
    Column("weekly_budget_eur", Float),
    Column("shift_pattern", JSON),  # {"0": "frueh", ...} Wochentag → Schicht
    Column("care_flag", Boolean, nullable=False, server_default="0"),  # kein Defizit (s. Onboarding)
    Column("onboarding_done", Boolean, nullable=False, server_default="0"),
    Column("disclaimer_accepted_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

foods = Table(
    "foods",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source", String(10), nullable=False),  # off | custom
    Column("barcode", String(32)),
    Column("owner_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),  # nur bei eigenen Produkten
    Column("name", String(255), nullable=False),
    Column("brand", String(255)),
    Column("kcal_100g", Float, nullable=False),
    Column("protein_100g", Float),
    Column("carbs_100g", Float),
    Column("fat_100g", Float),
    Column("fiber_100g", Float),
    Column("serving_g", Float),
    Column("fetched_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("source", "barcode", "owner_id", name="uq_foods_source_barcode_owner"),
)
Index("ix_foods_name", foods.c.name)

food_log = Table(
    "food_log",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("meal", String(20), nullable=False),  # fruehstueck | mittag | abend | snack
    Column("name", String(255), nullable=False),
    Column("grams", Float),
    Column("size_label", String(10)),  # klein | mittel | gross (Ungefähr-Modus)
    Column("kcal", Float, nullable=False, server_default="0"),
    Column("protein", Float, server_default="0"),
    Column("carbs", Float, server_default="0"),
    Column("fat", Float, server_default="0"),
    Column("source", String(20)),  # suche | barcode | freitext | foto | favorit | plan | manuell
    Column("food_id", Integer, ForeignKey("foods.id", ondelete="SET NULL")),
    Column("group_id", String(36)),  # gemeinsam eingetragene Mahlzeit
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
Index("ix_food_log_user_date", food_log.c.user_id, food_log.c.date)

favorites = Table(
    "favorites",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("name", String(255), nullable=False),
    Column("meal", String(20)),
    Column("items", JSON, nullable=False),
    Column("use_count", Integer, nullable=False, server_default="0"),
    Column("last_used", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

weights = Table(
    "weights",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("weight_kg", Float, nullable=False),
    Column("source", String(20), server_default="manuell"),
    UniqueConstraint("user_id", "date", name="uq_weights_user_date"),
)

activities = Table(
    "activities",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("kind", String(80)),
    Column("kcal", Float),
    Column("steps", Integer),
    Column("minutes", Float),
    Column("source", String(20), server_default="import"),
)

wellbeing = Table(
    "wellbeing",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("energy", Integer),  # 1–10
    Column("sleep_hours", Float),
    Column("sleep_quality", Integer),  # 1–10
    Column("mood", Integer),  # 1–10 Wohlbefinden
    Column("hunger", Integer),  # 1–10
    Column("waist_cm", Float),
    Column("note", Text),
    UniqueConstraint("user_id", "date", name="uq_wellbeing_user_date"),
)

strength = Table(
    "strength",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("exercise", String(80), nullable=False),
    Column("weight_kg", Float),
    Column("reps", Integer),
)

energy_targets = Table(
    "energy_targets",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("week_start", Date, nullable=False),
    Column("tdee", Float, nullable=False),
    Column("target_kcal", Float, nullable=False),
    Column("method", String(20), nullable=False),  # formel | adaptiv
    Column("confidence", Float, server_default="0"),
    Column("explanation", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("user_id", "week_start", name="uq_targets_user_week"),
)

day_exceptions = Table(
    "day_exceptions",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("planned_kcal", Float, nullable=False),
    Column("note", String(120)),
    UniqueConstraint("user_id", "date", name="uq_exceptions_user_date"),
)

shift_days = Table(
    "shift_days",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("date", Date, nullable=False),
    Column("shift", String(10), nullable=False),
    UniqueConstraint("user_id", "date", name="uq_shift_user_date"),
)

meal_plans = Table(
    "meal_plans",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("week_start", Date, nullable=False),
    Column("params", JSON, nullable=False),
    Column("plan", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

shopping_items = Table(
    "shopping_items",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("plan_id", Integer, ForeignKey("meal_plans.id", ondelete="CASCADE")),
    Column("name", String(255), nullable=False),
    Column("qty", Float),
    Column("unit", String(20)),
    Column("section", String(40), nullable=False),
    Column("checked", Boolean, nullable=False, server_default="0"),
    Column("custom", Boolean, nullable=False, server_default="0"),
)

prices = Table(
    "prices",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("item", String(120), nullable=False),
    Column("unit", String(10), nullable=False),  # g | ml | Stk
    Column("pack_qty", Float, nullable=False),
    Column("price_eur", Float, nullable=False),
    Column("section", String(40), nullable=False),
    UniqueConstraint("user_id", "item", name="uq_prices_user_item"),
)

coach_messages = Table(
    "coach_messages",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("role", String(10), nullable=False),  # user | assistant
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

coach_reports = Table(
    "coach_reports",
    metadata,
    Column("id", Integer, primary_key=True),
    _user_fk(),
    Column("week_start", Date, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("user_id", "week_start", name="uq_reports_user_week"),
)

# Reihenfolge fürs vollständige Löschen/Exportieren eines Kontos
USER_TABLES = [
    auth_tokens,
    food_log,
    favorites,
    weights,
    activities,
    wellbeing,
    strength,
    energy_targets,
    day_exceptions,
    shift_days,
    shopping_items,
    meal_plans,
    prices,
    coach_messages,
    coach_reports,
]
