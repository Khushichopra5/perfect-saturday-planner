"""Tool: generateFinalPlan.

Takes the scored candidate pools plus the parsed preferences and assembles a
sequenced, timed itinerary. Every stop carries a ``why`` explaining how it fits
the user, which is what turns a list of places into a *plan*.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..models import Interest, PlaceCandidate, Plan, PlanItem, PlanItemKind, Preferences
from .cost import estimate_item_cost, format_money

DURATIONS: dict[str, int] = {
    "museum": 90,
    "gallery": 60,
    "arts centre": 90,
    "attraction": 60,
    "park": 45,
    "garden": 45,
    "viewpoint": 30,
    "waterfront": 45,
    "pedestrian street": 45,
    "historic site": 45,
    "heritage walk": 60,
    "promenade": 45,
    "music venue": 120,
    "live gig": 120,
    "nightclub": 120,
    "bar": 60,
    "theatre": 120,
    "cinema": 120,
    "arcade": 90,
    "game lounge": 90,
    "bowling": 90,
    "sports centre": 90,
    "cycling": 90,
    "workshop": 90,
    "mall": 60,
    "department store": 45,
    "bookstore": 45,
    "library": 45,
    "record store": 30,
    "market": 60,
    "food court": 45,
    "restaurant": 60,
    "vegetarian restaurant": 60,
    "street food": 45,
    "cafe": 45,
    "café": 45,
    "fast food": 30,
    "place": 45,
}

INTEREST_LABELS: dict[Interest, str] = {
    "food": "food",
    "music": "live music",
    "walks": "walks",
    "art": "art & museums",
    "history": "history",
    "nature": "nature",
    "shopping": "shopping",
    "games": "games",
    "coffee": "coffee",
    "books": "books",
    "nightlife": "nightlife",
    "wellness": "wellness",
}


def duration_for(candidate: PlaceCandidate, kind: PlanItemKind) -> int:
    if kind == "food":
        return 45 if candidate.category in ("cafe", "café") else 60
    if kind == "walk":
        return 45
    return DURATIONS.get(candidate.category, 60)


def interest_label(interest: Interest) -> str:
    return INTEREST_LABELS.get(interest, interest)


def build_why(candidate: PlaceCandidate, prefs: Preferences, kind: PlanItemKind) -> str:
    reasons: list[str] = []
    matched = [i for i in candidate.interests if i in prefs.interests]
    if matched:
        reasons.append(f"it lines up with your interest in {' & '.join(interest_label(i) for i in matched)}")
    if prefs.mood_tags and set(prefs.mood_tags) & {"relaxed", "cozy"}:
        if candidate.category in ("park", "garden", "cafe", "café", "library", "bookstore", "viewpoint"):
            reasons.append("it's low-key enough for a tired-but-fun mood")
    if set(prefs.mood_tags) & {"social"} and candidate.category in ("bar", "music venue", "nightclub", "arcade", "bowling"):
        reasons.append("it has a social, lively energy")
    if prefs.avoid_crowded and candidate.crowd == "low":
        reasons.append("it tends to stay uncrowded")
    if prefs.vegetarian and kind == "food" and candidate.vegetarian_friendly:
        reasons.append("it's vegetarian-friendly")
    if kind == "walk":
        reasons.append("it breaks up the day with some fresh air")
    if not reasons:
        if prefs.mood:
            reasons.append(f"it fits the {prefs.mood} mood you're after")
        else:
            reasons.append(f"it's a solid {candidate.category} pick in {prefs.city or 'the city'}")
    return f"Chosen because {', and '.join(reasons[:2])}."


def minutes_to_time(start_minutes: int) -> str:
    hours24 = (start_minutes // 60) % 24
    mins = start_minutes % 60
    suffix = "PM" if hours24 >= 12 else "AM"
    hours12 = 12 if hours24 % 12 == 0 else hours24 % 12
    return f"{hours12}:{mins:02d} {suffix}"


def _make_item(candidate: PlaceCandidate, kind: PlanItemKind, start_minutes: int, prefs: Preferences) -> PlanItem:
    cost = estimate_item_cost(candidate, prefs.currency)
    tags = [
        candidate.category,
        *candidate.interests,
        "crowded" if candidate.crowd == "high" else ("moderately-busy" if candidate.crowd == "medium" else "quiet"),
        "vegetarian-friendly" if candidate.vegetarian_friendly else "not-vegetarian",
        "live-data" if candidate.source == "osm" else "curated",
    ]
    description = candidate.category.capitalize() + (f" · {candidate.address}" if candidate.address else "")
    return PlanItem(
        id=candidate.id,
        kind=kind,
        title=candidate.name,
        description=description,
        location=prefs.city or "your city",
        start_time=minutes_to_time(start_minutes),
        duration_mins=duration_for(candidate, kind),
        cost=cost,
        tags=tags,
        why=build_why(candidate, prefs, kind),
        source=candidate.source,
        lat=candidate.lat,
        lon=candidate.lon,
        note=candidate.note,
    )


def _choose_activities(activities: list[PlaceCandidate], prefs: Preferences, count: int) -> list[PlaceCandidate]:
    """Greedily pick activities that cover as many *different* interests as possible.

    Without this the plan happily returns two parks in a row; covering interests
    gives a much more varied, believable day.
    """
    if count <= 0:
        return []
    wanted = set(prefs.interests)
    chosen: list[PlaceCandidate] = []
    remaining = list(activities)
    covered: set[Interest] = set()
    while remaining and len(chosen) < count:
        remaining.sort(key=lambda c: (-len((set(c.interests) & wanted) - covered), -c.score))
        best = remaining.pop(0)
        chosen.append(best)
        covered |= set(best.interests) & wanted
    return chosen


def _selection_for(hours: float) -> tuple[int, int, int]:
    """Return (activities, foods, start_minutes) sized to the time budget."""
    if hours >= 7:
        return 3, 2, 10 * 60
    if hours >= 5:
        return 2, 2, 11 * 60
    if hours >= 3.5:
        return 2, 1, 12 * 60
    return 1, 1, 13 * 60


def prune_plan(plan: Plan, drop_ids: list[str], prefs: Preferences) -> Plan:
    """Remove dropped items and re-time the remaining stops."""
    kept = [item for item in plan.items if item.id not in drop_ids]
    cursor = 10 * 60
    items: list[PlanItem] = []
    for item in kept:
        item = PlanItem(**{**item.__dict__, "start_time": minutes_to_time(cursor)})
        items.append(item)
        cursor += item.duration_mins + 20
    total_cost = sum(item.cost for item in items)
    return Plan(
        city=plan.city,
        headline=plan.headline,
        summary=plan.summary,
        items=items,
        total_cost=total_cost,
        budget=prefs.budget,
        currency=prefs.currency,
        within_budget=True if prefs.budget is None else total_cost <= prefs.budget,
        total_duration_mins=sum(i.duration_mins for i in items) + max(0, len(items) - 1) * 20,
        tradeoffs=list(plan.tradeoffs),
        warnings=list(plan.warnings),
        source=plan.source,
        generated_at=plan.generated_at,
    )


def generate_final_plan(
    activities: list[PlaceCandidate],
    foods: list[PlaceCandidate],
    prefs: Preferences,
    used_fallback: bool = False,
) -> Plan:
    activity_count, food_count, start_minutes = _selection_for(prefs.available_time_hours)

    chosen_activities = _choose_activities(activities, prefs, activity_count)
    chosen_foods = foods[:food_count]

    sequence: list[tuple[PlaceCandidate, PlanItemKind]] = []
    max_len = max(len(chosen_activities), len(chosen_foods))
    food_index = 0
    for i in range(max_len):
        if i < len(chosen_activities):
            sequence.append((chosen_activities[i], "activity"))
        if food_index < len(chosen_foods) and (i == 0 or i == max_len - 1 or len(sequence) % 2 == 0):
            sequence.append((chosen_foods[food_index], "food"))
            food_index += 1
    while food_index < len(chosen_foods):
        sequence.append((chosen_foods[food_index], "food"))
        food_index += 1

    items: list[PlanItem] = []
    cursor = start_minutes
    for candidate, kind in sequence:
        items.append(_make_item(candidate, kind, cursor, prefs))
        cursor += duration_for(candidate, kind) + 20

    total_cost = sum(item.cost for item in items)
    budget = prefs.budget
    within_budget = True if budget is None else total_cost <= budget

    tradeoffs: list[str] = []
    if budget is not None and total_cost > budget:
        priciest = max(items, key=lambda i: i.cost)
        tradeoffs.append(
            f"{priciest.title} is the biggest spend ({format_money(priciest.cost, prefs.currency)}). "
            f"It pushes you ~{format_money(total_cost - budget, prefs.currency)} over budget, but it's the "
            "strongest match for your mood. Drop it to stay comfortably within budget."
        )
    if used_fallback:
        tradeoffs.append(
            "Live place data was unavailable, so this uses our curated catalogue — names are illustrative rather than exact venues."
        )

    theme_bits: list[str] = []
    if set(prefs.mood_tags) & {"relaxed", "cozy"}:
        theme_bits.append("low-key")
    if "energetic" in prefs.mood_tags:
        theme_bits.append("high-energy")
    if "social" in prefs.mood_tags:
        theme_bits.append("social")
    if "creative" in prefs.mood_tags:
        theme_bits.append("creative")
    theme = (" ".join(theme_bits) + " ") if theme_bits else ""
    interest_words = ", ".join(interest_label(i) for i in prefs.interests[:3])

    headline = f"Your {theme}Saturday in {prefs.city or 'the city'}"
    source_note = "curated picks" if used_fallback else "live OpenStreetMap places"
    summary = (
        f"A {prefs.available_time_hours:g}h plan built around {interest_words or 'a bit of everything'} — "
        f"{len(items)} stops, {source_note}, roughly {format_money(total_cost, prefs.currency)} total"
        + (f" against your {format_money(budget, prefs.currency)} budget" if budget is not None else "")
        + "."
    )
    if prefs.constraints:
        summary += f" Kept to your constraints: {', '.join(prefs.constraints)}."

    source = "mock" if used_fallback else ("mixed" if any(i.source == "mock" for i in items) else "osm")

    return Plan(
        city=prefs.city or "your city",
        headline=headline,
        summary=summary,
        items=items,
        total_cost=total_cost,
        budget=budget,
        currency=prefs.currency,
        within_budget=within_budget,
        total_duration_mins=sum(i.duration_mins for i in items) + max(0, len(items) - 1) * 20,
        tradeoffs=tradeoffs,
        warnings=[],
        source=source,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
