"""Tool: distance & travel realism.

Real coordinates (from OpenStreetMap) let us do two things mocks can't: order
the day so you're not zig-zagging across the city, and estimate how long the
hops actually take. That is what keeps a plan *realistic* rather than a wish list.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def travel_minutes(km: float) -> int:
    """Rough door-to-door travel time.

    Short hops are walked (~4.8 km/h); longer ones assume a cab/metro with a few
    minutes of waiting. Deliberately conservative so we don't over-promise.
    """
    if km <= 0:
        return 0
    if km <= 1.5:
        minutes = km / 4.8 * 60
    else:
        minutes = km / 20.0 * 60 + 4
    return max(5, int(round(minutes)))


def nearest_neighbour_order(stops: list, origin: tuple[float, float] | None):
    """Order ``(candidate, kind)`` tuples by proximity, starting from ``origin``.

    Falls back to the original order when coordinates are missing (e.g. the
    curated catalogue), so offline plans are unaffected.
    """
    if not stops:
        return stops
    if any(candidate.lat is None or candidate.lon is None for candidate, _ in stops):
        return stops

    remaining = list(stops)
    ordered: list = []
    cursor = origin
    while remaining:
        if cursor is None:
            best = remaining.pop(0)
        else:
            best = min(
                remaining,
                key=lambda s: haversine_km(cursor[0], cursor[1], s[0].lat, s[0].lon),
            )
            remaining.remove(best)
        ordered.append(best)
        candidate, _ = best
        cursor = (candidate.lat, candidate.lon)
    return ordered
