"""Tool: getActivityOptions / getFoodOptions (with geocodeCity).

This is the "real data" part of the assignment. We use two free, keyless
OpenStreetMap services:

* **Nominatim** to geocode the city name.
* **Overpass API** to pull nearby places for the user's interests.

Everything degrades gracefully: if either service is slow, down, rate-limited or
returns nothing, the caller falls back to the curated catalogue in
``planner.data.mock_data``. Network access can be disabled entirely with
``PLANNER_OFFLINE=1`` (used by the test-suite).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..data.mock_data import find_known_city
from ..models import FOOD_CATEGORIES, Currency, Interest, MoodTag, PlaceCandidate, PlaceSource

USER_AGENT = "PerfectSaturdayPlanner/1.0 (open-source Saturday planning demo)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

NOMINATIM_TIMEOUT = 6.0
OVERPASS_TIMEOUT = 8.0
OVERPASS_TOTAL_BUDGET = 11.0

COUNTRY_CURRENCY: dict[str, Currency] = {
    "in": "INR",
    "us": "USD",
    "gb": "GBP",
    "fr": "EUR",
    "de": "EUR",
    "es": "EUR",
    "it": "EUR",
    "nl": "EUR",
    "be": "EUR",
    "at": "EUR",
    "pt": "EUR",
    "ie": "EUR",
    "jp": "JPY",
    "sg": "SGD",
    "ae": "AED",
    "au": "AUD",
}

_geo_cache: dict[str, "GeoLocation | None"] = {}
_overpass_cache: dict[str, list[dict[str, Any]]] = {}


def offline() -> bool:
    return os.getenv("PLANNER_OFFLINE", "").lower() in ("1", "true", "yes")


@dataclass
class GeoLocation:
    name: str
    lat: float
    lon: float
    currency: Currency
    source: PlaceSource


@dataclass
class OptionsResult:
    items: list[PlaceCandidate]
    source: PlaceSource
    provider: str = "none"  # "overpass" | "nominatim" | "none"


async def geocode_city(city: str) -> Optional[GeoLocation]:
    """Resolve a city name to coordinates via Nominatim, with a known-city fallback."""
    key = city.lower().strip()
    if key in _geo_cache:
        return _geo_cache[key]

    known = find_known_city(city)

    if not offline():
        try:
            async with httpx.AsyncClient(timeout=NOMINATIM_TIMEOUT) as client:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={"q": city, "format": "json", "limit": 1, "addressdetails": 1},
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    country = (data[0].get("address") or {}).get("country_code", "").lower()
                    currency: Currency = COUNTRY_CURRENCY.get(country) or (known.currency if known else "USD")  # type: ignore[assignment]
                    loc = GeoLocation(
                        name=city,
                        lat=float(data[0]["lat"]),
                        lon=float(data[0]["lon"]),
                        currency=currency,
                        source="osm",
                    )
                    _geo_cache[key] = loc
                    return loc
        except (httpx.HTTPError, ValueError, KeyError):
            pass

    if known:
        loc = GeoLocation(name=known.name, lat=known.lat, lon=known.lon, currency=known.currency, source="mock")  # type: ignore[arg-type]
        _geo_cache[key] = loc
        return loc

    _geo_cache[key] = None
    return None


async def _overpass(query: str) -> list[dict[str, Any]]:
    if query in _overpass_cache:
        return _overpass_cache[query]
    if offline():
        raise RuntimeError("offline mode")

    last_error: Exception | None = None
    deadline = time.monotonic() + OVERPASS_TOTAL_BUDGET
    for endpoint in OVERPASS_ENDPOINTS:
        remaining = deadline - time.monotonic()
        if remaining <= 1.0:
            break
        try:
            async with httpx.AsyncClient(timeout=min(OVERPASS_TIMEOUT, remaining)) as client:
                resp = await client.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                last_error = RuntimeError(f"Overpass responded {resp.status_code}")
                continue
            elements = resp.json().get("elements", [])
            result: list[dict[str, Any]] = []
            for el in elements:
                tags = el.get("tags") or {}
                if not tags.get("name"):
                    continue
                center = el.get("center") or {}
                result.append(
                    {
                        "id": el.get("id"),
                        "tags": tags,
                        "lat": el.get("lat", center.get("lat")),
                        "lon": el.get("lon", center.get("lon")),
                    }
                )
            _overpass_cache[query] = result
            return result
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
    raise last_error or RuntimeError("Overpass request failed")


INTEREST_OSM_TAGS: dict[Interest, tuple[str, ...]] = {
    "food": ('["amenity"="marketplace"]', '["amenity"="food_court"]'),
    "music": ('["amenity"="music_venue"]', '["amenity"="theatre"]', '["shop"="music"]', '["amenity"="nightclub"]'),
    "walks": ('["leisure"="park"]', '["tourism"="viewpoint"]', '["leisure"="garden"]'),
    "art": ('["tourism"="museum"]', '["tourism"="gallery"]', '["amenity"="arts_centre"]'),
    "history": ('["historic"]', '["tourism"="museum"]', '["historic"="monument"]', '["tourism"="attraction"]'),
    "nature": ('["leisure"="park"]', '["leisure"="garden"]', '["natural"="water"]', '["tourism"="viewpoint"]'),
    "shopping": ('["shop"="mall"]', '["shop"="department_store"]', '["amenity"="marketplace"]', '["shop"="books"]'),
    "games": ('["leisure"="amusement_arcade"]', '["leisure"="bowling_alley"]', '["leisure"="sports_centre"]', '["amenity"="cinema"]'),
    "coffee": ('["amenity"="cafe"]', '["shop"="bakery"]'),
    "books": ('["shop"="books"]', '["amenity"="library"]'),
    "nightlife": ('["amenity"="bar"]', '["amenity"="nightclub"]', '["amenity"="music_venue"]'),
    "wellness": ('["leisure"="spa"]', '["amenity"="spa"]', '["leisure"="fitness_centre"]'),
}

DEFAULT_INTERESTS: tuple[Interest, ...] = ("art", "walks", "nature", "food")

NON_VEG_CUISINES = ("barbecue", "steak", "seafood", "chicken", "kebab", "fish", "burger", "sushi", "grill", "meat")


def _build_union_query(filters: list[str], lat: float, lon: float, radius: int, limit: int) -> str:
    unique = list(dict.fromkeys(filters))
    body = "\n".join(f"  nwr{f}(around:{radius},{lat},{lon});" for f in unique)
    return f"[out:json][timeout:20];\n(\n{body}\n);\nout center {limit};"


def _crowd_from_tags(tags: dict[str, str], category: str) -> str:
    if category in ("marketplace", "mall", "attraction", "cinema", "market"):
        return "high"
    if category in ("museum", "restaurant", "viewpoint", "nightclub", "music venue", "zoo", "theme park"):
        return "medium"
    if tags.get("tourism") == "attraction":
        return "high"
    return "low"


def _derive_category(tags: dict[str, str]) -> tuple[str, list[Interest]]:
    if tags.get("tourism") == "museum":
        return "museum", ["art", "history"]
    if tags.get("tourism") == "gallery":
        return "gallery", ["art"]
    if tags.get("tourism") == "viewpoint":
        return "viewpoint", ["nature", "walks"]
    if tags.get("tourism") == "attraction":
        return "attraction", ["history", "walks"]
    if tags.get("amenity") == "arts_centre":
        return "arts centre", ["art"]
    if tags.get("amenity") == "music_venue":
        return "music venue", ["music", "nightlife"]
    if tags.get("amenity") == "nightclub":
        return "nightclub", ["music", "nightlife"]
    if tags.get("amenity") in ("bar", "pub", "biergarten"):
        return "bar", ["nightlife"]
    if tags.get("craft") == "brewery" or tags.get("industrial") == "brewery":
        return "bar", ["nightlife"]
    if tags.get("amenity") == "cafe":
        return "cafe", ["coffee", "food"]
    if tags.get("amenity") == "restaurant":
        return "restaurant", ["food"]
    if tags.get("amenity") == "fast_food":
        return "fast food", ["food"]
    if tags.get("amenity") == "food_court":
        return "food court", ["food"]
    if tags.get("amenity") == "marketplace":
        return "market", ["shopping", "food"]
    if tags.get("amenity") == "cinema":
        return "cinema", ["games", "art"]
    if tags.get("amenity") == "theatre":
        return "theatre", ["music", "art"]
    if tags.get("amenity") == "library":
        return "library", ["books"]
    if tags.get("leisure") == "park":
        return "park", ["nature", "walks"]
    if tags.get("leisure") == "garden":
        return "garden", ["nature", "walks"]
    if tags.get("leisure") == "amusement_arcade":
        return "arcade", ["games"]
    if tags.get("leisure") == "bowling_alley":
        return "bowling", ["games"]
    if tags.get("leisure") == "sports_centre":
        return "sports centre", ["games"]
    if tags.get("leisure") == "fitness_centre":
        return "gym", ["wellness"]
    if tags.get("shop") == "mall":
        return "mall", ["shopping"]
    if tags.get("shop") == "department_store":
        return "department store", ["shopping"]
    if tags.get("shop") == "books":
        return "bookstore", ["books"]
    if tags.get("shop") == "music":
        return "record store", ["music"]
    if tags.get("historic"):
        return "historic site", ["history"]
    if tags.get("natural") == "water":
        return "waterfront", ["nature", "walks"]
    if tags.get("highway") == "pedestrian":
        return "pedestrian street", ["walks", "shopping"]
    return "place", []


def _is_vegetarian_friendly(tags: dict[str, str]) -> bool:
    if tags.get("diet:vegetarian") == "yes" or tags.get("diet:vegan") == "yes":
        return True
    cuisine = (tags.get("cuisine") or "").lower()
    if any(word in cuisine for word in ("vegetarian", "vegan", "jain", "south_indian", "gujarati", "salad", "dessert", "ice_cream", "pizza", "pasta", "cafe")):
        return True
    if any(word in cuisine for word in NON_VEG_CUISINES):
        return False
    # Unknown cuisine: most restaurants/cafes can feed a vegetarian, so only an
    # explicitly non-vegetarian cuisine disqualifies a place.
    return tags.get("amenity") in ("restaurant", "cafe", "fast_food")


def _score_candidate(
    candidate: PlaceCandidate,
    interests: list[Interest],
    mood_tags: list[MoodTag],
    avoid_crowded: bool,
    require_vegetarian: bool,
) -> float:
    score = 0.0
    wanted = interests or list(DEFAULT_INTERESTS)
    for interest in candidate.interests:
        if interest in wanted:
            score += 3
    if candidate.category in ("park", "garden"):
        if "relaxed" in mood_tags or "cozy" in mood_tags:
            score += 2
        if "energetic" in mood_tags or "adventurous" in mood_tags:
            score += 1
    if candidate.category in ("cafe", "café", "library", "bookstore"):
        if set(mood_tags) & {"relaxed", "cozy", "creative"}:
            score += 2
    if candidate.category in ("music venue", "bar", "nightclub", "arcade", "bowling"):
        if set(mood_tags) & {"social", "energetic", "playful"}:
            score += 2
    if candidate.category in ("museum", "gallery", "arts centre"):
        if set(mood_tags) & {"creative", "relaxed"}:
            score += 1
    if candidate.crowd == "high":
        score -= 6 if avoid_crowded else 1
    if candidate.crowd == "medium" and avoid_crowded:
        score -= 2
    if require_vegetarian and not candidate.vegetarian_friendly:
        score -= 10
    if candidate.lat is None:
        score -= 1
    return score


def prefer_vegetarian(items: list[PlaceCandidate], vegetarian: bool) -> list[PlaceCandidate]:
    """If vegetarian and any veg-friendly option exists, drop the rest.

    Keeps us from picking a non-veg stop that then gets removed by validation.
    """
    if not vegetarian:
        return items
    veg = [c for c in items if c.vegetarian_friendly]
    return veg or items


def score_candidates(
    items: list[PlaceCandidate],
    interests: list[Interest],
    mood_tags: list[MoodTag],
    avoid_crowded: bool,
    require_vegetarian: bool = False,
) -> list[PlaceCandidate]:
    """Score and rank any candidate pool (used for curated fallbacks too)."""
    for candidate in items:
        candidate.score = _score_candidate(candidate, interests, mood_tags, avoid_crowded, require_vegetarian)
    return sorted(items, key=lambda c: (-c.score, c.name))


def _candidate_from_element(el: dict[str, Any], prefix: str, wanted: list[Interest], mood_tags: list[MoodTag], avoid_crowded: bool, require_vegetarian: bool) -> PlaceCandidate:
    tags = el["tags"]
    category, interests = _derive_category(tags)
    candidate = PlaceCandidate(
        id=f"{prefix}-{el['id']}",
        name=tags["name"],
        category=category,
        interests=interests,
        lat=el.get("lat"),
        lon=el.get("lon"),
        address=tags.get("addr:street"),
        source="osm",
        tags=tags,
        crowd=_crowd_from_tags(tags, category),  # type: ignore[arg-type]
        vegetarian_friendly=_is_vegetarian_friendly(tags),
    )
    candidate.score = _score_candidate(candidate, wanted, mood_tags, avoid_crowded, require_vegetarian)
    return candidate


INTEREST_SEARCH_TERMS: dict[Interest, str] = {
    "food": "market",
    "music": "live music venue",
    "walks": "park",
    "art": "museum",
    "history": "historic site",
    "nature": "park",
    "shopping": "market",
    "games": "amusement arcade",
    "coffee": "cafe",
    "books": "bookstore",
    "nightlife": "bar",
    "wellness": "spa",
}

POI_CLASSES = {"amenity", "tourism", "leisure", "shop", "historic", "natural"}


async def _nominatim_pois(city: str, terms: list[str], limit: int = 20) -> list[dict[str, Any]]:
    """Second live source: search named POIs via Nominatim.

    Overpass occasionally 504s under load; Nominatim is the same free
    OpenStreetMap ecosystem and much more reliable, so we use it as a backup.
    We honour its 1 request/second policy with a small sleep between calls.
    """
    if offline():
        return []
    results: list[dict[str, Any]] = []
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=NOMINATIM_TIMEOUT) as client:
        for term in dict.fromkeys(terms):
            try:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={"q": f"{term} in {city}", "format": "jsonv2", "limit": limit, "addressdetails": 1, "extratags": 1},
                    headers=headers,
                )
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            for item in resp.json():
                klass = item.get("category") or item.get("class") or ""
                if klass not in POI_CLASSES or not item.get("name"):
                    continue
                tags: dict[str, str] = {klass: str(item.get("type", ""))}
                tags.update({k: str(v) for k, v in (item.get("extratags") or {}).items()})
                results.append(
                    {
                        "id": item.get("place_id"),
                        "name": item["name"],
                        "lat": float(item["lat"]) if item.get("lat") else None,
                        "lon": float(item["lon"]) if item.get("lon") else None,
                        "tags": tags,
                        "address": (item.get("address") or {}).get("road"),
                    }
                )
            await asyncio.sleep(1.1)
    return results


def _candidate_from_poi(poi: dict[str, Any], prefix: str, wanted: list[Interest], mood_tags: list[MoodTag], avoid_crowded: bool, require_vegetarian: bool) -> PlaceCandidate:
    tags = poi["tags"]
    category, interests = _derive_category(tags)
    candidate = PlaceCandidate(
        id=f"{prefix}-n{poi['id']}",
        name=poi["name"],
        category=category,
        interests=interests,
        lat=poi.get("lat"),
        lon=poi.get("lon"),
        address=poi.get("address"),
        source="osm",
        tags=tags,
        crowd=_crowd_from_tags(tags, category),  # type: ignore[arg-type]
        vegetarian_friendly=_is_vegetarian_friendly(tags),
    )
    candidate.score = _score_candidate(candidate, wanted, mood_tags, avoid_crowded, require_vegetarian)
    return candidate


def _dedupe(items: list[PlaceCandidate]) -> list[PlaceCandidate]:
    seen: set[str] = set()
    out: list[PlaceCandidate] = []
    for item in items:
        key = item.name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _diversify(items: list[PlaceCandidate], limit: int, per_category: int) -> list[PlaceCandidate]:
    """Cap how many of any single category enter the pool.

    A dense city can return 100 parks; without this the shortlist is all parks
    and the plan loses variety.
    """
    out: list[PlaceCandidate] = []
    counts: dict[str, int] = {}
    for item in items:
        if counts.get(item.category, 0) >= per_category:
            continue
        out.append(item)
        counts[item.category] = counts.get(item.category, 0) + 1
        if len(out) >= limit:
            break
    return out


async def get_activity_options(
    geo: GeoLocation,
    interests: list[Interest],
    mood_tags: list[MoodTag],
    avoid_crowded: bool,
) -> OptionsResult:
    """Fetch candidate activities: Overpass first, then Nominatim, then nothing.

    The agent layers the curated catalogue on top if this returns too few.
    """
    wanted = interests or list(DEFAULT_INTERESTS)
    items: list[PlaceCandidate] = []
    provider = "none"
    try:
        filters: list[str] = []
        for interest in wanted:
            filters.extend(INTEREST_OSM_TAGS.get(interest, ()))
        query = _build_union_query(filters, geo.lat, geo.lon, 6000, 140)
        elements = await _overpass(query)
        items = _dedupe([_candidate_from_element(el, "osm", wanted, mood_tags, avoid_crowded, False) for el in elements])
        if items:
            provider = "overpass"
    except Exception:  # noqa: BLE001 - fall through to the second source
        items = []

    if len(items) < 2:
        try:
            terms = [INTEREST_SEARCH_TERMS.get(i, "attraction") for i in wanted]
            pois = await _nominatim_pois(geo.name, terms)
            fallback = _dedupe([_candidate_from_poi(p, "osmp", wanted, mood_tags, avoid_crowded, False) for p in pois])
            if fallback:
                provider = "overpass+nominatim" if items else "nominatim"
                items = _dedupe(items + fallback)
        except Exception:  # noqa: BLE001
            pass

    # Eating venues belong to the food tool, not the activity pool.
    items = [c for c in items if c.category not in FOOD_CATEGORIES]
    items.sort(key=lambda c: (-c.score, c.name))
    return OptionsResult(items=_diversify(items, 24, 5), source="osm", provider=provider)


async def get_food_options(
    geo: GeoLocation,
    vegetarian: bool,
    avoid_crowded: bool,
) -> OptionsResult:
    """Fetch candidate food stops: Overpass first, then Nominatim."""
    items: list[PlaceCandidate] = []
    provider = "none"
    try:
        filters = ['["amenity"="restaurant"]', '["amenity"="cafe"]', '["amenity"="fast_food"]']
        query = _build_union_query(filters, geo.lat, geo.lon, 5000, 160)
        elements = await _overpass(query)
        items = _dedupe([_candidate_from_element(el, "osm-food", ["food", "coffee"], [], avoid_crowded, vegetarian) for el in elements])
        if items:
            provider = "overpass"
    except Exception:  # noqa: BLE001
        items = []

    if len(items) < 1:
        try:
            pois = await _nominatim_pois(geo.name, ["restaurant", "cafe"])
            fallback = _dedupe([_candidate_from_poi(p, "osmp-food", ["food", "coffee"], [], avoid_crowded, vegetarian) for p in pois])
            if fallback:
                provider = "overpass+nominatim" if items else "nominatim"
                items = _dedupe(items + fallback)
        except Exception:  # noqa: BLE001
            pass

    # Keep only genuine eating venues (a bar that matches a "restaurant" search
    # is not a food stop).
    items = [c for c in items if c.category in FOOD_CATEGORIES]
    items = prefer_vegetarian(items, vegetarian)
    for candidate in items:
        if vegetarian and not candidate.vegetarian_friendly:
            candidate.note = "Not tagged vegetarian — verify before booking."
    items.sort(key=lambda c: (-c.score, c.name))
    return OptionsResult(items=_diversify(items, 20, 8), source="osm", provider=provider)
