"""Curated offline catalogue.

This is the graceful-degradation path: when the live OpenStreetMap lookups are
unavailable (offline, rate-limited, timeout) or return nothing useful, the agent
falls back to these templates so the user always gets a plan. Costs here are
hand-tuned per template rather than derived from category defaults.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Interest, PlaceCandidate


@dataclass(frozen=True)
class KnownCity:
    name: str
    lat: float
    lon: float
    currency: str
    aliases: tuple[str, ...] = ()


KNOWN_CITIES: tuple[KnownCity, ...] = (
    KnownCity("Bangalore", 12.9716, 77.5946, "INR", ("bengaluru", "blr", "banglore")),
    KnownCity("Mumbai", 19.0760, 72.8777, "INR", ("bombay",)),
    KnownCity("Delhi", 28.6139, 77.2090, "INR", ("new delhi", "ncr")),
    KnownCity("Pune", 18.5204, 73.8567, "INR"),
    KnownCity("Chennai", 13.0827, 80.2707, "INR", ("madras",)),
    KnownCity("Hyderabad", 17.3850, 78.4867, "INR"),
    KnownCity("Kolkata", 22.5726, 88.3639, "INR", ("calcutta",)),
    KnownCity("Jaipur", 26.9124, 75.7873, "INR"),
    KnownCity("Goa", 15.4909, 73.8278, "INR", ("panaji", "panjim")),
    KnownCity("Kochi", 9.9312, 76.2673, "INR", ("cochin",)),
    KnownCity("New York", 40.7128, -74.0060, "USD", ("nyc", "manhattan")),
    KnownCity("London", 51.5074, -0.1278, "GBP"),
    KnownCity("San Francisco", 37.7749, -122.4194, "USD", ("sf", "bay area")),
    KnownCity("Singapore", 1.3521, 103.8198, "SGD"),
    KnownCity("Dubai", 25.2048, 55.2708, "AED"),
    KnownCity("Tokyo", 35.6762, 139.6503, "JPY"),
    KnownCity("Paris", 48.8566, 2.3522, "EUR"),
    KnownCity("Berlin", 52.5200, 13.4050, "EUR"),
    KnownCity("Sydney", -33.8688, 151.2093, "AUD"),
)


def find_known_city(text: str) -> KnownCity | None:
    """Return the first known city mentioned in ``text`` (fuzzy on aliases)."""
    q = (text or "").lower().strip()
    if not q:
        return None
    for city in KNOWN_CITIES:
        if q == city.name.lower() or q in city.aliases:
            return city
        if city.name.lower() in q:
            return city
        for alias in city.aliases:
            if len(alias) > 2 and alias in q:
                return city
    return None


@dataclass(frozen=True)
class MockTemplate:
    name: str
    category: str
    interests: tuple[Interest, ...]
    crowd: str
    cost: int
    vegetarian_friendly: bool = True
    tags: tuple[tuple[str, str], ...] = ()


ACTIVITY_TEMPLATES: tuple[MockTemplate, ...] = (
    MockTemplate("{city} City Museum", "museum", ("art", "history"), "medium", 200, tags=(("tourism", "museum"),)),
    MockTemplate("Old {city} Heritage Walk", "heritage walk", ("history", "walks"), "low", 0, tags=(("historic", "yes"),)),
    MockTemplate("{city} Botanical Gardens", "garden", ("nature", "walks"), "low", 0, tags=(("leisure", "garden"),)),
    MockTemplate("Riverside Promenade, {city}", "promenade", ("walks", "nature"), "low", 0, tags=(("leisure", "park"),)),
    MockTemplate("{city} Contemporary Art Gallery", "gallery", ("art",), "low", 150, tags=(("tourism", "gallery"),)),
    MockTemplate("{city} Live Music Room", "music venue", ("music", "nightlife"), "medium", 600, tags=(("amenity", "music_venue"),)),
    MockTemplate("Indie Sessions @ {city}", "live gig", ("music",), "medium", 500, tags=(("amenity", "music_venue"),)),
    MockTemplate("{city} Central Market", "market", ("shopping", "food"), "high", 0, tags=(("amenity", "marketplace"),)),
    MockTemplate("{city} Book Cafe & Library", "bookstore", ("books", "coffee"), "low", 0, tags=(("shop", "books"),)),
    MockTemplate("{city} Board Game Lounge", "game lounge", ("games",), "medium", 350, tags=(("leisure", "amusement_arcade"),)),
    MockTemplate("{city} Rooftop Cinema", "cinema", ("games", "art"), "medium", 350, tags=(("amenity", "cinema"),)),
    MockTemplate("Sunset Viewpoint, {city}", "viewpoint", ("nature", "walks"), "medium", 0, tags=(("tourism", "viewpoint"),)),
    MockTemplate("{city} Pottery & Craft Studio", "workshop", ("art", "games"), "low", 500, tags=(("amenity", "arts_centre"),)),
    MockTemplate("{city} Lakeside Cycling Loop", "cycling", ("nature", "games"), "low", 200, tags=(("leisure", "park"),)),
)

FOOD_TEMPLATES: tuple[MockTemplate, ...] = (
    MockTemplate("The Green Table, {city}", "vegetarian restaurant", ("food",), "low", 450, True, (("amenity", "restaurant"), ("cuisine", "vegetarian"))),
    MockTemplate("{city} South Indian Tiffin House", "restaurant", ("food",), "medium", 300, True, (("amenity", "restaurant"), ("cuisine", "south_indian"))),
    MockTemplate("Momo & More, {city}", "restaurant", ("food",), "medium", 400, True, (("amenity", "restaurant"), ("cuisine", "asian"))),
    MockTemplate("{city} Artisan Coffee Roasters", "cafe", ("coffee", "food"), "low", 250, True, (("amenity", "cafe"),)),
    MockTemplate("Garden Cafe {city}", "cafe", ("coffee", "food"), "low", 300, True, (("amenity", "cafe"),)),
    MockTemplate("{city} Wood-Fired Pizza Co.", "restaurant", ("food",), "medium", 600, True, (("amenity", "restaurant"), ("cuisine", "pizza"))),
    MockTemplate("Biryani Junction, {city}", "restaurant", ("food",), "high", 500, False, (("amenity", "restaurant"), ("cuisine", "indian")),),
    MockTemplate("{city} Street Food Lane", "street food", ("food",), "high", 200, True, (("amenity", "restaurant"), ("cuisine", "street_food"))),
)


def _build(templates: tuple[MockTemplate, ...], city: str, prefix: str) -> list[PlaceCandidate]:
    city = city or "Your City"
    items: list[PlaceCandidate] = []
    for i, t in enumerate(templates):
        items.append(
            PlaceCandidate(
                id=f"{prefix}-{i}",
                name=t.name.format(city=city),
                category=t.category,
                interests=list(t.interests),
                source="mock",
                crowd=t.crowd,  # type: ignore[arg-type]
                vegetarian_friendly=t.vegetarian_friendly,
                est_cost=t.cost,
                tags=dict(t.tags),
            )
        )
    return items


def build_mock_activities(city: str) -> list[PlaceCandidate]:
    return _build(ACTIVITY_TEMPLATES, city, "mock-act")


def build_mock_food(city: str) -> list[PlaceCandidate]:
    return _build(FOOD_TEMPLATES, city, "mock-food")
