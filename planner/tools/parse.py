"""Tool: parseUserPreferences.

Turns either a structured JSON payload (the shape in the assignment brief) or a
free-text sentence into a normalised :class:`Preferences` object. Also surfaces
the assumptions it had to make so the agent can be honest about them, and
decides whether the request is vague enough to warrant clarifying questions.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..data.mock_data import find_known_city
from ..models import ClarifyingQuestion, Currency, Interest, MoodTag, Preferences
from .cost import default_budget, format_money

INTEREST_KEYWORDS: dict[Interest, tuple[str, ...]] = {
    "food": ("food", "foodie", "eat", "eating", "brunch", "lunch", "dinner", "cuisine", "restaurant", "street food", "snack"),
    "music": ("music", "gig", "concert", "live band", "dj", "acoustic", "karaoke"),
    "walks": ("walk", "walking", "stroll", "strolling", "promenade", "trek", "hike"),
    "art": ("art", "museum", "gallery", "painting", "exhibition", "pottery", "craft", "design"),
    "history": ("history", "historic", "heritage", "monument", "fort", "palace", "temple", "old city"),
    "nature": ("nature", "outdoor", "outdoors", "garden", "lake", "park", "green", "botanical", "beach", "sunset"),
    "shopping": ("shop", "shopping", "market", "mall", "bazaar", "vintage", "thrift"),
    "games": ("game", "games", "gaming", "arcade", "bowling", "board game", "escape room", "mini golf", "cinema", "movie"),
    "coffee": ("coffee", "cafe", "café", "espresso", "bakery"),
    "books": ("book", "books", "reading", "library", "bookstore", "poetry"),
    "nightlife": ("nightlife", "bar", "pub", "club", "drinks", "cocktail", "beer", "night out"),
    "wellness": ("spa", "wellness", "massage", "yoga", "meditation", "sauna"),
}

MOOD_KEYWORDS: dict[MoodTag, tuple[str, ...]] = {
    "relaxed": ("tired", "relax", "relaxed", "chill", "calm", "low-key", "low key", "lazy", "slow", "unwind", "peaceful", "quiet"),
    "energetic": ("energetic", "active", "adventure", "adventurous", "hike", "run", "sport", "pumped", "high energy"),
    "social": ("social", "friends", "people", "meet", "group", "party"),
    "cozy": ("cozy", "cosy", "comfort", "warm", "intimate", "homey"),
    "adventurous": ("adventure", "adventurous", "new", "explore", "try something", "spontaneous", "thrill"),
    "romantic": ("romantic", "date", "partner", "couple", "anniversary", "candle"),
    "creative": ("creative", "make", "paint", "craft", "write", "pottery", "photography", "artistic"),
    "playful": ("fun", "playful", "play", "silly", "games", "joy", "cheerful", "happy"),
}

ALL_INTERESTS: tuple[Interest, ...] = tuple(INTEREST_KEYWORDS.keys())


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9₹$.,\-\s]", " ", (text or "").lower())
    return " " + re.sub(r"\s+", " ", cleaned).strip() + " "


def _extract_interests(text: str) -> list[Interest]:
    found: list[Interest] = []
    for interest, keywords in INTEREST_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}(s|es|ing)?\b", text):
                found.append(interest)
                break
    return found


def _extract_mood_tags(text: str) -> list[MoodTag]:
    found: list[MoodTag] = []
    for tag, keywords in MOOD_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(tag)
    return found


def _extract_city(raw: str, text: str) -> Optional[str]:
    known = find_known_city(text)
    if known:
        return known.name
    match = re.search(r"\b(?:in|at|around|near|from)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", raw)
    if match:
        return match.group(1).strip()
    trimmed = raw.strip()
    if re.fullmatch(r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?", trimmed):
        return trimmed
    return None


_CURRENCY_PATTERNS: tuple[tuple[str, Currency], ...] = (
    (r"₹|\brs\.?\b|\binr\b|rupee", "INR"),
    (r"\$|\busd\b|dollar", "USD"),
    (r"€|\beur\b|euro", "EUR"),
    (r"£|\bgbp\b|pound", "GBP"),
    (r"¥|\bjpy\b|yen", "JPY"),
    (r"\bsgd\b|s\$", "SGD"),
    (r"\baed\b|dirham", "AED"),
    (r"\baud\b|a\$", "AUD"),
)


def _detect_currency(text: str) -> Optional[Currency]:
    for pattern, currency in _CURRENCY_PATTERNS:
        if re.search(pattern, text, re.I):
            return currency
    return None


def _extract_budget(text: str) -> tuple[Optional[int], Optional[Currency]]:
    currency = _detect_currency(text)
    # The number must not be a quantity of time/people ("4 hours", "2 people").
    match = re.search(
        r"(?:₹|\$|€|£|¥|budget(?:\s+of)?|under|within|about|around|approx\.?)?\s*"
        r"([\d][\d,]*\.?\d*)\s*(k|thousand)?"
        r"(?!\s*(?:hours?|hrs?|h|min|mins?|minutes?|days?|people|ppl|adults?|kids?|stops?)\b)",
        text,
        re.I,
    )
    if not match:
        return None, currency
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, currency
    if match.group(2):
        value *= 1000
    if value <= 0:
        return None, currency
    return int(round(value)), currency


def _extract_time_hours(text: str) -> Optional[float]:
    rng = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", text)
    if rng:
        return max(float(rng.group(1)), float(rng.group(2)))
    single = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", text)
    if single:
        return float(single.group(1))
    if re.search(r"\b(full day|whole day|all day)\b", text):
        return 8.0
    if re.search(r"\b(half day)\b", text):
        return 4.0
    if re.search(r"\b(evening|night)\b", text):
        return 3.0
    if re.search(r"\b(afternoon|morning)\b", text):
        return 4.0
    return None


def _extract_constraints(text: str) -> tuple[list[str], bool, bool]:
    constraints: list[str] = []
    vegetarian = bool(re.search(r"\b(vegetarian|veg only|no meat|meatless|vegan|pure veg|jain)\b", text))
    if vegetarian:
        constraints.append("vegan" if re.search(r"\bvegan\b", text) else "vegetarian")
    avoid_crowded = bool(re.search(r"\b(avoid crowd|crowded|quiet|peaceful|not too busy|less busy|calm|no crowd)\b", text))
    if avoid_crowded:
        constraints.append("avoid crowded places")
    if re.search(r"\bno alcohol|sober|no drinks\b", text):
        constraints.append("no alcohol")
    if re.search(r"\bwheelchair|accessible|mobility\b", text):
        constraints.append("accessible")
    if re.search(r"\bpet|dog\b", text):
        constraints.append("pet friendly")
    return constraints, vegetarian, avoid_crowded


def parse_user_preferences(text: str) -> Preferences:
    """Parse a free-text description into :class:`Preferences`."""
    raw = text or ""
    normalized = _normalize(raw)
    assumptions: list[str] = []

    city = _extract_city(raw, normalized)

    budget, detected_currency = _extract_budget(normalized)
    known_city = find_known_city(city) if city else None
    currency: Currency = detected_currency or (known_city.currency if known_city else "INR")  # type: ignore[assignment]
    no_limit = bool(re.search(r"\b(no limit|unlimited|no budget|any budget|money is no object|whatever it costs)\b", normalized))
    budget_answered = budget is not None or no_limit
    if budget is None:
        assumptions.append(
            f"No budget given — assumed a comfortable {format_money(default_budget(currency), currency)} range."
        )

    time_hours = _extract_time_hours(normalized)
    if time_hours is None:
        time_hours = 4.0
        assumptions.append("No time given — assumed 4 hours.")

    mood_tags = _extract_mood_tags(normalized)
    mood = ", ".join(mood_tags) if mood_tags else None

    interests = _extract_interests(normalized)
    interests_explicit = bool(interests)
    if not interests:
        interests = ["food", "walks", "art"]
        assumptions.append("No interests given — assumed a mix of food, walks and art.")

    constraints, vegetarian, avoid_crowded = _extract_constraints(normalized)

    return Preferences(
        raw=raw,
        city=city,
        budget=budget,
        currency=currency,
        available_time_hours=time_hours,
        mood=mood,
        mood_tags=mood_tags,
        interests=interests,
        constraints=constraints,
        vegetarian=vegetarian,
        avoid_crowded=avoid_crowded,
        assumptions=assumptions,
        budget_answered=budget_answered,
        interests_explicit=interests_explicit,
    )


def parse_structured(payload: dict[str, Any]) -> Preferences:
    """Parse the structured JSON shape from the assignment brief."""
    assumptions: list[str] = []

    city = payload.get("city")
    if isinstance(city, str):
        known = find_known_city(city)
        city = known.name if known else city.strip() or None
    else:
        city = None

    budget_raw = payload.get("budget")
    budget: Optional[int] = None
    if isinstance(budget_raw, (int, float)) and budget_raw > 0:
        budget = int(budget_raw)
    elif isinstance(budget_raw, str):
        budget, _ = _extract_budget(_normalize(budget_raw))
    if budget is None:
        assumptions.append("No budget given — assumed a comfortable ₹2,000 / $40 range.")

    time_raw = payload.get("available_time")
    time_hours: Optional[float] = None
    if isinstance(time_raw, (int, float)) and time_raw > 0:
        time_hours = float(time_raw)
    elif isinstance(time_raw, str):
        time_hours = _extract_time_hours(_normalize(time_raw))
    if time_hours is None:
        time_hours = 4.0
        assumptions.append("No time given — assumed 4 hours.")

    mood_raw = payload.get("mood")
    mood_tags: list[MoodTag] = _extract_mood_tags(_normalize(mood_raw)) if isinstance(mood_raw, str) else []
    mood = mood_raw if isinstance(mood_raw, str) and mood_raw.strip() else (", ".join(mood_tags) or None)

    interests_raw = payload.get("interests") or []
    interests: list[Interest] = []
    if isinstance(interests_raw, str):
        interests_raw = [p.strip() for p in re.split(r"[,;]", interests_raw)]
    for item in interests_raw:
        if not isinstance(item, str):
            continue
        key = item.strip().lower().replace(" ", "_")
        aliases = {"walking": "walks", "art_museums": "art", "live_music": "music"}
        key = aliases.get(key, key)
        if key in INTEREST_KEYWORDS and key not in interests:
            interests.append(key)  # type: ignore[arg-type]
    interests_explicit = bool(interests)
    if not interests:
        interests = ["food", "walks", "art"]
        assumptions.append("No interests given — assumed a mix of food, walks and art.")

    constraints_raw = payload.get("constraints") or []
    if isinstance(constraints_raw, str):
        constraints_raw = [p.strip() for p in re.split(r"[,;]", constraints_raw)]
    constraints_text = " ".join(c for c in constraints_raw if isinstance(c, str))
    constraints, vegetarian, avoid_crowded = _extract_constraints(_normalize(constraints_text))

    known_city = find_known_city(city) if city else None
    detected_currency = _detect_currency(_normalize(str(payload)))
    currency: Currency = detected_currency or (known_city.currency if known_city else "INR")  # type: ignore[assignment]
    if budget is None:
        assumptions.append(
            f"No budget given — assumed a comfortable {format_money(default_budget(currency), currency)} range."
        )

    return Preferences(
        raw=str(payload),
        city=city,
        budget=budget,
        currency=currency,
        available_time_hours=time_hours,
        mood=mood,
        mood_tags=mood_tags,
        interests=interests,
        constraints=constraints,
        vegetarian=vegetarian,
        avoid_crowded=avoid_crowded,
        assumptions=assumptions,
        budget_answered=budget is not None,
        interests_explicit=interests_explicit,
    )


def detect_clarifications(prefs: Preferences) -> list[ClarifyingQuestion]:
    """Ask at most two questions, and only when the request is genuinely vague.

    Ordered by importance: city, then budget, then mood. "No limit" answers are
    recognised as a real budget answer so we never re-ask in a loop.
    """
    questions: list[ClarifyingQuestion] = []
    if not prefs.city:
        questions.append(
            ClarifyingQuestion(
                question="Which city are you planning your Saturday in?",
                field="city",
                options=["Bangalore", "Mumbai", "Delhi", "New York", "London"],
            )
        )
    if not prefs.budget_answered:
        questions.append(
            ClarifyingQuestion(
                question="Roughly what's your budget for the day?",
                field="budget",
                options=["Under ₹1,000", "Around ₹2,000", "₹3,000–5,000", "₹5,000+"],
            )
        )
    if not prefs.mood and not prefs.interests_explicit:
        questions.append(
            ClarifyingQuestion(
                question="What kind of mood are you in?",
                field="mood",
                options=["Tired but want something fun", "Energetic and outdoorsy", "Chill and cozy", "Social with friends"],
            )
        )
    return questions[:2]
