from planner.models import PlaceCandidate
from planner.tools.places import (
    _derive_category,
    _diversify,
    _nominatim_pois,
    geocode_city,
    score_candidates,
)


def test_derive_category_known_tags():
    assert _derive_category({"tourism": "museum"})[0] == "museum"
    assert _derive_category({"amenity": "cafe"})[0] == "cafe"
    assert _derive_category({"amenity": "pub"})[0] == "bar"
    assert _derive_category({"craft": "brewery"})[0] == "bar"
    assert _derive_category({"leisure": "park"})[0] == "park"


def test_unknown_tags_do_not_claim_a_false_interest():
    category, interests = _derive_category({"weird": "tag"})
    assert category == "place"
    assert interests == []


def test_diversify_caps_categories():
    parks = [
        PlaceCandidate(id=str(i), name=f"P{i}", category="park", interests=["walks"], source="osm")
        for i in range(10)
    ]
    venue = PlaceCandidate(id="m", name="Music Room", category="music venue", interests=["music"], source="osm")
    out = _diversify(parks + [venue], 24, 5)
    assert sum(1 for c in out if c.category == "park") == 5
    assert any(c.category == "music venue" for c in out)


def test_score_prefers_matching_interest():
    park = PlaceCandidate(id="p", name="Park", category="park", interests=["walks"], source="osm", crowd="low")
    bar = PlaceCandidate(id="b", name="Bar", category="bar", interests=["nightlife"], source="osm", crowd="high")
    ranked = score_candidates([bar, park], ["walks"], ["relaxed"], True)
    assert ranked[0].id == "p"


def test_vegetarian_penalty_ranks_veg_first():
    veg = PlaceCandidate(id="v", name="Veg", category="restaurant", interests=["food"], source="osm", vegetarian_friendly=True)
    meat = PlaceCandidate(id="m", name="Meat", category="restaurant", interests=["food"], source="osm", vegetarian_friendly=False)
    ranked = score_candidates([meat, veg], ["food"], [], False, require_vegetarian=True)
    assert ranked[0].id == "v"


async def test_geocode_known_city_offline_uses_city_index():
    geo = await geocode_city("Bangalore")
    assert geo is not None
    assert geo.source == "mock"
    assert geo.currency == "INR"
    assert abs(geo.lat - 12.9716) < 0.01


async def test_geocode_unknown_city_offline_returns_none():
    assert await geocode_city("Zzyzx-Nowhere-123") is None


async def test_nominatim_fallback_is_disabled_offline():
    assert await _nominatim_pois("Bangalore", ["park"]) == []
