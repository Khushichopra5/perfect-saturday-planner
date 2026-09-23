"""Tool: estimateCost.

Turns a list of places into a believable spend figure. We prefer a real
``charge``/``fee`` tag from OpenStreetMap when present, then the template cost
for curated places, then a per-category default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Currency, PlaceCandidate, Preferences

BASE_COST_INR: dict[str, int] = {
    "museum": 200,
    "gallery": 150,
    "arts centre": 300,
    "attraction": 100,
    "park": 0,
    "garden": 0,
    "viewpoint": 0,
    "waterfront": 0,
    "pedestrian street": 0,
    "historic site": 50,
    "music venue": 700,
    "nightclub": 800,
    "bar": 600,
    "theatre": 400,
    "cinema": 350,
    "arcade": 400,
    "bowling": 400,
    "sports centre": 300,
    "mall": 0,
    "department store": 0,
    "bookstore": 0,
    "library": 0,
    "record store": 0,
    "market": 0,
    "food court": 350,
    "restaurant": 500,
    "cafe": 300,
    "café": 300,
    "fast food": 250,
    "place": 100,
}

ACTIVITY_DEFAULT_INR = 150

# Rough INR -> local conversion factors and symbols. Costs are estimates, so we
# only need to be in the right ballpark — but we should at least use the right
# currency for the city rather than defaulting everything to dollars.
CURRENCY_FACTOR: dict[str, float] = {
    "INR": 1.0,
    "USD": 0.02,
    "EUR": 0.018,
    "GBP": 0.016,
    "JPY": 3.0,
    "SGD": 0.027,
    "AED": 0.073,
    "AUD": 0.030,
}

CURRENCY_SYMBOL: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "SGD": "S$",
    "AED": "AED ",
    "AUD": "A$",
}

DEFAULT_BUDGET: dict[str, int] = {
    "INR": 2000,
    "USD": 40,
    "EUR": 40,
    "GBP": 35,
    "JPY": 6000,
    "SGD": 55,
    "AED": 150,
    "AUD": 60,
}


def _parse_charge(tags: dict[str, str]) -> int | None:
    charge = tags.get("charge") or tags.get("fee")
    if not charge or charge in ("no", "yes"):
        return None
    match = re.search(r"([\d]+(?:\.\d+)?)", charge)
    if not match:
        return None
    value = float(match.group(1))
    if value <= 0:
        return None
    return int(round(value))


def convert_cost(inr: int, currency: Currency) -> int:
    if currency == "INR":
        return int(round(inr / 10.0)) * 10
    return max(0, int(round(inr * CURRENCY_FACTOR.get(currency, 0.02))))


def estimate_item_cost(candidate: PlaceCandidate, currency: Currency) -> int:
    charged = _parse_charge(candidate.tags)
    if charged is not None:
        return convert_cost(charged, currency)
    if candidate.est_cost is not None:
        return convert_cost(candidate.est_cost, currency)
    base = BASE_COST_INR.get(candidate.category, ACTIVITY_DEFAULT_INR)
    return convert_cost(base, currency)


@dataclass
class CostBreakdown:
    total: int
    within_budget: bool
    over_by: int
    currency: Currency

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "within_budget": self.within_budget,
            "over_by": self.over_by,
            "currency": self.currency,
        }


def estimate_cost(costs: list[int], budget: int | None, currency: Currency = "INR") -> CostBreakdown:
    total = sum(costs)
    within = True if budget is None else total <= budget
    over_by = 0 if budget is None or within else total - budget
    return CostBreakdown(total=total, within_budget=within, over_by=over_by, currency=currency)


def format_money(amount: int, currency: Currency) -> str:
    return f"{CURRENCY_SYMBOL.get(currency, '')}{amount:,}"


def default_budget(currency: Currency) -> int:
    return DEFAULT_BUDGET.get(currency, 2000)


def normalize_budget(prefs: Preferences) -> int:
    return prefs.budget if prefs.budget is not None else default_budget(prefs.currency)
