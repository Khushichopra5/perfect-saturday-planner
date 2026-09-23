from planner.models import PlanItem
from planner.tools.validate import plan_duration_mins, validate_plan


def make_item(item_id, kind, duration, cost=0, tags=None, travel_mins=0):
    return PlanItem(
        id=item_id,
        kind=kind,
        title=item_id,
        description="",
        location="X",
        start_time="10:00 AM",
        duration_mins=duration,
        cost=cost,
        tags=tags or [],
        why="",
        source="mock",
        travel_mins=travel_mins,
    )


def test_plan_duration_includes_travel_time():
    items = [make_item("a", "activity", 60), make_item("b", "food", 60, travel_mins=20)]
    assert plan_duration_mins(items) == 140


def test_drops_activity_when_over_time(bangalore_prefs):
    bangalore_prefs.available_time_hours = 1
    items = [make_item("a", "activity", 60), make_item("b", "activity", 60), make_item("f", "food", 45)]
    result = validate_plan(items, bangalore_prefs, 0)
    assert result.drop_ids
    assert any("Trimmed" in w for w in result.warnings)


def test_vegetarian_drops_non_veg_food(bangalore_prefs):
    items = [make_item("f", "food", 60, tags=["not-vegetarian"])]
    result = validate_plan(items, bangalore_prefs, 0)
    assert "f" in result.drop_ids
    assert any("vegetarian" in w.lower() for w in result.warnings)


def test_avoid_crowded_emits_warning(bangalore_prefs):
    items = [make_item("a", "activity", 30, tags=["crowded"])]
    result = validate_plan(items, bangalore_prefs, 0)
    assert any("crowd" in w.lower() for w in result.warnings)


def test_budget_is_handled_by_tradeoffs_not_validation(bangalore_prefs):
    # Budget is explained once, in generate.build_tradeoffs(), not here.
    items = [make_item("a", "activity", 30, cost=5000)]
    result = validate_plan(items, bangalore_prefs, 5000)
    assert not any("budget" in w.lower() for w in result.warnings)


def test_clean_plan_has_no_warnings(bangalore_prefs):
    bangalore_prefs.vegetarian = False
    bangalore_prefs.avoid_crowded = False
    items = [make_item("a", "activity", 30, tags=["quiet"]), make_item("f", "food", 30, tags=["vegetarian-friendly"])]
    result = validate_plan(items, bangalore_prefs, 0)
    assert result.warnings == []
    assert result.drop_ids == []
