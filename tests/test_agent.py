import planner.agent as agent_mod
from planner.agent import (
    parse_payload,
    run_agent,
    run_agent_from_prefs,
    run_agent_from_prefs_safe,
)
from planner.tools.parse import parse_user_preferences

EXPECTED_TOOLS = {
    "parseUserPreferences",
    "geocodeCity",
    "getActivityOptions",
    "getFoodOptions",
    "estimateCost",
    "validatePlan",
    "generateFinalPlan",
}


async def collect(generator):
    return [event async for event in generator]


async def test_offline_agent_produces_a_full_plan():
    events = await collect(
        run_agent(
            "Bangalore, ₹2000, 4 hours, relaxed, food music walks, vegetarian, avoid crowded places",
            force=True,
        )
    )
    types = [e["type"] for e in events]
    assert types[-1] == "done"
    assert "plan" in types

    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["items"]
    assert plan["total_cost"] == sum(i["cost"] for i in plan["items"])

    tools = {e["step"]["tool"] for e in events if e["type"] == "trace"}
    assert EXPECTED_TOOLS <= tools


async def test_vague_input_asks_clarifying_questions():
    events = await collect(run_agent("plan my saturday"))
    assert any(e["type"] == "clarify" for e in events)
    assert not any(e["type"] == "plan" for e in events)


async def test_force_skips_clarifying_and_still_plans():
    events = await collect(run_agent("plan my saturday", force=True))
    assert not any(e["type"] == "clarify" for e in events)
    assert any(e["type"] == "plan" for e in events)


async def test_unknown_city_degrades_gracefully():
    events = await collect(run_agent("I'm in Zzyzxville with 4 hours and food", force=True))
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["source"] == "mock"
    assert any(e["type"] == "trace" and e["step"]["status"] == "fallback" for e in events)


async def test_run_agent_from_prefs():
    prefs = parse_user_preferences("Bangalore, ₹2000, 4 hours, relaxed, food and walks")
    events = await collect(run_agent_from_prefs(prefs))
    assert any(e["type"] == "plan" for e in events)


async def test_vegetarian_constraint_is_respected():
    events = await collect(
        run_agent("Bangalore, ₹2000, 4 hours, food and walks, vegetarian", force=True)
    )
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    food_items = [i for i in plan["items"] if i["kind"] == "food"]
    assert food_items
    assert all("not-vegetarian" not in i["tags"] for i in food_items)


async def test_simulated_outage_uses_curated_fallback():
    events = await collect(
        run_agent("Bangalore, ₹2000, 4 hours, relaxed, food and walks", force=True, simulate_outage=True)
    )
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["source"] == "mock"
    assert any(
        e["type"] == "trace" and "simulated" in e["step"]["message"].lower() for e in events
    )


async def test_plan_includes_travel_and_why():
    events = await collect(
        run_agent("Bangalore, ₹2000, 4 hours, relaxed, food music walks", force=True)
    )
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert all("why" in item and item["why"] for item in plan["items"])
    assert all("travel_mins" in item for item in plan["items"])


def test_parse_payload_free_text():
    text, prefs = parse_payload({"input": "hello"})
    assert text == "hello"
    assert prefs is None


def test_parse_payload_structured():
    text, prefs = parse_payload({"city": "Bangalore", "budget": 2000, "interests": ["food"]})
    assert text is None
    assert prefs is not None
    assert prefs.city == "Bangalore"


def test_parse_payload_empty():
    assert parse_payload({}) == (None, None)


async def test_run_agent_from_prefs_safe_surfaces_errors(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(agent_mod, "generate_final_plan", boom)
    prefs = parse_user_preferences("Bangalore, ₹2000, 4 hours, relaxed, food and walks")

    events = await collect(run_agent_from_prefs_safe(prefs, force=True))
    types = [e["type"] for e in events]

    assert types[-1] == "done"
    assert "error" in types
    error_index = types.index("error")
    assert events[error_index - 1]["type"] == "trace"
    assert events[error_index - 1]["step"]["status"] == "error"
