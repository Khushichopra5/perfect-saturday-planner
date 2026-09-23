from planner.tools.hours import opening_status

SATURDAY = 5
SUNDAY = 6


def test_24_7_is_always_open():
    assert opening_status("24/7", SATURDAY, 600) == "open"


def test_weekday_only_is_closed_on_saturday():
    assert opening_status("Mo-Fr 09:00-18:00", SATURDAY, 600) == "closed"


def test_including_saturday_is_open():
    assert opening_status("Mo-Sa 09:00-18:00", SATURDAY, 600) == "open"


def test_outside_hours_is_closed():
    assert opening_status("Sa 10:00-14:00", SATURDAY, 9 * 60) == "closed"
    assert opening_status("Sa 10:00-14:00", SATURDAY, 11 * 60) == "open"


def test_explicit_off_day():
    assert opening_status("Su off", SUNDAY, 600) == "closed"
    assert opening_status("Mo-Fr 09:00-17:00; Sa off", SATURDAY, 600) == "closed"


def test_missing_hours_is_unknown():
    assert opening_status(None, SATURDAY, 600) == "unknown"
    assert opening_status("", SATURDAY, 600) == "unknown"


def test_unparseable_solar_times_are_unknown():
    assert opening_status("sunrise-sunset", SATURDAY, 600) == "unknown"
