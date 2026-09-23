from planner.tools.generate import _choose_activities, generate_final_plan, prune_plan
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


def test_short_window_produces_smaller_plan(bangalore_prefs, activities, foods):
    bangalore_prefs.available_time_hours = 2
    plan = generate_final_plan(
        rank(activities, bangalore_prefs),
        rank(foods, bangalore_prefs, vegetarian=True),
        bangalore_prefs,
    )
    assert len(plan.items) == 2
