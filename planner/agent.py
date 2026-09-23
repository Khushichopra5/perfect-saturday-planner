"""The agent orchestrator.

``run_agent`` is an async generator that yields trace events as it works, so the
web UI can stream "the agent is thinking". It is the only place that knows the
order of operations; each step is a separately testable tool.

Failure handling is built in at every step:

* unknown / unresolvable city  -> generic template plan
* live lookups fail or are thin -> curated catalogue
* over time budget             -> trim the least essential stop
* constraint violations        -> swap/drop and warn
* over budget                  -> keep it, but explain the trade-off
* unexpected exception         -> surfaced as an ``error`` event, never a crash
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Optional

from . import llm
from .data.mock_data import build_mock_activities, build_mock_food
from .models import PlaceCandidate, Preferences, TraceStep
from .tools.cost import estimate_cost, format_money, normalize_budget
from .tools.generate import generate_final_plan, prune_plan
from .tools.parse import detect_clarifications, parse_structured, parse_user_preferences
from .tools.places import (
    GeoLocation,
    geocode_city,
    get_activity_options,
    get_food_options,
    score_candidates,
)
from .tools.validate import validate_plan

_step_counter = 0


def _next_id() -> str:
    global _step_counter
    _step_counter += 1
    return f"step-{_step_counter}-{int(time.time() * 1000):x}"


def _trace(tool: str, status: str, message: str, ms: Optional[int] = None) -> dict[str, Any]:
    step = TraceStep(id=_next_id(), tool=tool, status=status, message=message, ms=ms)  # type: ignore[arg-type]
    return {"type": "trace", "step": step.to_dict()}


def _summarize_prefs(prefs: Preferences) -> str:
    bits = [
        f"city={prefs.city or 'unknown'}",
        f"budget={prefs.budget if prefs.budget is not None else 'unspecified'}",
        f"time={prefs.available_time_hours:g}h",
        f"interests=[{', '.join(prefs.interests)}]",
    ]
    if prefs.mood:
        bits.append(f"mood={prefs.mood}")
    if prefs.constraints:
        bits.append(f"constraints=[{', '.join(prefs.constraints)}]")
    return "Parsed " + " · ".join(bits)


async def _continue(
    prefs: Preferences, force: bool, started: float, simulate_outage: bool = False
) -> AsyncIterator[dict[str, Any]]:
    """Run everything after parsing, given normalised preferences."""
    questions = detect_clarifications(prefs)
    if questions and not force:
        yield _trace("parseUserPreferences", "info", "Input is a bit vague — asking before guessing.")
        yield {"type": "clarify", "questions": [q.to_dict() for q in questions]}
        yield {"type": "done"}
        return
    if questions and force:
        yield _trace("parseUserPreferences", "info", "Proceeding with sensible assumptions instead of clarifying.")
    for assumption in prefs.assumptions:
        yield _trace("parseUserPreferences", "info", assumption)

    # --- geocode ---------------------------------------------------------
    t = time.monotonic()
    yield _trace("geocodeCity", "running", f"Locating {prefs.city or 'your city'} on the map…")
    used_fallback = False
    geo: Optional[GeoLocation] = None
    if simulate_outage:
        used_fallback = True
        yield _trace(
            "geocodeCity",
            "fallback",
            "Live-data outage simulated — skipping map lookups and using the curated catalogue.",
            int((time.monotonic() - t) * 1000),
        )
    else:
        try:
            geo = await geocode_city(prefs.city) if prefs.city else None
        except Exception:  # noqa: BLE001 - any failure must degrade gracefully
            geo = None

        if not geo:
            used_fallback = True
            message = (
                f'Couldn\'t find "{prefs.city}" in the live map data — I\'ll build a sensible template plan instead.'
                if prefs.city
                else "No city given — building a generic template plan."
            )
            yield _trace("geocodeCity", "fallback", message, int((time.monotonic() - t) * 1000))
        else:
            via = "OpenStreetMap Nominatim" if geo.source == "osm" else "offline city index"
            yield _trace(
                "geocodeCity",
                "ok" if geo.source == "osm" else "fallback",
                f"Found {geo.name} ({geo.lat:.3f}, {geo.lon:.3f}) via {via}.",
                int((time.monotonic() - t) * 1000),
            )

    # Kick off both live lookups at once so the user waits for the slower one,
    # not their sum. Each still degrades to the curated catalogue on failure.
    live = geo is not None and geo.source == "osm"
    activity_task = (
        asyncio.create_task(get_activity_options(geo, prefs.interests, prefs.mood_tags, prefs.avoid_crowded))  # type: ignore[arg-type]
        if live
        else None
    )
    food_task = (
        asyncio.create_task(get_food_options(geo, prefs.vegetarian, prefs.avoid_crowded))  # type: ignore[arg-type]
        if live
        else None
    )

    # --- activities ------------------------------------------------------
    t = time.monotonic()
    yield _trace("getActivityOptions", "running", f"Searching for {', '.join(prefs.interests)} around {prefs.city or 'you'}…")
    activities: list[PlaceCandidate] = []
    if activity_task is not None:
        try:
            activities = (await activity_task).items
        except Exception:  # noqa: BLE001
            activities = []
    if len(activities) < 2:
        used_fallback = True
        live_count = len(activities)
        activities = score_candidates(
            build_mock_activities(prefs.city or "Your City"),
            prefs.interests,
            prefs.mood_tags,
            prefs.avoid_crowded,
        )
        if live_count == 0:
            message = f"No live options matched your interests — falling back to a broad curated mix ({len(activities)} options)."
        else:
            message = f"Only {live_count} live option(s) matched — topping up with the curated catalogue ({len(activities)} options)."
        yield _trace("getActivityOptions", "fallback", message, int((time.monotonic() - t) * 1000))
    else:
        yield _trace("getActivityOptions", "ok", f"Found {len(activities)} candidate activities via OpenStreetMap Overpass.", int((time.monotonic() - t) * 1000))

    # --- food ------------------------------------------------------------
    t = time.monotonic()
    yield _trace("getFoodOptions", "running", f"Looking for {'vegetarian-friendly ' if prefs.vegetarian else ''}food stops…")
    foods: list[PlaceCandidate] = []
    if food_task is not None:
        try:
            foods = (await food_task).items
        except Exception:  # noqa: BLE001
            foods = []
    if len(foods) < 1:
        used_fallback = True
        live_count = len(foods)
        foods = score_candidates(
            build_mock_food(prefs.city or "Your City"),
            ["food", "coffee"],
            [],
            prefs.avoid_crowded,
            prefs.vegetarian,
        )
        if live_count == 0:
            message = f"No live food options came back — using the curated food list instead ({len(foods)} options)."
        else:
            message = f"Only {live_count} live food option(s) — topping up with curated food options ({len(foods)} options)."
        yield _trace("getFoodOptions", "fallback", message, int((time.monotonic() - t) * 1000))
    else:
        yield _trace("getFoodOptions", "ok", f"Found {len(foods)} food options via OpenStreetMap Overpass.", int((time.monotonic() - t) * 1000))

    # --- draft -----------------------------------------------------------
    t = time.monotonic()
    yield _trace("generateFinalPlan", "running", "Drafting an itinerary and writing up why each stop fits…")
    origin = (geo.lat, geo.lon) if geo is not None and geo.source == "osm" else None
    draft = generate_final_plan(activities, foods, prefs, used_fallback, origin)
    yield _trace("generateFinalPlan", "ok", f"Drafted a {len(draft.items)}-stop plan.", int((time.monotonic() - t) * 1000))

    # --- cost ------------------------------------------------------------
    t = time.monotonic()
    yield _trace("estimateCost", "running", "Adding up tickets, food and coffee…")
    cost = estimate_cost([item.cost for item in draft.items], normalize_budget(prefs), prefs.currency)
    budget_note = f" vs {format_money(prefs.budget, prefs.currency)} budget" if prefs.budget is not None else ""
    yield _trace("estimateCost", "ok", f"Estimated total {format_money(cost.total, prefs.currency)}{budget_note}.", int((time.monotonic() - t) * 1000))

    # --- validate --------------------------------------------------------
    t = time.monotonic()
    yield _trace("validatePlan", "running", "Checking the plan against your time, budget and constraints…")
    validation = validate_plan(draft.items, prefs, cost.total)
    plan = draft
    if validation.drop_ids:
        plan = prune_plan(draft, validation.drop_ids, prefs)
        yield _trace("validatePlan", "fallback", f"Adjusted the plan to respect your constraints ({len(validation.drop_ids)} change(s)).", int((time.monotonic() - t) * 1000))
    else:
        yield _trace("validatePlan", "ok", "Plan fits your time, budget and constraints.", int((time.monotonic() - t) * 1000))

    plan.warnings = validation.warnings
    if validation.warnings:
        plan.tradeoffs.extend(validation.warnings)

    # --- optional LLM polish --------------------------------------------
    if llm.enabled():
        t = time.monotonic()
        yield _trace("narratePlan", "running", "Polishing the write-up with a language model…")
        plan = await llm.narrate(plan, prefs)
        yield _trace("narratePlan", "ok", "Write-up polished.", int((time.monotonic() - t) * 1000))

    yield _trace("generateFinalPlan", "ok", f"Final plan ready in {(time.monotonic() - started):.1f}s.")
    yield {"type": "plan", "plan": plan.to_dict()}
    yield {"type": "done"}


async def run_agent(
    input_text: str, force: bool = False, simulate_outage: bool = False
) -> AsyncIterator[dict[str, Any]]:
    """Parse free text, then run the planner."""
    started = time.monotonic()
    t = time.monotonic()
    yield _trace("parseUserPreferences", "running", "Reading your request and pulling out the important bits…")
    prefs = parse_user_preferences(input_text)
    yield _trace("parseUserPreferences", "ok", _summarize_prefs(prefs), int((time.monotonic() - t) * 1000))
    async for event in _continue(prefs, force, started, simulate_outage):
        yield event


async def run_agent_from_prefs(
    prefs: Preferences, force: bool = False, simulate_outage: bool = False
) -> AsyncIterator[dict[str, Any]]:
    """Run the planner from an already-structured preferences object."""
    started = time.monotonic()
    yield _trace("parseUserPreferences", "ok", _summarize_prefs(prefs))
    async for event in _continue(prefs, force, started, simulate_outage):
        yield event


async def run_agent_safe(
    input_text: str, force: bool = False, simulate_outage: bool = False
) -> AsyncIterator[dict[str, Any]]:
    """Wrap :func:`run_agent` so an unexpected error becomes a streamed event."""
    try:
        async for event in run_agent(input_text, force, simulate_outage):
            yield event
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"The agent hit an unexpected error: {exc}"}
        yield {"type": "done"}


def parse_payload(payload: dict[str, Any]) -> tuple[Optional[str], Optional[Preferences]]:
    """Decide whether a request body is free text or the structured brief shape."""
    text = payload.get("input")
    if isinstance(text, str) and text.strip():
        return text.strip(), None
    structured_keys = {"city", "budget", "available_time", "mood", "interests", "constraints"}
    if structured_keys & set(payload.keys()):
        return None, parse_structured(payload)
    return None, None
