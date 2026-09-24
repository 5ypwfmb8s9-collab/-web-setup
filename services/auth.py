"""Registrierung, Anmeldung und „Angemeldet bleiben“.

* Passwörter werden mit scrypt (Standardbibliothek) und zufälligem Salt gehasht.
* Nach 5 Fehlversuchen ist das Konto 10 Minuten gesperrt (Schutz gegen Durchprobieren).
* „Angemeldet bleiben“ nutzt ein zufälliges Token; in der Datenbank liegt nur dessen
  SHA-256-Hash, damit ein Datenbank-Leak keine gültigen Sitzungen preisgibt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from db import repo

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MAX_FAILED = 5
LOCK_MINUTES = 10
TOKEN_DAYS = 30
MIN_PASSWORD_LEN = 8

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """Fehler mit nutzerfreundlicher deutscher Meldung."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"Das Passwort braucht mindestens {MIN_PASSWORD_LEN} Zeichen.")
    if password.isdigit() or password.isalpha():
        raise AuthError("Bitte kombiniere Buchstaben mit Zahlen oder Sonderzeichen.")


def register(email: str, password: str) -> int:
    email = normalize_email(email)
    if not EMAIL_RE.match(email):
        raise AuthError("Bitte gib eine gültige E-Mail-Adresse ein.")
    validate_new_password(password)
    if repo.get_user_by_email(email):
        raise AuthError("Für diese E-Mail-Adresse gibt es bereits ein Konto.")
    return repo.create_user(email, hash_password(password))


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def login(email: str, password: str) -> int:
    """Gibt die User-ID zurück oder wirft AuthError (bewusst ohne Hinweis, ob die E-Mail existiert)."""
    user = repo.get_user_by_email(normalize_email(email))
    generic = AuthError("E-Mail oder Passwort stimmen nicht.")
    if not user:
        hash_password(password)  # gleiche Rechenzeit wie bei existierendem Konto
        raise generic
    now = datetime.now(timezone.utc)
    locked = _aware(user["locked_until"])
    if locked and locked > now:
        minutes = max(1, int((locked - now).total_seconds() // 60) + 1)
        raise AuthError(f"Zu viele Versuche. Bitte in {minutes} Minuten erneut probieren.")
    if not verify_password(password, user["password_hash"]):
        failed = (user["failed_logins"] or 0) + 1
        lock = now + timedelta(minutes=LOCK_MINUTES) if failed >= MAX_FAILED else None
        repo.set_login_state(user["id"], 0 if lock else failed, lock)
        raise generic
    if user["failed_logins"] or user["locked_until"]:
        repo.set_login_state(user["id"], 0, None)
    return user["id"]


def change_password(user_id: int, old: str, new: str) -> None:
    user = repo.get_user(user_id)
    if not user or not verify_password(old, user["password_hash"]):
        raise AuthError("Das aktuelle Passwort stimmt nicht.")
    validate_new_password(new)
    repo.update_password(user_id, hash_password(new))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class IssuedToken:
    token: str
    max_age_seconds: int


def issue_token(user_id: int) -> IssuedToken:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    repo.add_token(user_id, _token_hash(token), expires)
    return IssuedToken(token=token, max_age_seconds=TOKEN_DAYS * 86400)


def user_for_token(token: str | None) -> int | None:
    if not isinstance(token, str) or not token or len(token) > 200:
        return None
    return repo.user_id_for_token(_token_hash(token))


def revoke_token(token: str | None) -> None:
    if token:
        repo.delete_token(_token_hash(token))
