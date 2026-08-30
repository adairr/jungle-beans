"""Core game engine for Jungle Beans: state, market, travel, and events."""

from __future__ import annotations

import itertools
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

from . import data

SAVES_DIR = Path(__file__).resolve().parents[2] / "saves"


def _haversine_km(a: data.Airport, b: data.Airport) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def airfare(origin_code: str, dest_code: str) -> int:
    origin = data.AIRPORT_BY_CODE[origin_code]
    dest = data.AIRPORT_BY_CODE[dest_code]
    km = _haversine_km(origin, dest)
    fare = data.AIRFARE_BASE_FEE + km * data.AIRFARE_PER_KM
    return int(round(fare, -1))  # rounded to nearest $10


class GameState:
    def __init__(self) -> None:
        self.new_game()

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    def new_game(self) -> None:
        self.cash = data.STARTING_CASH
        self.debt = 0
        self.life = data.STARTING_LIFE
        self.day = 0
        self.location = data.HOME_AIRPORT
        self.inventory: dict[str, int] = {p.key: 0 for p in data.PRODUCTS}
        self.sales_count = 0
        self.sales_by_airport: dict[str, int] = {a.code: 0 for a in data.AIRPORTS}
        self.sales_since_day = 0
        self.notices: list[str] = []
        self.game_over = False
        self.win = False
        self.game_over_reason = ""

        # Assign 4 negative / 3 positive / 3 baseline modifiers across the 10 airports.
        # São Paulo is always the deepest discount — it's the source region, right at
        # the Amazon, so stocking up on Raw Bean/Bean Beverage at home is always the
        # cheapest option in the game (helps a new player get their first trade going).
        codes = [a.code for a in data.AIRPORTS if a.code != data.HOME_AIRPORT]
        random.shuffle(codes)
        self.airport_modifier: dict[str, float] = {
            data.HOME_AIRPORT: round(random.uniform(-0.45, -0.36), 3)
        }
        for code in codes[:3]:
            self.airport_modifier[code] = round(random.uniform(-0.35, -0.15), 3)
        for code in codes[3:6]:
            self.airport_modifier[code] = round(random.uniform(0.15, 0.35), 3)
        for code in codes[6:]:
            self.airport_modifier[code] = 0.0

        # Per-airport/product drift, updated on price refresh days.
        self.drift: dict[str, dict[str, float]] = {
            a.code: {p.key: 0.0 for p in data.PRODUCTS} for a in data.AIRPORTS
        }
        # Temporary per-cycle "market shock" applied to 3 random airports.
        self.shock: dict[str, float] = {}
        self._apply_shock()

        # Cheap regional short-hops, rolled fresh this game.
        self.regional_fare: dict[str, int] = self._roll_regional_fares()

        self._log(f"Touched down in {data.AIRPORT_BY_CODE[self.location].name} with "
                   f"${self.cash:,} and a bag full of hope. Day 0.")

    @staticmethod
    def _roll_regional_fares() -> dict[str, int]:
        """Random discounted fare per intra-cluster airport pair, keyed by
        the pair's codes sorted and joined ("ATL-DEN") so it round-trips
        through JSON save files without needing a custom encoder."""
        fares: dict[str, int] = {}
        for cluster in data.AIRPORT_CLUSTERS:
            for a, b in itertools.combinations(sorted(cluster), 2):
                fare = random.randint(data.REGIONAL_FARE_MIN, data.REGIONAL_FARE_MAX)
                fares[f"{a}-{b}"] = int(round(fare, -1))
        return fares

    def _apply_shock(self) -> None:
        self.shock = {}
        picks = random.sample([a.code for a in data.AIRPORTS], 3)
        for code in picks:
            self.shock[code] = round(random.uniform(-0.3, 0.3), 3)

    # ------------------------------------------------------------------ #
    # Derived values
    # ------------------------------------------------------------------ #
    @property
    def level(self) -> int:
        return min(1 + self.day // data.LEVEL_UP_INTERVAL_DAYS, 4)

    def unlocked_products(self) -> list[data.Product]:
        return [p for p in data.PRODUCTS if p.unlock_level <= self.level]

    def current_price(self, airport_code: str, product_key: str) -> int:
        product = data.PRODUCT_BY_KEY[product_key]
        modifier = self.airport_modifier.get(airport_code, 0.0)
        drift = self.drift.get(airport_code, {}).get(product_key, 0.0)
        shock = self.shock.get(airport_code, 0.0)
        price = product.base_price * (1 + modifier) * (1 + drift) * (1 + shock)
        return max(5, int(round(price)))

    def prices_at(self, airport_code: str) -> dict[str, int]:
        return {p.key: self.current_price(airport_code, p.key) for p in data.PRODUCTS}

    def fare_to(self, dest_code: str) -> int:
        """Airfare from the current location to dest_code — the discounted
        regional short-hop rate if this pair rolled one, else the normal
        distance-based fare."""
        key = "-".join(sorted((self.location, dest_code)))
        if key in self.regional_fare:
            return self.regional_fare[key]
        return airfare(self.location, dest_code)

    def heat_faces(self, airport_code: str) -> int:
        """How many faces of a d12 count as a "challenge" roll at this airport.

        Scales with how far above baseline the market's average price is
        running — the better the deal, the more enforcement attention it's
        drawing. Always at least HEAT_BASE_FACES, capped at DICE_SIDES.
        """
        ratios = [
            self.current_price(airport_code, p.key) / p.base_price for p in data.PRODUCTS
        ]
        avg_ratio = sum(ratios) / len(ratios)
        premium = max(0.0, avg_ratio - 1.0)
        faces = data.HEAT_BASE_FACES + round(premium * data.HEAT_SENSITIVITY)
        return max(1, min(data.DICE_SIDES, faces))

    def net_worth(self) -> int:
        inv_value = sum(
            self.inventory[k] * self.current_price(self.location, k) for k in self.inventory
        )
        return int(self.cash + inv_value - self.debt)

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    def _log(self, message: str) -> None:
        self.notices.insert(0, f"Day {self.day} — {message}")
        del self.notices[60:]

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def buy(self, product_key: str, qty: int) -> dict:
        if self.game_over:
            return {"ok": False, "error": "The game has ended. Reset to play again."}
        product = data.PRODUCT_BY_KEY.get(product_key)
        if product is None or qty <= 0:
            return {"ok": False, "error": "Pick a product and a quantity greater than zero."}
        if product.unlock_level > self.level:
            return {"ok": False, "error": f"{product.name} unlocks at level {product.unlock_level}."}
        price = self.current_price(self.location, product_key)
        cost = price * qty
        if cost > self.cash:
            return {"ok": False, "error": f"Not enough cash. {product.name} x{qty} costs ${cost:,}."}
        self.cash -= cost
        self.inventory[product_key] += qty
        self._log(f"Bought {qty}x {product.name} for ${cost:,} at {self._airport_name()}.")
        return {"ok": True}

    def attempt_sale(self, product_key: str, qty: int) -> dict:
        if self.game_over:
            return {"ok": False, "error": "The game has ended. Reset to play again."}
        product = data.PRODUCT_BY_KEY.get(product_key)
        if product is None or qty <= 0:
            return {"ok": False, "error": "Pick a product and a quantity greater than zero."}
        held = self.inventory.get(product_key, 0)
        if held < qty:
            return {"ok": False, "error": f"You only have {held}x {product.name}."}

        hot_faces = self.heat_faces(self.location)

        pre_roll = random.randint(1, data.DICE_SIDES)
        if pre_roll <= hot_faces:
            self._resolve_event(product_key, "pre", pre_roll, hot_faces)
        else:
            price = self.current_price(self.location, product_key)
            revenue = int(round(price * qty * (1 - data.SELL_SPREAD_PCT)))
            self.inventory[product_key] -= qty
            self.cash += revenue
            self.sales_count += 1
            self.sales_by_airport[self.location] = self.sales_by_airport.get(self.location, 0) + qty
            self._log(f"Sold {qty}x {product.name} for ${revenue:,} at {self._airport_name()}.")

            post_roll = random.randint(1, data.DICE_SIDES)
            if post_roll <= hot_faces:
                self._resolve_event(product_key, "post", post_roll, hot_faces)

        self.sales_since_day += 1
        if self.sales_since_day >= data.SALES_PER_DAY:
            self.sales_since_day = 0
            self._advance_day()

        self._check_end_conditions()
        return {"ok": True}

    def _resolve_event(self, product_key: str, timing: str, roll: int, hot_faces: int) -> None:
        product = data.PRODUCT_BY_KEY[product_key]
        die1, die2 = random.randint(1, 6), random.randint(1, 6)
        event = data.DICE_SUM_TO_EVENT[die1 + die2]
        outcomes = event["outcomes"]
        outcome = random.choices(outcomes, weights=[o["weight"] for o in outcomes])[0]
        intensity = data.LEVEL_INTENSITY_MULTIPLIER.get(self.level, 1.0)

        cash_loss = 0
        if "cash_loss_pct_range" in outcome:
            pct = min(1.0, random.uniform(*outcome["cash_loss_pct_range"]) * intensity)
            cash_loss = int(self.cash * pct)
            self.cash = max(0, self.cash - cash_loss)
        if "cash_flat_range" in outcome:
            flat = int(round(random.randint(*outcome["cash_flat_range"]) * intensity))
            flat = min(flat, self.cash)  # a flat fine can't take cash you don't have
            cash_loss += flat
            self.cash = max(0, self.cash - flat)

        lost_qty = 0
        if "inventory_loss_pct_range" in outcome:
            pct = min(1.0, random.uniform(*outcome["inventory_loss_pct_range"]) * intensity)
            lost_qty = int(self.inventory[product_key] * pct)
            self.inventory[product_key] = max(0, self.inventory[product_key] - lost_qty)

        debt_gain = 0
        if "debt_gain_range" in outcome:
            debt_gain = int(round(random.randint(*outcome["debt_gain_range"]) * intensity))
            self.debt += debt_gain

        life_loss = 0
        if "life_loss_range" in outcome:
            life_loss = int(round(random.randint(*outcome["life_loss_range"]) * intensity))
            self.life = max(0, self.life - life_loss)

        lede = (
            "Ambushed before the deal could close! "
            if timing == "pre"
            else "Caught on the way out! "
        )
        detail = [
            f"{lede}[triggered {roll}/{hot_faces} on the d{data.DICE_SIDES}, "
            f"rolled {die1}+{die2}={die1 + die2} → {event['name']}] {outcome['notice']}"
        ]
        if cash_loss:
            detail.append(f"Lost ${cash_loss:,}.")
        if lost_qty:
            detail.append(f"Lost {lost_qty}x {product.name}.")
        if debt_gain:
            detail.append(f"Slapped with ${debt_gain:,} in debt.")
        if life_loss:
            detail.append(f"({life_loss} half-heart damage)")
        self._log(" ".join(detail))

    def travel(self, dest_code: str) -> dict:
        if self.game_over:
            return {"ok": False, "error": "The game has ended. Reset to play again."}
        if dest_code not in data.AIRPORT_BY_CODE:
            return {"ok": False, "error": "Unknown airport."}
        if dest_code == self.location:
            return {"ok": False, "error": "You're already there."}
        cost = self.fare_to(dest_code)
        if cost > self.cash:
            return {"ok": False, "error": f"Airfare to {data.AIRPORT_BY_CODE[dest_code].name} is ${cost:,} — you can't afford it."}
        self.cash -= cost
        origin_name = self._airport_name()
        self.location = dest_code
        self.sales_since_day = 0
        self._advance_day()
        self._log(f"Flew from {origin_name} to {self._airport_name()} for ${cost:,} airfare.")
        self._check_end_conditions()
        return {"ok": True}

    def _advance_day(self) -> None:
        old_level = self.level
        self.day += 1
        if self.debt > 0:
            payment = min(self.cash, max(1, int(self.debt * 0.2)))
            self.cash -= payment
            self.debt -= payment
            if self.debt > 0:
                self.debt = int(self.debt * 1.05)
        if self.day % data.PRICE_REFRESH_DAYS == 0:
            self._refresh_prices()
        if self.level > old_level:
            unlocked = [p for p in data.PRODUCTS if p.unlock_level == self.level]
            names = ", ".join(p.name for p in unlocked) or "new tiers"
            self._log(f"Reputation grows — you've reached level {self.level}! {names} unlocked.")

    def _refresh_prices(self) -> None:
        for airport_drift in self.drift.values():
            for key in airport_drift:
                airport_drift[key] = max(
                    -0.4, min(0.4, airport_drift[key] + random.uniform(-0.1, 0.1))
                )
        self._apply_shock()
        self._log("Market prices shifted around the world.")

    def airports_covered(self) -> int:
        return sum(
            1
            for a in data.AIRPORTS
            if self.sales_by_airport.get(a.code, 0) >= data.WIN_MIN_SALES_PER_AIRPORT
        )

    def _check_end_conditions(self) -> None:
        if self.life <= 0 and not self.game_over:
            self.game_over = True
            self.game_over_reason = "Your life meter hit zero. You've been taken off the board."
            self._log("GAME OVER — " + self.game_over_reason)
        elif (
            self.net_worth() >= data.WIN_NET_WORTH
            and self.airports_covered() >= len(data.AIRPORTS)
            and not self.game_over
        ):
            self.game_over = True
            self.win = True
            self.game_over_reason = (
                f"You built a ${self.net_worth():,} empire with beans moving through all "
                f"{len(data.AIRPORTS)} airports and retired a legend."
            )
            self._log(
                "✈️🔥✈️ YOU WIN! 🔥✈️🔥 " + self.game_over_reason + " 🔥✈️🔥✈️🔥"
            )

    def _airport_name(self) -> str:
        return data.AIRPORT_BY_CODE[self.location].name

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "debt": self.debt,
            "life": self.life,
            "day": self.day,
            "location": self.location,
            "inventory": self.inventory,
            "sales_count": self.sales_count,
            "sales_by_airport": self.sales_by_airport,
            "sales_since_day": self.sales_since_day,
            "notices": self.notices,
            "game_over": self.game_over,
            "win": self.win,
            "game_over_reason": self.game_over_reason,
            "airport_modifier": self.airport_modifier,
            "drift": self.drift,
            "shock": self.shock,
            "regional_fare": self.regional_fare,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "GameState":
        state = cls.__new__(cls)
        state.cash = payload["cash"]
        state.debt = payload["debt"]
        state.life = payload["life"]
        state.day = payload["day"]
        state.location = payload["location"]
        state.inventory = payload["inventory"]
        state.sales_count = payload["sales_count"]
        state.sales_by_airport = payload.get(
            "sales_by_airport", {a.code: 0 for a in data.AIRPORTS}
        )
        state.sales_since_day = payload["sales_since_day"]
        state.notices = payload["notices"]
        state.game_over = payload["game_over"]
        state.win = payload["win"]
        state.game_over_reason = payload["game_over_reason"]
        state.airport_modifier = payload["airport_modifier"]
        state.drift = payload["drift"]
        state.shock = payload["shock"]
        state.regional_fare = payload.get("regional_fare") or cls._roll_regional_fares()
        return state

    def save(self, name: str) -> str:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_ ").strip() or "save"
        path = SAVES_DIR / f"{safe_name}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        self._log(f"Game saved as '{safe_name}'.")
        return safe_name

    @staticmethod
    def list_saves() -> list[str]:
        if not SAVES_DIR.exists():
            return []
        return sorted(p.stem for p in SAVES_DIR.glob("*.json"))

    @classmethod
    def load(cls, name: str) -> "GameState":
        path = SAVES_DIR / f"{name}.json"
        payload = json.loads(path.read_text())
        return cls.from_dict(payload)

    # ------------------------------------------------------------------ #
    # View model for the frontend
    # ------------------------------------------------------------------ #
    def public_state(self) -> dict:
        airports = []
        for a in data.AIRPORTS:
            airports.append(
                {
                    "code": a.code,
                    "name": a.name,
                    "lat": a.lat,
                    "lon": a.lon,
                    "is_current": a.code == self.location,
                    "airfare": None if a.code == self.location else self.fare_to(a.code),
                    "heat": self.heat_faces(a.code),
                    "heat_max": data.DICE_SIDES,
                    "sold_here": self.sales_by_airport.get(a.code, 0),
                    "win_covered": self.sales_by_airport.get(a.code, 0) >= data.WIN_MIN_SALES_PER_AIRPORT,
                }
            )
        products = []
        for p in data.PRODUCTS:
            unlocked = p.unlock_level <= self.level
            products.append(
                {
                    "key": p.key,
                    "name": p.name,
                    "unlock_level": p.unlock_level,
                    "unlocked": unlocked,
                    "price": self.current_price(self.location, p.key) if unlocked else None,
                    "owned": self.inventory.get(p.key, 0),
                }
            )
        airport_prices = {a.code: self.prices_at(a.code) for a in data.AIRPORTS}
        return {
            "cash": self.cash,
            "debt": self.debt,
            "life": self.life,
            "life_max": data.STARTING_LIFE,
            "day": self.day,
            "sales_since_day": self.sales_since_day,
            "sales_per_day": data.SALES_PER_DAY,
            "level": self.level,
            "location": self.location,
            "net_worth": self.net_worth(),
            "net_worth_goal": data.WIN_NET_WORTH,
            "airports_covered": self.airports_covered(),
            "airports_total": len(data.AIRPORTS),
            "airports": airports,
            "products": products,
            "airport_prices": airport_prices,
            "notices": self.notices[:20],
            "game_over": self.game_over,
            "win": self.win,
            "game_over_reason": self.game_over_reason,
            "saves": self.list_saves(),
        }
