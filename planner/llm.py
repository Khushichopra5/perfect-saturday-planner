"""Optional LLM narrator.

The planner is deliberately *not* a single giant prompt — the itinerary is built
by deterministic tools so it always works and is easy to test. This module is a
thin, optional layer that uses an OpenAI-compatible chat API to make the prose
warmer and more personal.

It is strictly best-effort: if there is no API key, the call fails, or the model
returns something malformed, we silently keep the deterministic copy.
"""

from __future__ import annotations

import json
import os

import httpx

from .models import Plan, Preferences

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


def enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _system_prompt() -> str:
    return (
        "You are a warm, concise local guide who plans great Saturdays. "
        "You are given a JSON itinerary that is already decided. Do not add or remove stops, "
        "do not change times or costs. Only rewrite the human-facing text to be specific and personal. "
        "Reply with JSON only, matching this shape: "
        '{"headline": str, "summary": str, "why": {"<item id>": str}}. '
        "Each `why` must be one short sentence explaining how that stop fits the user's mood, "
        "interests or constraints. Never invent facts not present in the itinerary."
    )


async def narrate(plan: Plan, prefs: Preferences, timeout: float = 20.0) -> Plan:
    """Best-effort rewrite of the plan's prose. Returns ``plan`` unchanged on any issue."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return plan

    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

    payload = {
        "city": plan.city,
        "currency": plan.currency,
        "budget": plan.budget,
        "within_budget": plan.within_budget,
        "mood": prefs.mood,
        "interests": prefs.interests,
        "constraints": prefs.constraints,
        "headline": plan.headline,
        "summary": plan.summary,
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "kind": item.kind,
                "start_time": item.start_time,
                "cost": item.cost,
                "why": item.why,
            }
            for item in plan.items
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.6,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
            )
        if resp.status_code != 200:
            return plan
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return plan

    headline = data.get("headline")
    if isinstance(headline, str) and headline.strip():
        plan.headline = headline.strip()
    summary = data.get("summary")
    if isinstance(summary, str) and summary.strip():
        plan.summary = summary.strip()
    why_map = data.get("why")
    if isinstance(why_map, dict):
        for item in plan.items:
            replacement = why_map.get(item.id)
            if isinstance(replacement, str) and replacement.strip():
                item.why = replacement.strip()
    return plan
