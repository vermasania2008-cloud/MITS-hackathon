"""SQLite-backed account authentication for the sustainability planner."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

DATABASE_PATH = Path(__file__).with_name("users.db")
_PASSWORD_ITERATIONS = 310_000
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class User:
    id: int
    full_name: str
    email: str


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create the account table when the application is first started."""
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if len(normalized) > 254 or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", maxsplit=1)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def register_user(full_name: str, email: str, password: str) -> User:
    """Create an account and return its public profile."""
    name = full_name.strip()
    normalized_email = _normalize_email(email)
    if not name or len(name) > 100:
        raise ValueError("Name must be between 1 and 100 characters.")
    if not 8 <= len(password) <= 128:
        raise ValueError("Password must be between 8 and 128 characters.")

    init_db()
    try:
        with closing(_connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO users (full_name, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (name, normalized_email, _hash_password(password)),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("An account with this email already exists.") from error

    return User(id=user_id, full_name=name, email=normalized_email)


def authenticate_user(email: str, password: str) -> User | None:
    """Return a user's public profile when the credentials are valid."""
    normalized_email = _normalize_email(email)
    if not password or len(password) > 128:
        return None

    init_db()
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            """
            SELECT id, full_name, email, password_hash
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()

    if row is None or not _verify_password(password, row["password_hash"]):
        return None

    return User(id=row["id"], full_name=row["full_name"], email=row["email"])
