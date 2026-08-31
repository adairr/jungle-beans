"""SQLite persistence for player accounts, saved games, and the leaderboard.

Kept deliberately simple (stdlib sqlite3, no ORM) — this is a friends-and-
colleagues playtesting app, not a production service. Passwords are hashed
with werkzeug's built-in hashing (already a dependency via Flask), never
stored in plaintext.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).resolve().parents[2] / "jungle_beans.db"

# `name` is the login identity and what shows on the leaderboard; `email` is
# optional (kept for a possible future contact/recovery use, not used to log
# in). SQLite can't add a UNIQUE NOT NULL column to an existing table via
# ALTER TABLE, so `name` is added nullable here and backfilled/indexed by
# _migrate() below for databases created before this column existed.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    game_json TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    UNIQUE(user_id, name)
);
CREATE TABLE IF NOT EXISTS wins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    days INTEGER NOT NULL,
    net_worth INTEGER NOT NULL,
    won_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT,
    email TEXT,
    event TEXT NOT NULL,
    ip_address TEXT,
    at TEXT NOT NULL
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_info(conn: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing (email-only) database up to the name+optional-
    email schema, without touching anyone's password or losing accounts."""
    user_cols = _table_info(conn, "users")
    # Older databases have `email TEXT UNIQUE NOT NULL`. SQLite can't drop a
    # NOT NULL constraint (or add one that's UNIQUE-and-nullable) via ALTER
    # TABLE, so when that's the case — or `name` is simply missing — rebuild
    # the table: rename it aside, recreate with the new schema, copy every
    # row across by id (preserving all foreign keys in saves/wins/
    # access_log), then drop the old copy.
    needs_rebuild = "name" not in user_cols or (
        "email" in user_cols and user_cols["email"]["notnull"]
    )
    if needs_rebuild:
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.execute(
            """CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        if "name" in user_cols:
            conn.execute(
                """INSERT INTO users (id, name, email, password_hash, created_at)
                   SELECT id, name, email, password_hash, created_at FROM users_old"""
            )
        else:
            conn.execute(
                """INSERT INTO users (id, email, password_hash, created_at)
                   SELECT id, email, password_hash, created_at FROM users_old"""
            )
        conn.execute("DROP TABLE users_old")
        # Backfill existing accounts (which all had a required email) with a
        # name derived from their email's local part, so their password
        # keeps working — they just log in with that name from now on.
        conn.execute(
            """UPDATE users SET name = substr(email, 1, instr(email, '@') - 1)
               WHERE name IS NULL AND email IS NOT NULL AND instr(email, '@') > 0"""
        )
        conn.execute("UPDATE users SET name = 'player' || id WHERE name IS NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_name ON users(name)")

    log_cols = _table_info(conn, "access_log")
    # Same story as users.email above: the original access_log had
    # `email TEXT NOT NULL`, which ALTER TABLE can't relax, so a plain
    # ADD COLUMN for `name` isn't enough on its own — every future insert
    # with email=NULL (the whole point of making it optional) would still
    # violate the old NOT NULL constraint on the email column itself.
    log_needs_rebuild = "name" not in log_cols or (
        "email" in log_cols and log_cols["email"]["notnull"]
    )
    if log_needs_rebuild:
        conn.execute("ALTER TABLE access_log RENAME TO access_log_old")
        conn.execute(
            """CREATE TABLE access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT,
                email TEXT,
                event TEXT NOT NULL,
                ip_address TEXT,
                at TEXT NOT NULL
            )"""
        )
        if "name" in log_cols:
            conn.execute(
                """INSERT INTO access_log (id, user_id, name, email, event, ip_address, at)
                   SELECT id, user_id, name, email, event, ip_address, at FROM access_log_old"""
            )
        else:
            conn.execute(
                """INSERT INTO access_log (id, user_id, email, event, ip_address, at)
                   SELECT id, user_id, email, event, ip_address, at FROM access_log_old"""
            )
        conn.execute("DROP TABLE access_log_old")
        conn.execute("UPDATE access_log SET name = email WHERE name IS NULL")


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def register_user(name: str, password: str, email: str | None = None) -> dict:
    name = name.strip()
    if not name:
        return {"ok": False, "error": "Enter a name."}
    if len(password) < 4:
        return {"ok": False, "error": "Password must be at least 4 characters."}
    email = (email or "").strip().lower() or None
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        return {"ok": False, "error": "That doesn't look like a valid email address."}
    with _connect() as conn:
        if conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone():
            return {"ok": False, "error": "That name is already taken."}
        if email and conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            return {"ok": False, "error": "An account with that email already exists."}
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()),
        )
        return {"ok": True, "user_id": cur.lastrowid, "name": name, "email": email}


def authenticate(name: str, password: str) -> dict:
    name = name.strip()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, password_hash, email FROM users WHERE name = ?", (name,)
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return {"ok": False, "error": "Incorrect name or password."}
    return {"ok": True, "user_id": row["id"], "name": name, "email": row["email"]}


def save_game(user_id: int, name: str, game_dict: dict) -> str:
    safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_ ").strip() or "save"
    with _connect() as conn:
        conn.execute(
            """INSERT INTO saves (user_id, name, game_json, saved_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, name) DO UPDATE SET
                 game_json = excluded.game_json, saved_at = excluded.saved_at""",
            (user_id, safe_name, json.dumps(game_dict), datetime.now(timezone.utc).isoformat()),
        )
    return safe_name


def load_game(user_id: int, name: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT game_json FROM saves WHERE user_id = ? AND name = ?", (user_id, name)
        ).fetchone()
    return json.loads(row["game_json"]) if row else None


def list_saves(user_id: int) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM saves WHERE user_id = ? ORDER BY saved_at DESC", (user_id,)
        ).fetchall()
    return [r["name"] for r in rows]


def record_win(user_id: int, days: int, net_worth: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO wins (user_id, days, net_worth, won_at) VALUES (?, ?, ?, ?)",
            (user_id, days, net_worth, datetime.now(timezone.utc).isoformat()),
        )


def log_access(user_id: int, name: str, email: str | None, event: str, ip_address: str | None) -> None:
    """event: "register" or "login" — who tried the game, and when."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO access_log (user_id, name, email, event, ip_address, at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, email, event, ip_address, datetime.now(timezone.utc).isoformat()),
        )


def access_log(limit: int = 200) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name, email, event, ip_address, at FROM access_log ORDER BY at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def leaderboard(limit: int = 25) -> list[dict]:
    """Wins ranked by fastest days-to-win, then earliest if tied."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT users.name AS name, wins.days AS days,
                      wins.net_worth AS net_worth, wins.won_at AS won_at
               FROM wins JOIN users ON users.id = wins.user_id
               ORDER BY wins.days ASC, wins.won_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
