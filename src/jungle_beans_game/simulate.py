"""Monte Carlo balance simulator for Jungle Beans.

Runs many simulated games under a simple greedy bot — "buy the biggest
discount at the airport I'm standing in, fly to wherever that product is
selling highest, dump it all, repeat" — so economy tunings (starting cash,
price levels, bust chance, ...) can be compared numerically instead of by
guesswork. The bot only uses information a real player could get by
clicking every airport (which the game already allows), so it's not
cheating — just tireless.

Usage:
    uv run python -m jungle_beans_game.simulate
    uv run python -m jungle_beans_game.simulate --episodes 1000 --price-multiplier 2
    uv run python -m jungle_beans_game.simulate --compare 1,1.5,2,3
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import random
import statistics
from typing import Iterator

from . import data
from .engine import GameState, airfare

MAX_DAYS = 200
MAX_STEPS = MAX_DAYS * 6  # safety net so a stuck bot can't spin forever
CASH_RESERVE = 200  # the bot always keeps a little cash on hand


@contextlib.contextmanager
def economy_overrides(*, price_multiplier: float = 1.0, **attr_overrides) -> Iterator[None]:
    """Temporarily scale product base prices and/or patch data.py constants.

    engine.py always reads constants as `data.SOMETHING` (never imported by
    value), so mutating the module's attributes here is picked up by every
    GameState created inside the `with` block, and cleanly restored after.
    """
    original_products = data.PRODUCTS
    original_by_key = data.PRODUCT_BY_KEY
    saved_attrs = {name: getattr(data, name) for name in attr_overrides}
    try:
        if price_multiplier != 1.0:
            scaled = [
                dataclasses.replace(p, base_price=max(1, int(round(p.base_price * price_multiplier))))
                for p in original_products
            ]
            data.PRODUCTS = scaled
            data.PRODUCT_BY_KEY = {p.key: p for p in scaled}
        for name, value in attr_overrides.items():
            setattr(data, name, value)
        yield
    finally:
        data.PRODUCTS = original_products
        data.PRODUCT_BY_KEY = original_by_key
        for name, value in saved_attrs.items():
            setattr(data, name, value)


def best_opportunity(game: GameState) -> tuple[str, int, str] | None:
    """The single (product, quantity, destination) trade with the highest projected
    profit from here, after airfare and the sell spread — or None if nothing on the
    board actually turns a profit. Checked against every airport (including staying
    put), same as a player who clicks through the Airports list before committing.
    """
    best: tuple[float, str, int, str] | None = None
    for p in game.unlocked_products():
        buy_price = game.current_price(game.location, p.key)
        if buy_price <= 0:
            continue
        for a in data.AIRPORTS:
            sell_price = game.current_price(a.code, p.key)
            net_sell = sell_price * (1 - data.SELL_SPREAD_PCT)
            margin_per_unit = net_sell - buy_price
            if margin_per_unit <= 0:
                continue
            fare = 0 if a.code == game.location else airfare(game.location, a.code)
            budget = max(0, game.cash - CASH_RESERVE - fare)
            qty = int(budget // buy_price)
            if qty <= 0:
                continue
            profit = margin_per_unit * qty - fare
            if profit <= 0:
                continue
            if best is None or profit > best[0]:
                best = (profit, p.key, qty, a.code)
    if best is None:
        return None
    _, product_key, qty, dest = best
    return product_key, qty, dest


def run_episode(seed: int | None = None) -> dict:
    if seed is not None:
        random.seed(seed)
    game = GameState()
    steps = 0
    stuck = False

    while not game.game_over and game.day < MAX_DAYS and steps < MAX_STEPS:
        steps += 1
        opp = best_opportunity(game)
        if opp is None:
            # Nothing profitable from here — reposition and hope for better prices,
            # rather than taking a sale that's guaranteed to lose money.
            others = [a.code for a in data.AIRPORTS if a.code != game.location]
            if not game.travel(random.choice(others))["ok"]:
                stuck = True
                break
            continue

        product_key, qty, dest = opp
        if not game.buy(product_key, qty)["ok"]:
            stuck = True
            break
        if dest != game.location and not game.travel(dest)["ok"]:
            # Fare became unaffordable between planning and buying — cut losses locally.
            game.attempt_sale(product_key, game.inventory[product_key])
            continue
        game.attempt_sale(product_key, game.inventory[product_key])

    return {
        "win": game.win,
        "bankrupt": game.game_over and not game.win,
        "stuck": stuck,
        "timed_out": not game.game_over and not stuck,
        "days": game.day,
        "net_worth": game.net_worth(),
        "sales_count": game.sales_count,
    }


def run_batch(episodes: int, *, price_multiplier: float = 1.0, **attr_overrides) -> dict:
    with economy_overrides(price_multiplier=price_multiplier, **attr_overrides):
        results = [run_episode(seed=i) for i in range(episodes)]

    wins = [r for r in results if r["win"]]
    return {
        "episodes": episodes,
        "win_rate": len(wins) / episodes,
        "bankrupt_rate": sum(r["bankrupt"] for r in results) / episodes,
        "stuck_rate": sum(r["stuck"] for r in results) / episodes,
        "timeout_rate": sum(r["timed_out"] for r in results) / episodes,
        "avg_days_to_win": statistics.mean(r["days"] for r in wins) if wins else None,
        "median_days_to_win": statistics.median(r["days"] for r in wins) if wins else None,
        "avg_net_worth": statistics.mean(r["net_worth"] for r in results),
        "avg_sales_count": statistics.mean(r["sales_count"] for r in results),
    }


def _print_summary(label: str, summary: dict) -> None:
    win_days = f"{summary['avg_days_to_win']:.0f}" if summary["avg_days_to_win"] else "—"
    print(
        f"{label:<18} win {summary['win_rate']:>5.1%}  "
        f"bankrupt {summary['bankrupt_rate']:>5.1%}  "
        f"stuck {summary['stuck_rate']:>5.1%}  "
        f"timeout {summary['timeout_rate']:>5.1%}  "
        f"days/win {win_days:>4}  "
        f"avg net worth ${summary['avg_net_worth']:>8,.0f}  "
        f"avg sales {summary['avg_sales_count']:>5.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Jungle Beans Monte Carlo balance simulator")
    parser.add_argument("--episodes", type=int, default=500)
    parser.add_argument("--price-multiplier", type=float, default=1.0)
    parser.add_argument("--starting-cash", type=int, default=None)
    parser.add_argument("--event-chance", type=float, default=None)
    parser.add_argument("--sell-spread", type=float, default=None, help="e.g. 0.10 for a 10% spread")
    parser.add_argument("--airfare-per-km", type=float, default=None)
    parser.add_argument("--airfare-base-fee", type=float, default=None)
    parser.add_argument(
        "--compare",
        type=str,
        default=None,
        help="Comma-separated price multipliers to run side by side, e.g. 1,1.5,2,3",
    )
    args = parser.parse_args()

    overrides = {}
    if args.starting_cash is not None:
        overrides["STARTING_CASH"] = args.starting_cash
    if args.event_chance is not None:
        overrides["EVENT_CHANCE_PER_SALE"] = args.event_chance
    if args.sell_spread is not None:
        overrides["SELL_SPREAD_PCT"] = args.sell_spread
    if args.airfare_per_km is not None:
        overrides["AIRFARE_PER_KM"] = args.airfare_per_km
    if args.airfare_base_fee is not None:
        overrides["AIRFARE_BASE_FEE"] = args.airfare_base_fee

    if args.compare:
        multipliers = [float(x) for x in args.compare.split(",")]
        print(f"{args.episodes} episodes per multiplier, greedy-bot strategy\n")
        for m in multipliers:
            summary = run_batch(args.episodes, price_multiplier=m, **overrides)
            _print_summary(f"{m}x prices", summary)
    else:
        summary = run_batch(args.episodes, price_multiplier=args.price_multiplier, **overrides)
        _print_summary(f"{args.price_multiplier}x prices", summary)


if __name__ == "__main__":
    main()
