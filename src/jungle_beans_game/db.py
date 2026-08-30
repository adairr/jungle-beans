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

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
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
    email TEXT NOT NULL,
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


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def register_user(email: str, password: str) -> dict:
    email = email.strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"ok": False, "error": "Enter a valid email address."}
    if len(password) < 4:
        return {"ok": False, "error": "Password must be at least 4 characters."}
    with _connect() as conn:
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            return {"ok": False, "error": "An account with that email already exists."}
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()),
        )
        return {"ok": True, "user_id": cur.lastrowid, "email": email}


def authenticate(email: str, password: str) -> dict:
    email = email.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return {"ok": False, "error": "Incorrect email or password."}
    return {"ok": True, "user_id": row["id"], "email": email}


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


def log_access(user_id: int, email: str, event: str, ip_address: str | None) -> None:
    """event: "register" or "login" — who tried the game, and when."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO access_log (user_id, email, event, ip_address, at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, event, ip_address, datetime.now(timezone.utc).isoformat()),
        )


def access_log(limit: int = 200) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT email, event, ip_address, at FROM access_log ORDER BY at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def leaderboard(limit: int = 25) -> list[dict]:
    """Wins ranked by fastest days-to-win, then earliest if tied."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT users.email AS email, wins.days AS days,
                      wins.net_worth AS net_worth, wins.won_at AS won_at
               FROM wins JOIN users ON users.id = wins.user_id
               ORDER BY wins.days ASC, wins.won_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
