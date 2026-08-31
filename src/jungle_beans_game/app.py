"""Flask app serving the Jungle Beans dashboard and game API."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, render_template, request, session

from . import data, db
from .engine import GameState

app = Flask(__name__)
# A fixed secret (via env var) keeps player sessions alive across server
# restarts; the random fallback is fine for solo local dev, where losing
# your session on restart is a non-issue.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=30)

db.init_db()

# One GameState per logged-in user, not one shared global — otherwise two
# people hitting a hosted instance at once would be playing the same
# wallet/location/inventory. Keyed by the DB user id, so it's stable across
# devices/browsers for the same account (not just per-cookie).
GAMES: dict[int, GameState] = {}


def current_user_id() -> int | None:
    return session.get("user_id")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user_id() is None:
            return jsonify({"ok": False, "error": "Not logged in."}), 401
        return view(*args, **kwargs)

    return wrapped


def get_game() -> GameState:
    uid = current_user_id()
    if uid not in GAMES:
        GAMES[uid] = GameState()
    return GAMES[uid]


def _finalize(game: GameState) -> dict:
    """Record a leaderboard entry the moment a game is won, exactly once, and
    attach the account-scoped bits (saves, name) that GameState itself has
    no business knowing about."""
    uid = current_user_id()
    if game.win and not game.win_recorded:
        db.record_win(uid, game.day, game.net_worth())
        game.win_recorded = True
    state = game.public_state()
    state["saves"] = db.list_saves(uid)
    state["name"] = session.get("name")
    return state


@app.get("/")
def index():
    if current_user_id() is None:
        return render_template("login.html")
    sell_pct = round(100 * (1 - data.SELL_SPREAD_PCT))
    return render_template("index.html", sell_pct=sell_pct, name=session.get("name"))


@app.get("/mobile")
def mobile():
    if current_user_id() is None:
        return render_template("login.html")
    sell_pct = round(100 * (1 - data.SELL_SPREAD_PCT))
    return render_template("mobile.html", sell_pct=sell_pct, name=session.get("name"))


@app.get("/about")
def about():
    return render_template("about.html")


@app.get("/leaderboard")
def leaderboard_page():
    rows = db.leaderboard()
    for row in rows:
        try:
            row["won_at_display"] = datetime.fromisoformat(row["won_at"]).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            row["won_at_display"] = row["won_at"]
    return render_template("leaderboard.html", rows=rows)


@app.post("/api/register")
def api_register():
    payload = request.get_json(force=True) or {}
    result = db.register_user(
        payload.get("name", ""), payload.get("password", ""), payload.get("email") or None
    )
    if not result["ok"]:
        return jsonify(result)
    session.permanent = True
    session["user_id"] = result["user_id"]
    session["name"] = result["name"]
    db.log_access(result["user_id"], result["name"], result.get("email"), "register", request.remote_addr)
    return jsonify({"ok": True})


@app.post("/api/login")
def api_login():
    payload = request.get_json(force=True) or {}
    result = db.authenticate(payload.get("name", ""), payload.get("password", ""))
    if not result["ok"]:
        return jsonify(result)
    session.permanent = True
    session["user_id"] = result["user_id"]
    session["name"] = result["name"]
    db.log_access(result["user_id"], result["name"], result.get("email"), "login", request.remote_addr)
    return jsonify({"ok": True})


@app.post("/api/reset-password")
def api_reset_password():
    payload = request.get_json(force=True) or {}
    result = db.reset_password(payload.get("name", ""), payload.get("password", ""))
    if not result["ok"]:
        return jsonify(result)
    session.permanent = True
    session["user_id"] = result["user_id"]
    session["name"] = result["name"]
    db.log_access(result["user_id"], result["name"], result.get("email"), "password_reset", request.remote_addr)
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/state")
@login_required
def api_state():
    return jsonify(_finalize(get_game()))


@app.post("/api/buy")
@login_required
def api_buy():
    game = get_game()
    payload = request.get_json(force=True) or {}
    result = game.buy(payload.get("product"), int(payload.get("qty", 0)))
    return jsonify({**result, "state": _finalize(game)})


@app.post("/api/sell")
@login_required
def api_sell():
    game = get_game()
    payload = request.get_json(force=True) or {}
    result = game.attempt_sale(payload.get("product"), int(payload.get("qty", 0)))
    return jsonify({**result, "state": _finalize(game)})


@app.post("/api/travel")
@login_required
def api_travel():
    game = get_game()
    payload = request.get_json(force=True) or {}
    result = game.travel(payload.get("destination"))
    return jsonify({**result, "state": _finalize(game)})


@app.post("/api/reset")
@login_required
def api_reset():
    game = get_game()
    game.new_game()
    return jsonify({"ok": True, "state": _finalize(game)})


@app.post("/api/save")
@login_required
def api_save():
    game = get_game()
    payload = request.get_json(force=True) or {}
    name = payload.get("name") or "save"
    saved_name = db.save_game(current_user_id(), name, game.to_dict())
    game.note_saved(saved_name)
    return jsonify({"ok": True, "name": saved_name, "state": _finalize(game)})


@app.post("/api/load")
@login_required
def api_load():
    uid = current_user_id()
    payload = request.get_json(force=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Pick a save to load."})
    game_dict = db.load_game(uid, name)
    if game_dict is None:
        return jsonify({"ok": False, "error": f"No save named '{name}'."})
    GAMES[uid] = GameState.from_dict(game_dict)
    return jsonify({"ok": True, "state": _finalize(GAMES[uid])})


def main() -> None:
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, port=5050)


if __name__ == "__main__":
    main()
