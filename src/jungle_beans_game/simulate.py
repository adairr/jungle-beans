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
from .engine import GameState

MAX_DAYS = 200
MAX_STEPS = MAX_DAYS * 6  # safety net so a stuck bot can't spin forever
CASH_RESERVE = 200  # the bot always keeps a little cash on hand
EST_FARE_PER_UNCOVERED_STOP = 400  # rough reserve per airport still needed for the win condition


def _travel_reserve(game: GameState) -> int:
    """Cash held back for flights to airports still needed for the win
    condition. Without this the bot is "asset-rich, cash-poor": it happily
    invests down to CASH_RESERVE every cycle and ends up stranded with a
    six-figure net worth in unsellable inventory but $100 in its pocket,
    unable to afford the next $400 flight. A rough per-stop estimate (not a
    real routing solve) is enough to stop that failure mode.
    """
    uncovered = sum(
        1
        for a in data.AIRPORTS
        if game.sales_by_airport.get(a.code, 0) < data.WIN_MIN_SALES_PER_AIRPORT
    )
    return CASH_RESERVE + uncovered * EST_FARE_PER_UNCOVERED_STOP


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


UNCOVERED_BONUS = 3.0  # nudges the bot toward airports it still needs for the win condition


def best_opportunity(game: GameState) -> tuple[str, int, str] | None:
    """The single (product, quantity, destination) trade with the highest
    *risk-adjusted* profit from here — gross profit discounted by the odds of
    selling clean at the destination (heat governs both the pre- and post-sale
    ambush rolls, so a clean sale needs both to miss). Without this discount
    the bot (like a naive player) always chases the single biggest number,
    which is deliberately the same airport the heat mechanic makes most
    dangerous, and faceplants immediately. Checked against every airport
    (including staying put), same as a player who clicks through Airports
    first. Destinations still needed for the win condition (haven't sold
    there yet) get a bonus, so the bot doesn't just farm one lucrative route
    forever and never finish the "sell through every airport" requirement.
    """
    best: tuple[float, str, int, str] | None = None
    reserve = _travel_reserve(game)
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
            fare = 0 if a.code == game.location else game.fare_to(a.code)
            budget = max(0, game.cash - reserve - fare)
            qty = int(budget // buy_price)
            if qty <= 0:
                continue
            gross_profit = margin_per_unit * qty - fare
            if gross_profit <= 0:
                continue
            heat = game.heat_faces(a.code)
            clean_odds = ((data.DICE_SIDES - heat) / data.DICE_SIDES) ** 2
            expected_profit = gross_profit * clean_odds
            if game.sales_by_airport.get(a.code, 0) < data.WIN_MIN_SALES_PER_AIRPORT:
                expected_profit *= UNCOVERED_BONUS
            if expected_profit <= 0:
                continue
            if best is None or expected_profit > best[0]:
                best = (expected_profit, p.key, qty, a.code)
    if best is None:
        return None
    _, product_key, qty, dest = best
    return product_key, qty, dest


def mop_up_target(game: GameState) -> str | None:
    """Cheapest-to-reach airport still needed for the win condition, once
    profit-seeking has dried up but coverage isn't complete — a real player
    chasing the win would do this too rather than farming one route forever.
    """
    uncovered = [
        a.code
        for a in data.AIRPORTS
        if game.sales_by_airport.get(a.code, 0) < data.WIN_MIN_SALES_PER_AIRPORT
    ]
    if not uncovered:
        return None
    uncovered.sort(key=lambda code: 0 if code == game.location else game.fare_to(code))
    return uncovered[0]


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
            mop_up = mop_up_target(game)
            if mop_up is not None:
                if mop_up != game.location:
                    if not game.travel(mop_up)["ok"]:
                        stuck = True
                        break
                    continue
                # Already at an uncovered airport — punch the ticket with a
                # minimal sale of whatever's cheapest, profit be damned.
                cheapest = min(
                    game.unlocked_products(),
                    key=lambda p: game.current_price(game.location, p.key),
                )
                if game.inventory.get(cheapest.key, 0) < 1:
                    if not game.buy(cheapest.key, 1)["ok"]:
                        stuck = True
                        break
                game.attempt_sale(cheapest.key, 1)
                continue
            # Nothing profitable and nothing left to cover — reposition and
            # hope for better prices, rather than taking a guaranteed loss.
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
    parser.add_argument("--win-net-worth", type=int, default=None)
    parser.add_argument("--heat-base-faces", type=int, default=None, help="baseline risk out of 12 at a calm market")
    parser.add_argument("--heat-sensitivity", type=float, default=None, help="extra faces per 100% price premium")
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
    if args.win_net_worth is not None:
        overrides["WIN_NET_WORTH"] = args.win_net_worth
    if args.heat_base_faces is not None:
        overrides["HEAT_BASE_FACES"] = args.heat_base_faces
    if args.heat_sensitivity is not None:
        overrides["HEAT_SENSITIVITY"] = args.heat_sensitivity
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
