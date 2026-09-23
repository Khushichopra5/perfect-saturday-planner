from planner.models import PlaceCandidate
from planner.tools.cost import (
    convert_cost,
    default_budget,
    estimate_cost,
    estimate_item_cost,
    format_money,
)


def test_free_activity_costs_nothing(activities):
    garden = next(c for c in activities if c.category == "garden")
    assert estimate_item_cost(garden, "INR") == 0


def test_curated_template_cost_is_used(activities):
    museum = next(c for c in activities if c.category == "museum")
    assert estimate_item_cost(museum, "INR") == 200


def test_osm_charge_tag_wins_over_defaults():
    candidate = PlaceCandidate(
        id="x", name="Museum", category="museum", interests=["art"], source="osm", tags={"charge": "350"}
    )
    assert estimate_item_cost(candidate, "INR") == 350


def test_free_tag_is_ignored():
    candidate = PlaceCandidate(
        id="x", name="Park", category="park", interests=["walks"], source="osm", tags={"fee": "no"}
    )
    assert estimate_item_cost(candidate, "INR") == 0


def test_usd_conversion():
    assert convert_cost(2000, "USD") == 40


def test_estimate_cost_flags_over_budget():
    breakdown = estimate_cost([500, 600], 1000, "INR")
    assert breakdown.total == 1100
    assert breakdown.within_budget is False
    assert breakdown.over_by == 100


def test_estimate_cost_without_budget_is_within():
    breakdown = estimate_cost([500], None, "INR")
    assert breakdown.within_budget is True
    assert breakdown.over_by == 0


def test_format_money():
    assert format_money(2000, "INR") == "₹2,000"
    assert format_money(40, "USD") == "$40"


def test_format_money_gbp_eur_jpy():
    assert format_money(35, "GBP") == "£35"
    assert format_money(40, "EUR") == "€40"
    assert format_money(6000, "JPY") == "¥6,000"


def test_convert_cost_gbp_eur_jpy():
    assert convert_cost(2000, "GBP") == 32
    assert convert_cost(2000, "EUR") == 36
    assert convert_cost(2000, "JPY") == 6000


def test_default_budget_gbp_eur_jpy():
    assert default_budget("GBP") == 35
    assert default_budget("EUR") == 40
    assert default_budget("JPY") == 6000
