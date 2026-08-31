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

# Regional clusters get a cheap, randomly-rolled short-hop fare instead of
# the usual distance-based airfare — real regional carriers undercut a
# long-haul pricing formula for nearby city-pairs. Rolled fresh each new
# game (see GameState.new_game), capped under $200. GRU/South America isn't
# part of a cluster — every route to or from it stays on the normal formula.
AIRPORT_CLUSTERS: list[frozenset[str]] = [
    frozenset({"DEN", "ORD", "DFW", "ATL"}),  # North America
    frozenset({"LHR", "IST", "DXB"}),  # Europe / Middle East
    frozenset({"HND", "PVG"}),  # Asia
]
REGIONAL_FARE_MIN = 50
REGIONAL_FARE_MAX = 190

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
                "life_loss_range": (3, 3),  # 1.5 hearts
                "intensity_exempt": True,  # always exactly 1.5 hearts, not 1-2 by level
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
                # "Entire stock" is an absolute claim, not a scalable one —
                # there's no narratively sensible "partial confiscation of
                # everything." Exempt from LEVEL_INTENSITY_MULTIPLIER so it
                # stays a true 100% at every level instead of the notice
                # text overpromising what actually happened.
                "intensity_exempt": True,
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

# Positive counterweight to the challenge table, introduced once the player
# reaches level 2. Checked once per arrival (Travel), not per sale — a
# player who's already earned unfavorable-market resilience deserves a
# chance at favorable-market upside too. Five of the six bonuses only fire
# arriving at a "high cost" market (average price ratio above 1.0 — a good
# place to sell); Pineapple Express is the mirror case for a "low cost"
# market (a good place to buy) and can't share the same die-roll table with
# a mutually-exclusive trigger condition, so it's checked as its own
# independent roll (PINEAPPLE_EXPRESS_FACES) rather than a seventh dice_sums
# entry here. Ordered biggest-reward-to-rarest, same principle as the
# challenge table: {6,8} (27.8%) is deliberately left unmapped so "nothing
# happens" stays the single most likely outcome even at a high-cost
# arrival — bonuses should feel like a treat, not the default.
FIELD_BONUS_MIN_LEVEL = 2

FIELD_BONUSES: list[dict] = [
    {
        "key": "hippie_donation",
        "name": "Local hippie commune donation",
        "dice_sums": (2, 12),  # 2/36 = 5.6% — biggest prize, rarest
        "notice": "A local hippie commune, grateful for the blissful beans, donates to your cause.",
        "cash_gain": 750,
    },
    {
        "key": "mobster_protection",
        "name": "Local mobster protection",
        "dice_sums": (3, 11),  # 4/36 = 11.1%
        "notice": "Local mobsters take a liking to you — no field challenges here while you stay.",
        "protection": True,
    },
    {
        "key": "govt_support",
        "name": "Local government support",
        "dice_sums": (4, 10),  # 6/36 = 16.7%
        "notice": "The local government announces surprise support for jungle beans and gifts you cash.",
        "cash_gain": 500,
    },
    {
        "key": "catch_thief",
        "name": "Caught the thief first",
        "dice_sums": (7,),  # 6/36 = 16.7%
        "notice": "You spot the thief before they can shake you down and pocket their cash instead.",
        "cash_gain": 300,
    },
    {
        "key": "travel_voucher",
        "name": "Journalist travel voucher",
        "dice_sums": (5, 9),  # 8/36 = 22.2% — smallest prize, most common
        "notice": "A local journalist, grateful for the story, gifts you a travel voucher.",
        "cash_gain": 200,
    },
]
FIELD_BONUS_BY_SUM: dict[int, dict] = {
    s: bonus for bonus in FIELD_BONUSES for s in bonus["dice_sums"]
}

# Airport-specific randomized penalties — a flat 1d6 roll on arrival,
# independent of level or market heat (unlike the field bonuses above).
# Each airport has its own flavor-text mishap; odds and cost are the same
# everywhere. Mobster protection still blocks it, matching the "no field
# challenges here" wording used for the sale-triggered events.
AIRPORT_PENALTY_NOTICE: dict[str, str] = {
    "ATL": "While driving out to Decatur to meet your contact, you stopped at "
    "Buc-ee's for gas and got bitten by a pygmy rattlesnake.",
    "DXB": "You locked eyes with the daughter of the Crown Prince a minute too "
    "long and were lightly caned for the faux pas.",
    "HND": "Your local contact gifted you fermented fish — you've had "
    "diarrhea for 3 days.",
    "DFW": "You ate a bad BBQ meal at Sergeant Gramps' Roadhouse.",
    "LHR": "Someone at your hotel blasted loud EDM beats until 5am and you "
    "nearly lost your mind.",
    "PVG": "Something felt off about that overcooked dim sum you just ate.",
    "DEN": "Caught in a snowstorm still wearing your short shorts from Rio.",
    "ORD": "You ate a diseased hot dog from a cart near Wrigley Field.",
    "IST": "That kebab turned out to be sourced from sickly hedgehog meat.",
    "GRU": "You ate some suspicious blueish-purple berries along the trail.",
}
AIRPORT_PENALTY_FACES = 1  # out of a d6 (1/6 ≈ 16.7% chance per arrival)
AIRPORT_PENALTY_LIFE_LOSS = 2  # half-heart units — one full heart

PINEAPPLE_EXPRESS: dict = {
    "key": "pineapple_express",
    "name": "Pineapple Express",
    "notice": "A pineapple express weather pattern rolls in, dropping bean prices here even further.",
    "price_discount_pct": 0.25,
}
PINEAPPLE_EXPRESS_FACES = 3  # out of 12 (25%) on arrival at a low-cost market

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

# Supply/demand: buying or selling a product at an airport nudges that
# product's local price, evaluated on a faster cadence
# (SUPPLY_DEMAND_EVAL_DAYS) than the general market refresh
# (PRICE_REFRESH_DAYS) — this is the player's own recent trading talking,
# not world noise. Two-sided: buying up local supply pushes price up
# (demand), dumping product pushes it down (oversupply); same mechanism,
# opposite sign of net volume. Scoped to airport+product only, matching how
# `drift` already works, so a flooded product doesn't tank everything else
# on sale at that airport.
SUPPLY_DEMAND_EVAL_DAYS = 2
# Price-fraction shift per unit of net (bought - sold) volume since the
# last eval, before decay/clamp. Sized against the qty the greedy Monte
# Carlo bot routinely trades (tens of units per sale) so a real flood
# moves price meaningfully while a one- or two-unit purchase barely
# registers.
SUPPLY_DEMAND_UNIT_IMPACT = 0.006
# Existing pressure decays toward 0 by this factor every eval, active
# trading or not — an airport the player stops visiting gradually heals
# instead of staying flooded/starved forever.
SUPPLY_DEMAND_DECAY = 0.7
# Clamp so sustained flooding/hoarding can't push a price to near-zero or
# through the roof — same order of magnitude as the drift clamp (±0.4).
SUPPLY_DEMAND_CAP = 0.35

AIRFARE_BASE_FEE = 75
AIRFARE_PER_KM = 0.06

STARTING_CASH = 5000
STARTING_LIFE = 10  # half-heart units; 10 == 5 full hearts
SALES_PER_DAY = 3
PRICE_REFRESH_DAYS = 4
WIN_NET_WORTH = 20000
# Winning also requires having actually sold beans through every airport —
# not just found one lucrative route — to match the "global distribution
# network" fantasy. Units sold, not sale attempts, at any product mix.
WIN_MIN_SALES_PER_AIRPORT = 1

# Player level (and product unlocks) advance with elapsed in-game days, not
# sales count — a new tier every LEVEL_UP_INTERVAL_DAYS days, capped at
# level 4. E.g. at 3: day 0-2 = level 1, day 3-5 = level 2 (Bean Gummies), etc.
LEVEL_UP_INTERVAL_DAYS = 3

# Field challenge penalties scale with player level — a new smuggler
# starting out with Raw Bean shouldn't face the same heat as a level 4
# operator moving Bean Oil. Every sampled penalty (cash/inventory/life/debt)
# is multiplied by this before being applied; percentages are then clamped
# to 100%. Trigger odds (heat) are unaffected — this only scales how much a
# challenge costs you once it fires, not how often one fires.
LEVEL_INTENSITY_MULTIPLIER: dict[int, float] = {
    1: 0.5,
    2: 0.75,
    3: 1.0,
    4: 1.25,
}
