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

# Field logistical challenges that can strike on an "Attempt Sale", per the
# stats drafted in JB_template.md. Each event has one or more possible
# "outcomes" — a notice, a relative weight (how often that branch is picked
# among the event's outcomes), and ranges to sample the actual penalty from
# (a fixed number is just a range whose min equals its max). *_pct ranges are
# fractions of the current wallet/held quantity; *_flat ranges are dollar
# amounts untouched by wallet size; life is in half-heart units (1 heart = 2).
#
# Which challenge fires is decided by summing two d6, not a uniform 1-in-6
# pick — 2d6 is a bell curve (7 is 6x likelier than 2 or 12), so pairing each
# event with a symmetric pair of sums gives 6 naturally different rarities
# instead of an even split. Ordered here mildest/most-common to
# most-severe/rarest: Shots Fired's 3-heart hit only shows up on the {2,12}
# tail (5.6%), so the worst outcome stays a rare gut-punch rather than an
# every-other-roll coinflip.
EVENTS: list[dict] = [
    {
        "key": "extreme_weather",
        "name": "Extreme weather variable",
        "dice_sums": (6, 8),  # 10/36 = 27.8% of challenges — mildest, most common
        "outcomes": [
            {
                "notice": "A tropical storm grounded flights and cost you cleanup fees.",
                "weight": 1,
                "cash_flat_range": (150, 150),
            },
        ],
    },
    {
        "key": "payload_detected",
        "name": "Payload detected",
        "dice_sums": (5, 9),  # 8/36 = 22.2%
        "outcomes": [
            {
                "notice": "Customs flagged your shipment on the scanner — half your bag is gone.",
                "weight": 1,
                "inventory_loss_pct_range": (0.50, 0.50),
            },
            {
                "notice": "Border agents wave you through for a flat processing 'fine'.",
                "weight": 1,
                "cash_flat_range": (500, 500),
            },
        ],
    },
    {
        "key": "thief",
        "name": "Thief",
        "dice_sums": (7,),  # 6/36 = 16.7%
        "outcomes": [
            {
                "notice": "A pickpocket lifted cash right out of your jacket.",
                "weight": 1,
                "cash_loss_pct_range": (0.25, 0.40),
            },
            {
                "notice": "A sneak thief made off with a chunk of your bag.",
                "weight": 1,
                "inventory_loss_pct_range": (0.40, 0.75),
            },
        ],
    },
    {
        "key": "local_mobsters",
        "name": "Local mobsters",
        "dice_sums": (4, 10),  # 6/36 = 16.7% — first tier with a life-loss branch
        "outcomes": [
            {
                "notice": "Mobsters shake you down for cold hard cash.",
                "weight": 1,
                "cash_flat_range": (500, 500),
            },
            {
                "notice": "Mobsters send a message you'll feel for days.",
                "weight": 1,
                "life_loss_range": (3, 3),
            },
        ],
    },
    {
        "key": "police_seizure",
        "name": "Police seizure/confiscation",
        "dice_sums": (3, 11),  # 4/36 = 11.1%
        "outcomes": [
            {
                "notice": "Local police seized your entire stock.",
                "weight": 1,
                "inventory_loss_pct_range": (1.00, 1.00),
            },
        ],
    },
    {
        "key": "shots_fired",
        "name": "Shots fired",
        "dice_sums": (2, 12),  # 2/36 = 5.6% — rarest, most severe
        "outcomes": [
            {
                "notice": "Shots fired on the tarmac — you barely made it out alive.",
                "weight": 1,
                "life_loss_range": (6, 6),
            },
        ],
    },
]

DICE_SUM_TO_EVENT: dict[int, dict] = {
    s: event for event in EVENTS for s in event["dice_sums"]
}

# Risk is now tied to reward. Each airport's "heat" is how many faces (out of
# a d12) count as a hit, derived from how favorable its current prices are
# (average current price / base price across all products): a calm/cheap
# market stays near the baseline roll, a market with great sell prices runs
# hot. Every Attempt Sale rolls twice against that threshold — once before
# the deal (an ambush that cancels the sale) and once after (you got paid,
# then got hit on the way out) — so a hot market can realistically clear 50%+
# combined odds of a challenge on a single sale.
DICE_SIDES = 12
HEAT_BASE_FACES = 1  # baseline risk even at a calm/cheap market (1/12 ≈ 8%)
# Faces added per 100% the market runs above baseline price. Simulator-tested:
# 17 (50%+ heat at just a 30%-above-baseline deal) makes nearly every
# profitable trade automatically dangerous, since there's rarely a safer
# lower-margin route left to pick instead — win rate near 0% even at 4x
# starting cash. 6 keeps the same "best deals are the most dangerous"
# coupling but reserves 50%+ heat for genuinely exceptional price spikes,
# leaving modest/safer trades available as a real alternative.
HEAT_SENSITIVITY = 6

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

# Player level (and product unlocks) advance with elapsed in-game days, not
# sales count — a new tier every LEVEL_UP_INTERVAL_DAYS days, capped at
# level 4. E.g. at 3: day 0-2 = level 1, day 3-5 = level 2 (Bean Gummies), etc.
LEVEL_UP_INTERVAL_DAYS = 3
