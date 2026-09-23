"""Shared data models.

These are plain dataclasses (not Pydantic) so the tool layer stays framework
agnostic and trivial to unit test. ``to_dict`` uses ``dataclasses.asdict`` which
recurses into nested dataclasses, giving us JSON-ready structures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

Interest = Literal[
    "food",
    "music",
    "walks",
    "art",
    "history",
    "nature",
    "shopping",
    "games",
    "coffee",
    "books",
    "nightlife",
    "wellness",
]

MoodTag = Literal[
    "relaxed",
    "energetic",
    "social",
    "cozy",
    "adventurous",
    "romantic",
    "creative",
    "playful",
]

Currency = Literal["INR", "USD"]
PlaceSource = Literal["osm", "mock"]
TraceStatus = Literal["running", "ok", "fallback", "error", "info"]
PlanItemKind = Literal["activity", "food", "walk", "break"]


@dataclass
class Preferences:
    raw: str = ""
    city: Optional[str] = None
    budget: Optional[int] = None
    currency: Currency = "INR"
    available_time_hours: float = 4.0
    mood: Optional[str] = None
    mood_tags: list[MoodTag] = field(default_factory=list)
    interests: list[Interest] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    vegetarian: bool = False
    avoid_crowded: bool = False
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlaceCandidate:
    id: str
    name: str
    category: str
    interests: list[Interest]
    source: PlaceSource
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None
    tags: dict[str, str] = field(default_factory=dict)
    score: float = 0.0
    crowd: Literal["low", "medium", "high"] = "low"
    vegetarian_friendly: bool = False
    note: Optional[str] = None
    est_cost: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlanItem:
    id: str
    kind: PlanItemKind
    title: str
    description: str
    location: str
    start_time: str
    duration_mins: int
    cost: int
    tags: list[str]
    why: str
    source: PlaceSource
    lat: Optional[float] = None
    lon: Optional[float] = None
    over_budget: bool = False
    note: Optional[str] = None
    travel_mins: int = 0
    distance_km: Optional[float] = None
    opening_hours: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    city: str
    headline: str
    summary: str
    items: list[PlanItem]
    total_cost: int
    currency: Currency
    total_duration_mins: int
    tradeoffs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    budget: Optional[int] = None
    within_budget: bool = True
    source: str = "mock"
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceStep:
    id: str
    tool: str
    status: TraceStatus
    message: str
    ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClarifyingQuestion:
    question: str
    field: Literal["city", "interests", "mood", "budget", "time"]
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
