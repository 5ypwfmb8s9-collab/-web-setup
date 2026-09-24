from datetime import date

import pytest

from db import repo
from services import auth


def test_password_hash_roundtrip():
    h = auth.hash_password("sehr-geheim-1")
    assert auth.verify_password("sehr-geheim-1", h)
    assert not auth.verify_password("falsch", h)


def test_register_and_login():
    uid = auth.register("Anna@Example.de ", "passwort123")
    assert auth.login("anna@example.de", "passwort123") == uid
    with pytest.raises(auth.AuthError):
        auth.register("anna@example.de", "passwort123")
    with pytest.raises(auth.AuthError):
        auth.login("anna@example.de", "falsch123")


def test_weak_password_rejected():
    with pytest.raises(auth.AuthError):
        auth.register("b@example.de", "kurz")
    with pytest.raises(auth.AuthError):
        auth.register("b@example.de", "nurbuchstaben")


def test_lockout_after_failed_attempts():
    auth.register("c@example.de", "passwort123")
    for _ in range(auth.MAX_FAILED):
        with pytest.raises(auth.AuthError):
            auth.login("c@example.de", "falsch")
    with pytest.raises(auth.AuthError, match="Zu viele Versuche"):
        auth.login("c@example.de", "passwort123")


def test_remember_token(user_id):
    issued = auth.issue_token(user_id)
    assert auth.user_for_token(issued.token) == user_id
    auth.revoke_token(issued.token)
    assert auth.user_for_token(issued.token) is None
    assert auth.user_for_token("unsinn") is None


def test_delete_user_removes_everything(user_id):
    repo.upsert_weight(user_id, date(2026, 1, 1), 80)
    repo.add_entries(user_id, date(2026, 1, 1), "mittag", [{"name": "Apfel", "kcal": 80}], "manuell")
    repo.add_favorite(user_id, "Frühstück", "fruehstueck", [{"name": "Apfel", "kcal": 80}])
    repo.add_coach_message(user_id, "user", "Hallo")
    auth.issue_token(user_id)
    repo.delete_user(user_id)
    assert repo.get_user(user_id) is None
    data = repo.export_user_data(user_id)
    assert all(len(rows) == 0 for rows in data.values())


def test_weight_upsert_one_per_day(user_id):
    repo.upsert_weight(user_id, date(2026, 1, 1), 80)
    repo.upsert_weight(user_id, date(2026, 1, 1), 79.5)
    rows = repo.list_weights(user_id)
    assert len(rows) == 1 and rows[0]["weight_kg"] == 79.5
