"""Shared test setup.

We force offline mode so the suite is deterministic and never depends on the
OpenStreetMap services being up. ``PLANNER_OFFLINE=1`` makes the places tool use
the curated catalogue, which is exactly the graceful-degradation path we want to
exercise anyway.
"""

import os

os.environ["PLANNER_OFFLINE"] = "1"
os.environ.pop("OPENAI_API_KEY", None)

import pytest  # noqa: E402

from planner.data.mock_data import build_mock_activities, build_mock_food  # noqa: E402


@pytest.fixture
def bangalore_prefs():
    from planner.tools.parse import parse_user_preferences

    return parse_user_preferences(
        "I'm in Bangalore with about ₹2000 and 4 hours. Tired but want something fun. "
        "I like food, music and walks. I'm vegetarian and want to avoid crowded places."
    )


@pytest.fixture
def activities():
    return build_mock_activities("Bangalore")


@pytest.fixture
def foods():
    return build_mock_food("Bangalore")
