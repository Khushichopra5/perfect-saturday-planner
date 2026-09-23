import planner.tools.places as places_mod
from planner.models import FOOD_CATEGORIES, PlaceCandidate
from planner.tools.places import (
    GeoLocation,
    _derive_category,
    _diversify,
    _nominatim_pois,
    geocode_city,
    get_activity_options,
    get_food_options,
    score_candidates,
)

GEO = GeoLocation(name="Testville", lat=12.9716, lon=77.5946, currency="INR", source="osm")


def _element(element_id, name, tags, lat=12.9716, lon=77.5946):
    return {"id": element_id, "tags": {"name": name, **tags}, "lat": lat, "lon": lon}


def _poi(poi_id, name, tags, lat=12.9716, lon=77.5946):
    return {"id": poi_id, "name": name, "tags": tags, "lat": lat, "lon": lon}


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


async def test_activity_options_filter_out_eating_venues(monkeypatch):
    elements = [
        _element(1, "Pasta Palace", {"amenity": "restaurant"}),
        _element(2, "Bean There Cafe", {"amenity": "cafe"}),
        _element(3, "Quick Bites", {"amenity": "fast_food"}),
        _element(4, "Cubbon Park", {"leisure": "park"}),
        _element(5, "City Museum", {"tourism": "museum"}),
    ]

    async def fake_overpass(query):
        return elements

    monkeypatch.setattr(places_mod, "_overpass", fake_overpass)
    result = await get_activity_options(GEO, ["food", "walks", "art"], [], False)

    assert result.items
    assert not ({c.category for c in result.items} & FOOD_CATEGORIES)
    names = {c.name for c in result.items}
    assert "Cubbon Park" in names
    assert "City Museum" in names
    assert "Pasta Palace" not in names
    assert "Bean There Cafe" not in names


async def test_activity_provider_is_nominatim_when_overpass_fails(monkeypatch):
    async def failing_overpass(query):
        raise RuntimeError("overpass down")

    async def fake_pois(city, terms, limit=20):
        return [
            _poi(10, "Quiet Park", {"leisure": "park"}),
            _poi(11, "City Museum", {"tourism": "museum"}),
        ]

    monkeypatch.setattr(places_mod, "_overpass", failing_overpass)
    monkeypatch.setattr(places_mod, "_nominatim_pois", fake_pois)

    result = await get_activity_options(GEO, ["walks", "art"], [], False)
    assert result.provider == "nominatim"
    assert {c.name for c in result.items} == {"Quiet Park", "City Museum"}


async def test_activity_provider_is_overpass_when_it_returns_elements(monkeypatch):
    elements = [
        _element(1, "Cubbon Park", {"leisure": "park"}),
        _element(2, "Lalbagh Garden", {"leisure": "garden"}),
    ]

    async def fake_overpass(query):
        return elements

    monkeypatch.setattr(places_mod, "_overpass", fake_overpass)
    result = await get_activity_options(GEO, ["walks", "nature"], [], False)
    assert result.provider == "overpass"
    assert len(result.items) >= 2


async def test_food_options_keep_only_food_categories(monkeypatch):
    elements = [
        _element(1, "Corner Bar", {"amenity": "bar"}),
        _element(2, "Veg Kitchen", {"amenity": "restaurant", "cuisine": "vegetarian"}),
    ]

    async def fake_overpass(query):
        return elements

    monkeypatch.setattr(places_mod, "_overpass", fake_overpass)
    result = await get_food_options(GEO, vegetarian=False, avoid_crowded=False)

    assert result.items
    assert all(c.category in FOOD_CATEGORIES for c in result.items)
    names = {c.name for c in result.items}
    assert "Veg Kitchen" in names
    assert "Corner Bar" not in names
