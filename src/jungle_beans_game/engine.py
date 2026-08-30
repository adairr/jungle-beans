"""Core game engine for Jungle Beans: state, market, travel, and events."""

from __future__ import annotations

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
    return int(round(75 + km * 0.06, -1))  # rounded to nearest $10


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
        self.sales_since_day = 0
        self.notices: list[str] = []
        self.game_over = False
        self.win = False
        self.game_over_reason = ""

        # Assign 4 negative / 3 positive / 3 baseline modifiers across the 10 airports.
        codes = [a.code for a in data.AIRPORTS]
        random.shuffle(codes)
        self.airport_modifier: dict[str, float] = {}
        for code in codes[:4]:
            self.airport_modifier[code] = round(random.uniform(-0.35, -0.15), 3)
        for code in codes[4:7]:
            self.airport_modifier[code] = round(random.uniform(0.15, 0.35), 3)
        for code in codes[7:]:
            self.airport_modifier[code] = 0.0

        # Per-airport/product drift, updated on price refresh days.
        self.drift: dict[str, dict[str, float]] = {
            a.code: {p.key: 0.0 for p in data.PRODUCTS} for a in data.AIRPORTS
        }
        # Temporary per-cycle "market shock" applied to 3 random airports.
        self.shock: dict[str, float] = {}
        self._apply_shock()

        self._log(f"Touched down in {data.AIRPORT_BY_CODE[self.location].name} with "
                   f"${self.cash:,} and a bag full of hope. Day 0.")

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
        return min(1 + self.sales_count // 10, 4)

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

        triggered = random.random() < data.EVENT_CHANCE_PER_SALE
        if triggered:
            event = random.choice(data.EVENTS)
            self._resolve_event(event, product_key)
        else:
            price = self.current_price(self.location, product_key)
            revenue = price * qty
            self.inventory[product_key] -= qty
            self.cash += revenue
            old_level = self.level
            self.sales_count += 1
            self._log(f"Sold {qty}x {product.name} for ${revenue:,} at {self._airport_name()}.")
            if self.level > old_level:
                self._log(f"Reputation grows — you've reached level {self.level}!")

        self.sales_since_day += 1
        if self.sales_since_day >= data.SALES_PER_DAY:
            self.sales_since_day = 0
            self._advance_day()

        self._check_end_conditions()
        return {"ok": True}

    def _resolve_event(self, event: dict, product_key: str) -> None:
        product = data.PRODUCT_BY_KEY[product_key]
        cash_loss = int(self.cash * event["cash_loss_pct"])
        self.cash = max(0, self.cash - cash_loss)
        self.life = max(0, self.life - event["life_loss"])
        self.debt += event["debt_gain"]
        lost_qty = int(self.inventory[product_key] * event["inventory_loss_pct"])
        self.inventory[product_key] = max(0, self.inventory[product_key] - lost_qty)

        detail = [event["notice"]]
        if cash_loss:
            detail.append(f"Lost ${cash_loss:,}.")
        if lost_qty:
            detail.append(f"Lost {lost_qty}x {product.name}.")
        if event["debt_gain"]:
            detail.append(f"Slapped with ${event['debt_gain']:,} in debt.")
        detail.append(f"({event['life_loss']} half-heart damage)")
        self._log(" ".join(detail))

    def travel(self, dest_code: str) -> dict:
        if self.game_over:
            return {"ok": False, "error": "The game has ended. Reset to play again."}
        if dest_code not in data.AIRPORT_BY_CODE:
            return {"ok": False, "error": "Unknown airport."}
        if dest_code == self.location:
            return {"ok": False, "error": "You're already there."}
        cost = airfare(self.location, dest_code)
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
        self.day += 1
        if self.debt > 0:
            payment = min(self.cash, max(1, int(self.debt * 0.2)))
            self.cash -= payment
            self.debt -= payment
            if self.debt > 0:
                self.debt = int(self.debt * 1.05)
        if self.day % data.PRICE_REFRESH_DAYS == 0:
            self._refresh_prices()

    def _refresh_prices(self) -> None:
        for airport_drift in self.drift.values():
            for key in airport_drift:
                airport_drift[key] = max(
                    -0.4, min(0.4, airport_drift[key] + random.uniform(-0.1, 0.1))
                )
        self._apply_shock()
        self._log("Market prices shifted around the world.")

    def _check_end_conditions(self) -> None:
        if self.life <= 0 and not self.game_over:
            self.game_over = True
            self.game_over_reason = "Your life meter hit zero. You've been taken off the board."
            self._log("GAME OVER — " + self.game_over_reason)
        elif self.net_worth() >= data.WIN_NET_WORTH and not self.game_over:
            self.game_over = True
            self.win = True
            self.game_over_reason = f"You built a ${self.net_worth():,} empire and retired a legend."
            self._log("YOU WIN — " + self.game_over_reason)

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
            "sales_since_day": self.sales_since_day,
            "notices": self.notices,
            "game_over": self.game_over,
            "win": self.win,
            "game_over_reason": self.game_over_reason,
            "airport_modifier": self.airport_modifier,
            "drift": self.drift,
            "shock": self.shock,
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
        state.sales_since_day = payload["sales_since_day"]
        state.notices = payload["notices"]
        state.game_over = payload["game_over"]
        state.win = payload["win"]
        state.game_over_reason = payload["game_over_reason"]
        state.airport_modifier = payload["airport_modifier"]
        state.drift = payload["drift"]
        state.shock = payload["shock"]
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
                    "airfare": None if a.code == self.location else airfare(self.location, a.code),
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
            "airports": airports,
            "products": products,
            "notices": self.notices[:20],
            "game_over": self.game_over,
            "win": self.win,
            "game_over_reason": self.game_over_reason,
            "saves": self.list_saves(),
        }
