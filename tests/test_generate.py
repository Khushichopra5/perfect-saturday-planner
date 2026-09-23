from planner.models import PlaceCandidate
from planner.tools.generate import _choose_activities, generate_final_plan, prune_plan
from planner.tools.parse import parse_user_preferences
from planner.tools.places import score_candidates


def rank(activities, prefs, vegetarian=False):
    return score_candidates(activities, prefs.interests, prefs.mood_tags, prefs.avoid_crowded, vegetarian)


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
