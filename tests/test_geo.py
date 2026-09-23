from planner.models import PlaceCandidate
from planner.tools.geo import haversine_km, nearest_neighbour_order, travel_minutes


def test_haversine_known_distance():
    # Bangalore → Chennai is roughly 290 km as the crow flies.
    distance = haversine_km(12.9716, 77.5946, 13.0827, 80.2707)
    assert 250 < distance < 320


def test_haversine_zero_for_same_point():
    assert haversine_km(1.0, 2.0, 1.0, 2.0) == 0


def test_travel_time_grows_with_distance():
    assert travel_minutes(0.5) >= 5
    assert travel_minutes(10) > travel_minutes(2)


def test_nearest_neighbour_visits_closest_first():
    near = PlaceCandidate(id="n", name="Near", category="park", interests=["walks"], source="osm", lat=0.01, lon=0.01)
    far = PlaceCandidate(id="f", name="Far", category="park", interests=["walks"], source="osm", lat=1.0, lon=1.0)
    ordered = nearest_neighbour_order([(far, "activity"), (near, "activity")], (0.0, 0.0))
    assert ordered[0][0].id == "n"
    assert ordered[1][0].id == "f"


def test_nearest_neighbour_falls_back_without_coordinates():
    a = PlaceCandidate(id="a", name="A", category="park", interests=["walks"], source="mock")
    b = PlaceCandidate(id="b", name="B", category="cafe", interests=["food"], source="mock")
    sequence = [(a, "activity"), (b, "food")]
    assert nearest_neighbour_order(sequence, (0.0, 0.0)) == sequence
