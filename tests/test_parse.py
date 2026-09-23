from planner.tools.parse import (
    detect_clarifications,
    parse_structured,
    parse_user_preferences,
)


def test_parses_the_assignment_example():
    prefs = parse_user_preferences(
        "I'm in Bangalore with about ₹2000 and 4 hours. Tired but want something fun. "
        "I like food, music and walks. I'm vegetarian and want to avoid crowded places."
    )
    assert prefs.city == "Bangalore"
    assert prefs.budget == 2000
    assert prefs.available_time_hours == 4
    assert {"food", "music", "walks"} <= set(prefs.interests)
    assert prefs.vegetarian is True
    assert prefs.avoid_crowded is True
    assert "relaxed" in prefs.mood_tags


def test_parses_plurals_and_punctuation():
    prefs = parse_user_preferences("walks, books and coffees please")
    assert "walks" in prefs.interests
    assert "books" in prefs.interests
    assert "coffee" in prefs.interests


def test_parses_structured_payload():
    prefs = parse_structured(
        {
            "city": "Bangalore",
            "budget": 2000,
            "available_time": "4 hours",
            "mood": "tired but wants to do something fun",
            "interests": ["food", "music", "walks"],
            "constraints": ["vegetarian", "avoid crowded places"],
        }
    )
    assert prefs.city == "Bangalore"
    assert prefs.budget == 2000
    assert prefs.available_time_hours == 4
    assert prefs.interests == ["food", "music", "walks"]
    assert prefs.vegetarian is True
    assert prefs.avoid_crowded is True


def test_structured_normalises_city_alias_and_currency():
    prefs = parse_structured({"city": "bengaluru", "budget": 50})
    assert prefs.city == "Bangalore"
    assert prefs.currency == "INR"

    nyc = parse_structured({"city": "NYC", "budget": 50})
    assert nyc.city == "New York"
    assert nyc.currency == "USD"


def test_missing_fields_become_documented_assumptions():
    prefs = parse_user_preferences("Bangalore")
    assert prefs.city == "Bangalore"
    assert prefs.budget is None
    assert prefs.assumptions


def test_clarifying_questions_for_vague_input():
    prefs = parse_user_preferences("I want to do something")
    questions = detect_clarifications(prefs)
    assert questions
    assert len(questions) <= 2
    assert any(q.field == "city" for q in questions)


def test_no_questions_when_input_is_specific():
    prefs = parse_user_preferences("Bangalore, ₹2000, 4 hours, food and music, relaxed")
    assert detect_clarifications(prefs) == []


def test_usd_budget_detection():
    prefs = parse_user_preferences("New York, $60, 5 hours, energetic, art and coffee")
    assert prefs.currency == "USD"
    assert prefs.budget == 60
