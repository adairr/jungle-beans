# Jungle Beans

A browser-playable trading/survival game inspired by 90's off-brand windows games, built with
Flask (Python) on the backend and a retro Minesweeper-style dashboard on the
front end. Buy and sell *Jungle Beans* — a miracle medicinal plant that Mega
Pharma wants banned — across 10 global airports, dodge random field
challenges, and try to build a fortune before your life meter (or your luck)
runs out.

## Running it

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv run python -m jungle_beans_game.app
```

Then open http://127.0.0.1:5050 in Chrome, Safari, or Edge.

## Gameplay notes

- Start in São Paulo (GRU) with $5,000, 5 full life hearts, and an empty bag.
- **Buy** beans cheap from the Market Prices panel, **Travel** to another
  airport, then **Attempt Sale** to cash in at a better price.
- Every sale attempt has a ~12% chance of triggering a random field
  challenge (police seizure, thieves, extreme weather, etc.) that can cost
  you cash, product, life, or saddle you with debt.
- Every 3 sale attempts, or any trip between airports, advances the in-game
  day. Market prices drift every 5 days, and 3 random airports get a price
  "shock" each cycle.
- Higher-tier products (Bean Gummies, Bean IV, Bean Oil) unlock as your
  sales count grows (every 10 sales = +1 level, up to level 4).
- Debt is paid down automatically (20%/day) from your cash when you have
  some; unpaid debt accrues 5% interest per day.
- Reach $50,000 net worth to win; hit 0 life and it's game over.
- **Save** snapshots the current game to a named JSON file under `saves/`
  (gitignored); **Load** restores one.

## Design decisions not fully spelled out in the original notes

The source design notes (`JB_template.md`) left a few mechanics
underspecified. Calls made for this first playable build, easy to revisit:

- Product tier unlocks are keyed off total sales count (10 sales/level).
- Debt has no dedicated UI action — it auto-amortizes each day instead.
- A "Buy" control was added inline in the Market Prices panel (buying isn't
  risky the way selling is, so it doesn't share the Attempt Sale flow).
- A win condition ($50k net worth) was added to give "survive" an endpoint.

## Project layout

```
src/jungle_beans_game/
  data.py       # airports, products, event table, tunable constants
  engine.py     # GameState: market math, buy/sell/travel, save/load
  app.py        # Flask routes / API
  templates/    # dashboard HTML
  static/       # dashboard CSS + JS
saves/          # save-game JSON files (gitignored)
```
