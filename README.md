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
  airport, then **Attempt Sale** to cash in at a better price. Selling nets
  ~90% of the listed price (a dealer's cut) — buying and instantly reselling
  the same product at the same airport is always a small loss, so real
  profit has to come from genuine arbitrage or a price swing.
- Every airport has a **heat** level (0-12, shown as a 🔥 badge in the
  Airports list and on map hover) driven by how far above baseline its
  current prices are running — the better the deal, the more attention it's
  drawing. Every Attempt Sale rolls a d12 against that airport's heat twice:
  once before the deal closes (an ambush that cancels the sale) and once
  after (you got paid, then got hit on the way out). A genuinely hot market
  can clear 50%+ combined odds of a field challenge on a single sale; a calm
  one sits near an 8% baseline either way.
- Once a challenge is confirmed to fire, *which* of the 6 (payload
  detected, police seizure, local mobsters, thieves, extreme weather, shots
  fired) it is comes from a 2d6 roll, not an even 1-in-6 — summed dice form
  a bell curve, so grouping symmetric sums into 6 pairs gives each
  challenge a different natural rarity (27.8% down to 5.6%). Shots Fired's
  3-heart hit sits on the rarest tail, so the worst outcome stays a rare
  gut-punch instead of as common as Extreme Weather's $150 ding. Some
  challenges (Thief) also roll between distinct outcomes — e.g. either
  25-40% of your wallet or up to 75% of the product you're carrying, never
  both.
- Challenge penalties scale with player level (`LEVEL_INTENSITY_MULTIPLIER`
  in `data.py`: 0.5x at level 1, 0.75x at level 2, 1.0x at level 3, 1.25x at
  level 4) — a level 1 smuggler moving Raw Bean gets a nerfed version of
  every penalty, and it escalates as you level up into higher-value
  products. Trigger odds (heat) are unaffected by level; only how much a
  challenge costs you once it fires.
- Every 3 sale attempts, or any trip between airports, advances the in-game
  day. Market prices drift every 5 days, and 3 random airports get a price
  "shock" each cycle.
- Higher-tier products (Bean Gummies, Bean IV, Bean Oil) unlock with elapsed
  in-game days, not sales count — a new level every 3 days, up to level 4
  (day 3 = Bean Gummies, day 6 = Bean IV, day 9 = Bean Oil).
- Debt is paid down automatically (20%/day) from your cash when you have
  some; unpaid debt accrues 5% interest per day.
- Reach $50,000 net worth to win; hit 0 life and it's game over.
- **Save** snapshots the current game to a named JSON file under `saves/`
  (gitignored); **Load** restores one.

## Design decisions not fully spelled out in the original notes

The source design notes (`JB_template.md`) left a few mechanics
underspecified. Calls made for this first playable build, easy to revisit:

- Product tier unlocks are keyed off elapsed in-game days (`LEVEL_UP_INTERVAL_DAYS`
  in `data.py`, currently 3 days/level).
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
