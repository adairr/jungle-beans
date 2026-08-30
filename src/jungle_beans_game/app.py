"""Flask app serving the Jungle Beans dashboard and game API."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from flask import Flask, jsonify, render_template, request, session

from . import data
from .engine import GameState

app = Flask(__name__)
# A fixed secret (via env var) keeps player sessions alive across server
# restarts; the random fallback is fine for solo local dev, where losing
# your session on restart is a non-issue.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=30)

# One GameState per browser session, not one shared global — otherwise two
# people hitting a hosted instance at once would be playing the same
# wallet/location/inventory.
GAMES: dict[str, GameState] = {}


def _player_id() -> str:
    if "player_id" not in session:
        session.permanent = True
        session["player_id"] = secrets.token_hex(16)
    return session["player_id"]


def get_game() -> GameState:
    pid = _player_id()
    if pid not in GAMES:
        GAMES[pid] = GameState()
    return GAMES[pid]


@app.get("/")
def index():
    sell_pct = round(100 * (1 - data.SELL_SPREAD_PCT))
    return render_template("index.html", sell_pct=sell_pct)


@app.get("/about")
def about():
    return render_template("about.html")


@app.get("/api/state")
def api_state():
    return jsonify(get_game().public_state())


@app.post("/api/buy")
def api_buy():
    game = get_game()
    payload = request.get_json(force=True) or {}
    result = game.buy(payload.get("product"), int(payload.get("qty", 0)))
    return jsonify({**result, "state": game.public_state()})


@app.post("/api/sell")
def api_sell():
    game = get_game()
    payload = request.get_json(force=True) or {}
    result = game.attempt_sale(payload.get("product"), int(payload.get("qty", 0)))
    return jsonify({**result, "state": game.public_state()})


@app.post("/api/travel")
def api_travel():
    game = get_game()
    payload = request.get_json(force=True) or {}
    result = game.travel(payload.get("destination"))
    return jsonify({**result, "state": game.public_state()})


@app.post("/api/reset")
def api_reset():
    game = get_game()
    game.new_game()
    return jsonify({"ok": True, "state": game.public_state()})


@app.post("/api/save")
def api_save():
    game = get_game()
    payload = request.get_json(force=True) or {}
    name = payload.get("name") or "save"
    saved_name = game.save(name)
    return jsonify({"ok": True, "name": saved_name, "state": game.public_state()})


@app.post("/api/load")
def api_load():
    pid = _player_id()
    payload = request.get_json(force=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Pick a save to load."})
    try:
        GAMES[pid] = GameState.load(name)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": f"No save named '{name}'."})
    return jsonify({"ok": True, "state": GAMES[pid].public_state()})


def main() -> None:
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, port=5050)


if __name__ == "__main__":
    main()
