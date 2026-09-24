"""Gemeinsame Test-Fixtures: jede Testfunktion bekommt eine frische SQLite-Datenbank."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import engine as db_engine  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    db_engine.set_engine(db_engine.make_engine(url))
    yield
    db_engine.set_engine(None)  # type: ignore[arg-type]


@pytest.fixture
def user_id():
    from db import repo
    from services import auth

    uid = repo.create_user("test@kano.de", auth.hash_password("geheim1234"))
    repo.update_profile(
        uid, sex="w", birth_year=1990, height_cm=168, activity="leicht", goal="abnehmen",
        pace_kg_week=0.5, diet_type="ausgewogen", onboarding_done=True, ai_consent=True,
    )
    return uid
