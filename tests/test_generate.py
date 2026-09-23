from planner.models import PlaceCandidate, Plan, PlanItem, Preferences
from planner.tools.generate import (
    _choose_activities,
    build_tradeoffs,
    generate_final_plan,
    prune_plan,
)
from planner.tools.parse import parse_user_preferences
from planner.tools.places import score_candidates


def rank(activities, prefs, vegetarian=False):
    return score_candidates(activities, prefs.interests, prefs.mood_tags, prefs.avoid_crowded, vegetarian)


def make_item(item_id, title, cost, tags=None, kind="activity", distance_km=None):
    return PlanItem(
        id=item_id,
        kind=kind,
        title=title,
        description="",
        location="Testville",
        start_time="10:00 AM",
        duration_mins=60,
        cost=cost,
        tags=tags or [],
        why="",
        source="mock",
        distance_km=distance_km,
    )


def make_plan(items, total_cost, budget=None, swaps=None):
    return Plan(
        city="Testville",
        headline="",
        summary="",
        items=items,
        total_cost=total_cost,
        currency="INR",
        total_duration_mins=sum(i.duration_mins + i.travel_mins for i in items),
        budget=budget,
        within_budget=True if budget is None else total_cost <= budget,
        swaps=swaps or [],
    )


def test_generates_a_timed_plan_with_reasons(bangalore_prefs, activities, foods):
    plan = generate_final_plan(
        rank(activities, bangalore_prefs),
        rank(foods, bangalore_prefs, vegetarian=True),
        bangalore_prefs,
    )
    assert plan.items
    assert all(item.why for item in plan.items)
    assert all(item.start_time for item in plan.items)
    assert plan.total_cost == sum(item.cost for item in plan.items)
    assert plan.headline


def test_activity_choice_covers_multiple_interests(bangalore_prefs, activities):
    chosen = _choose_activities(rank(activities, bangalore_prefs), bangalore_prefs, 2)
    covered = set()
    for candidate in chosen:
        covered |= set(candidate.interests) & set(bangalore_prefs.interests)
    assert len(covered) >= 2


def test_over_budget_produces_a_tradeoff(bangalore_prefs, activities, foods):
    bangalore_prefs.budget = 1
    plan = generate_final_plan(
        rank(activities, bangalore_prefs),
        rank(foods, bangalore_prefs, vegetarian=True),
        bangalore_prefs,
    )
    assert plan.within_budget is False
    assert plan.tradeoffs


def test_prune_plan_removes_and_retimes(bangalore_prefs, activities, foods):
    plan = generate_final_plan(
        rank(activities, bangalore_prefs),
        rank(foods, bangalore_prefs, vegetarian=True),
        bangalore_prefs,
    )
    drop = plan.items[0].id
    pruned = prune_plan(plan, [drop], bangalore_prefs)
    assert drop not in [i.id for i in pruned.items]
    assert len(pruned.items) == len(plan.items) - 1
    assert pruned.total_cost == sum(i.cost for i in pruned.items)


def test_real_coordinates_produce_travel_and_distance():
    prefs = parse_user_preferences("Bangalore, ₹2000, 4 hours, relaxed, food and walks")
    a1 = PlaceCandidate(id="a1", name="Park A", category="park", interests=["walks"], source="osm", lat=12.9716, lon=77.5946, crowd="low")
    a2 = PlaceCandidate(id="a2", name="Museum B", category="museum", interests=["art"], source="osm", lat=12.9850, lon=77.6050, crowd="low")
    f1 = PlaceCandidate(id="f1", name="Cafe C", category="cafe", interests=["food"], source="osm", lat=12.9760, lon=77.5960, crowd="low", vegetarian_friendly=True)
    plan = generate_final_plan([a1, a2], [f1], prefs, origin=(12.9716, 77.5946))
    assert any(item.travel_mins > 0 for item in plan.items)
    assert all(item.distance_km is not None for item in plan.items)
    assert plan.total_duration_mins == sum(i.duration_mins for i in plan.items) + sum(i.travel_mins for i in plan.items)


def test_closed_place_is_swapped_out():
    prefs = parse_user_preferences("Bangalore, ₹2000, 4 hours, relaxed, food and walks")
    closed = PlaceCandidate(
        id="c", name="Closed Museum", category="museum", interests=["walks"], source="osm",
        lat=12.97, lon=77.59, crowd="low", tags={"opening_hours": "Mo-Fr 09:00-17:00"},
    )
    open_one = PlaceCandidate(id="o1", name="Open Park", category="park", interests=["walks"], source="osm", lat=12.98, lon=77.60, crowd="low")
    open_two = PlaceCandidate(id="o2", name="Another Park", category="park", interests=["walks"], source="osm", lat=12.99, lon=77.61, crowd="low")
    f1 = PlaceCandidate(id="f1", name="Cafe", category="cafe", interests=["food"], source="osm", lat=12.975, lon=77.595, crowd="low", vegetarian_friendly=True)

    plan = generate_final_plan([closed, open_one, open_two], [f1], prefs)
    assert "Closed Museum" not in [item.title for item in plan.items]
    assert any("Swapped" in trade for trade in plan.tradeoffs)


def test_short_window_produces_smaller_plan(bangalore_prefs, activities, foods):
    bangalore_prefs.available_time_hours = 2
    plan = generate_final_plan(
        rank(activities, bangalore_prefs),
        rank(foods, bangalore_prefs, vegetarian=True),
        bangalore_prefs,
    )
    assert len(plan.items) == 2


def test_build_tradeoffs_notes_over_budget_priciest_item():
    prefs = Preferences(city="Testville", budget=100, currency="INR", interests=["art"])
    plan = make_plan([make_item("a", "Pricey Museum", 800, tags=["museum", "art"])], 800, budget=100)
    trades = build_tradeoffs(plan, prefs, [], [], False)
    assert any("over budget" in t for t in trades)
    assert any("Pricey Museum" in t for t in trades)


def test_build_tradeoffs_skips_high_crowd_candidate_when_avoiding_crowds():
    prefs = Preferences(city="Testville", currency="INR", interests=["walks"], avoid_crowded=True)
    busy = PlaceCandidate(
        id="busy", name="Busy Market", category="market", interests=["shopping"], source="osm", crowd="high"
    )
    calm = PlaceCandidate(
        id="calm", name="Quiet Park", category="park", interests=["walks"], source="osm", crowd="low"
    )
    plan = make_plan([make_item("calm", "Quiet Park", 0, tags=["park", "walks", "quiet"])], 0)
    trades = build_tradeoffs(plan, prefs, [busy, calm], [], False)
    assert any(t.startswith("Skipped Busy Market") for t in trades)


def test_build_tradeoffs_does_not_call_available_interest_uncovered():
    prefs = Preferences(city="Testville", currency="INR", interests=["walks", "music"])
    trimmed = PlaceCandidate(
        id="music", name="Music Room", category="music venue", interests=["music"], source="osm", crowd="low"
    )
    plan = make_plan([make_item("park", "Quiet Park", 0, tags=["park", "walks", "quiet"])], 0)
    trades = build_tradeoffs(plan, prefs, [trimmed], [], False)
    assert not any("No strong" in t for t in trades)


def test_build_tradeoffs_starts_from_plan_swaps():
    prefs = Preferences(city="Testville", currency="INR")
    plan = make_plan([], 0, swaps=["Swapped A → B: A was closed."])
    trades = build_tradeoffs(plan, prefs, [], [], False)
    assert trades[0] == "Swapped A → B: A was closed."


def test_tradeoffs_refresh_after_pruning_reference_kept_item():
    prefs = Preferences(city="Testville", budget=100, currency="INR", interests=["art"])
    pricey = make_item("pricey", "Pricey Museum", 800, tags=["museum", "art"])
    cheap = make_item("cheap", "Cheap Park", 200, tags=["park", "art"])
    plan = make_plan([pricey, cheap], 1000, budget=100)

    pruned = prune_plan(plan, ["pricey"], prefs)
    assert [i.id for i in pruned.items] == ["cheap"]
    assert pruned.total_cost == 200

    trades = build_tradeoffs(pruned, prefs, [], [], False)
    note = next(t for t in trades if "biggest spend" in t)
    assert "Cheap Park" in note
    assert "Pricey Museum" not in note
