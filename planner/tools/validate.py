"""Tool: validatePlan.

The agent's self-check. It compares the draft itinerary against the user's time
window, budget and constraints and returns warnings plus a list of items that
should be dropped (which the agent then re-plans around).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import PlanItem, Preferences

TRAVEL_BUFFER_MINS = 20


@dataclass
class ValidationResult:
    warnings: list[str] = field(default_factory=list)
    drop_ids: list[str] = field(default_factory=list)
    travel_buffer_mins: int = 0

    def to_dict(self) -> dict:
        return {
            "warnings": self.warnings,
            "drop_ids": self.drop_ids,
            "travel_buffer_mins": self.travel_buffer_mins,
        }


def plan_duration_mins(items: list[PlanItem]) -> int:
    activity = sum(item.duration_mins for item in items)
    travel = max(0, len(items) - 1) * TRAVEL_BUFFER_MINS
    return activity + travel


def validate_plan(items: list[PlanItem], prefs: Preferences, total_cost: int) -> ValidationResult:
    warnings: list[str] = []
    drop_ids: list[str] = []
    travel_buffer_mins = max(0, len(items) - 1) * TRAVEL_BUFFER_MINS

    time_budget_mins = prefs.available_time_hours * 60
    duration = plan_duration_mins(items)
    if duration > time_budget_mins:
        warnings.append(
            f"The first draft ran {int(duration)} min — {int(duration - time_budget_mins)} min over your "
            f"{prefs.available_time_hours:g}h window. Trimmed the least essential stop."
        )
        droppable = [item for item in reversed(items) if item.kind == "activity"]
        for item in droppable:
            if duration <= time_budget_mins:
                break
            drop_ids.append(item.id)
            duration -= item.duration_mins + TRAVEL_BUFFER_MINS

    if prefs.vegetarian:
        offenders = [i for i in items if i.kind == "food" and "vegetarian-friendly" not in i.tags]
        if offenders:
            warnings.append("A food stop isn't tagged vegetarian, so it was swapped out for a safer option.")
            drop_ids.extend(i.id for i in offenders)

    if prefs.avoid_crowded:
        busy = [i for i in items if "crowded" in i.tags]
        if busy:
            warnings.append(f"You asked to avoid crowds — flagged {', '.join(b.title for b in busy)} as likely busy.")

    if prefs.budget is not None and total_cost > prefs.budget:
        warnings.append("Estimated spend is over your budget — see the trade-offs below.")

    return ValidationResult(warnings=warnings, drop_ids=drop_ids, travel_buffer_mins=travel_buffer_mins)
