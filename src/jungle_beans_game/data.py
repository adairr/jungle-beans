"""Static game data: airports, products, and field logistical challenges."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Airport:
    code: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    base_price: int
    unlock_level: int


# Home base is São Paulo (GRU). The other nine come straight from the design notes.
AIRPORTS: list[Airport] = [
    Airport("GRU", "São Paulo (GRU)", -23.55, -46.63),
    Airport("ATL", "Atlanta Hartsfield-Jackson (ATL)", 33.64, -84.43),
    Airport("DXB", "Dubai (DXB)", 25.25, 55.36),
    Airport("HND", "Tokyo Haneda (HND)", 35.55, 139.78),
    Airport("DFW", "Dallas/Fort Worth (DFW)", 32.90, -97.04),
    Airport("LHR", "London Heathrow (LHR)", 51.47, -0.45),
    Airport("PVG", "Shanghai Pudong (PVG)", 31.14, 121.80),
    Airport("DEN", "Denver (DEN)", 39.86, -104.67),
    Airport("ORD", "Chicago O'Hare (ORD)", 41.98, -87.90),
    Airport("IST", "Istanbul (IST)", 41.26, 28.74),
]

AIRPORT_BY_CODE: dict[str, Airport] = {a.code: a for a in AIRPORTS}

HOME_AIRPORT = "GRU"

PRODUCTS: list[Product] = [
    Product("raw_bean", "Raw Bean", 50, 1),
    Product("bean_beverage", "Bean Beverage", 75, 1),
    Product("bean_gummies", "Bean Gummies", 125, 2),
    Product("bean_iv", "Bean IV", 200, 3),
    Product("bean_oil", "Bean Oil", 350, 4),
]

PRODUCT_BY_KEY: dict[str, Product] = {p.key: p for p in PRODUCTS}

# Field logistical challenges that can strike on an "Attempt Sale". Each entry
# describes what it costs the player when it fires.
EVENTS: list[dict] = [
    {
        "key": "payload_detected",
        "name": "Payload detected",
        "notice": "Customs flagged your shipment! The beans in your bag are gone.",
        "cash_loss_pct": 0.0,
        "life_loss": 1,
        "inventory_loss_pct": 1.0,
        "debt_gain": 0,
    },
    {
        "key": "police_seizure",
        "name": "Police seizure/confiscation",
        "notice": "Local police seized your stock and hit you with a fine.",
        "cash_loss_pct": 0.25,
        "life_loss": 1,
        "inventory_loss_pct": 1.0,
        "debt_gain": 500,
    },
    {
        "key": "local_mobsters",
        "name": "Local mobsters",
        "notice": "Mobsters muscled in and took a cut of your cash.",
        "cash_loss_pct": 0.35,
        "life_loss": 2,
        "inventory_loss_pct": 0.0,
        "debt_gain": 0,
    },
    {
        "key": "thief",
        "name": "Thief",
        "notice": "A pickpocket lifted product from your bag in the terminal.",
        "cash_loss_pct": 0.0,
        "life_loss": 1,
        "inventory_loss_pct": 0.5,
        "debt_gain": 0,
    },
    {
        "key": "extreme_weather",
        "name": "Extreme weather variable",
        "notice": "A tropical storm grounded flights and spoiled part of your stock.",
        "cash_loss_pct": 0.0,
        "life_loss": 1,
        "inventory_loss_pct": 0.3,
        "debt_gain": 0,
    },
    {
        "key": "shots_fired",
        "name": "Shots fired",
        "notice": "Shots fired on the tarmac — you barely made it out alive.",
        "cash_loss_pct": 0.1,
        "life_loss": 3,
        "inventory_loss_pct": 0.25,
        "debt_gain": 0,
    },
]

EVENT_CHANCE_PER_SALE = 0.12

# Sell orders execute at a discount to the listed market price (a bid/ask
# spread). Without this, buying and immediately reselling the same product
# at the same airport is a risk-free wash — a player (or a bot) can rack up
# pure-downside bust risk for zero expected reward. The spread makes local
# flipping a guaranteed small loss, so real profit has to come from actually
# traveling to a better market or waiting out a price swing.
SELL_SPREAD_PCT = 0.10

AIRFARE_BASE_FEE = 75
AIRFARE_PER_KM = 0.06

STARTING_CASH = 5000
STARTING_LIFE = 10  # half-heart units; 10 == 5 full hearts
SALES_PER_DAY = 3
PRICE_REFRESH_DAYS = 5
WIN_NET_WORTH = 50000
