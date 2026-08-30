"""Flask app serving the Jungle Beans dashboard and game API."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from .engine import GameState

app = Flask(__name__)
GAME = GameState()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    return jsonify(GAME.public_state())


@app.post("/api/buy")
def api_buy():
    payload = request.get_json(force=True) or {}
    result = GAME.buy(payload.get("product"), int(payload.get("qty", 0)))
    return jsonify({**result, "state": GAME.public_state()})


@app.post("/api/sell")
def api_sell():
    payload = request.get_json(force=True) or {}
    result = GAME.attempt_sale(payload.get("product"), int(payload.get("qty", 0)))
    return jsonify({**result, "state": GAME.public_state()})


@app.post("/api/travel")
def api_travel():
    payload = request.get_json(force=True) or {}
    result = GAME.travel(payload.get("destination"))
    return jsonify({**result, "state": GAME.public_state()})


@app.post("/api/reset")
def api_reset():
    GAME.new_game()
    return jsonify({"ok": True, "state": GAME.public_state()})


@app.post("/api/save")
def api_save():
    payload = request.get_json(force=True) or {}
    name = payload.get("name") or "save"
    saved_name = GAME.save(name)
    return jsonify({"ok": True, "name": saved_name, "state": GAME.public_state()})


@app.post("/api/load")
def api_load():
    global GAME
    payload = request.get_json(force=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Pick a save to load."})
    try:
        GAME = GameState.load(name)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": f"No save named '{name}'."})
    return jsonify({"ok": True, "state": GAME.public_state()})


def main() -> None:
    app.run(debug=True, port=5050)


if __name__ == "__main__":
    main()
