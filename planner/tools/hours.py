"""Tool: opening-hours awareness.

OpenStreetMap sometimes carries an ``opening_hours`` tag. We parse the common
subset so the agent can avoid suggesting a museum that's shut on a Saturday
morning. Anything we can't confidently parse returns ``"unknown"`` — we never
claim a place is closed when we're unsure.
"""

from __future__ import annotations

import re

DAY_ALIASES = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}
DAY_NAMES = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")
_DAY_TOKEN_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?(,[a-z]{2}(-[a-z]{2})?)*$")


def _parse_days(token: str) -> set[int]:
    days: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if "-" in part:
            start, _, end = part.partition("-")
            if start in DAY_ALIASES and end in DAY_ALIASES:
                i = DAY_ALIASES[start]
                while True:
                    days.add(i)
                    if i == DAY_ALIASES[end]:
                        break
                    i = (i + 1) % 7
        elif part in DAY_ALIASES:
            days.add(DAY_ALIASES[part])
    return days


def _in_range(minutes: int, start: int, end: int) -> bool:
    if end >= start:
        return start <= minutes <= end
    # crosses midnight, e.g. 22:00-02:00
    return minutes >= start or minutes <= end


def opening_status(opening_hours: str | None, weekday: int, minutes: int) -> str:
    """Return ``"open"``, ``"closed"`` or ``"unknown"``.

    ``weekday`` is 0=Monday … 6=Sunday; ``minutes`` is minutes since midnight.
    """
    if not opening_hours:
        return "unknown"
    value = opening_hours.strip().lower()
    if value in ("24/7", "24/7 open"):
        return "open"
    if not value:
        return "unknown"

    rules = [r.strip() for r in value.split(";") if r.strip()]
    matched_day = False
    open_any = False

    for rule in rules:
        days: set[int] | None = None
        off = False
        ranges: list[tuple[int, int]] = []
        unsupported = False

        for token in rule.split():
            if token in ("off", "closed"):
                off = True
            elif token == "24/7":
                return "open"
            elif token.startswith("ph") or token.startswith("public"):
                continue
            elif token.startswith("sunrise") or token.startswith("sunset") or token == "dawn" or token == "dusk":
                unsupported = True
            elif _TIME_RE.fullmatch(token):
                m = _TIME_RE.fullmatch(token)
                ranges.append((int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))))
            elif _DAY_TOKEN_RE.fullmatch(token):
                parsed = _parse_days(token)
                if parsed:
                    days = parsed

        if unsupported:
            return "unknown"
        if days is not None and weekday not in days:
            continue

        matched_day = True
        if off:
            continue
        if not ranges:
            open_any = True
        elif any(_in_range(minutes, start, end) for start, end in ranges):
            open_any = True

    if not matched_day:
        return "closed"
    return "open" if open_any else "closed"
