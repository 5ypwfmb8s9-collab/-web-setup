"""Rauchtest: Jede Seite rendert mit Demodaten ohne Exception (Streamlit AppTest)."""

import runpy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["heute", "tracken", "plan", "fortschritt", "coach", "profil"]


@pytest.fixture
def demo_user(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["seed_demo.py", "smoke@kano.test", "smoke1234"])
    runpy.run_path(str(ROOT / "scripts" / "seed_demo.py"), run_name="__main__")
    from db import repo

    return repo.get_user_by_email("smoke@kano.test")["id"]


def _run(uid, page: str | None = None, hide=False, approx=False):
    from db import repo

    repo.update_profile(uid, hide_numbers=hide, approx_mode=approx)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["user_id"] = uid
    at.run()
    if page:
        at.switch_page(f"pages/{page}.py")
        at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_pages_render(demo_user, page):
    at = _run(demo_user, page)
    assert not at.exception, [e.value for e in at.exception]
    html = " ".join(h.proto.body for h in at.get("html"))
    assert "kano-title" in html  # die Seite selbst (nicht nur der Rahmen) wurde gerendert


@pytest.mark.parametrize("page", ["heute", "tracken", "fortschritt", "plan"])
def test_pages_render_hidden_numbers_and_approx(demo_user, page):
    at = _run(demo_user, page, hide=True, approx=True)
    assert not at.exception, [e.value for e in at.exception]
    if page == "heute":
        text = " ".join(h.proto.body for h in at.get("html"))
        assert "kcal übrig" not in text


def test_login_page_for_anonymous():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Konto erstellen" in t.label for t in at.tabs)


def test_database_outage_shows_friendly_message(demo_user, monkeypatch):
    """Fällt die Datenbank mitten in einer Seite aus, erscheint ein Hinweis statt eines Stacktraces."""
    from sqlalchemy.exc import OperationalError

    from db import repo

    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("Verbindung verloren"))

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["user_id"] = demo_user
    at.run()
    monkeypatch.setattr(repo, "get_entries", broken)
    at.run()
    assert not at.exception
    html = " ".join(h.proto.body for h in at.get("html"))
    assert "Datenbank ist gerade nicht erreichbar" in html
