from datetime import time, timedelta

import pytest

from edash.timeutil import TimeRange, format_duration, format_weekdays, parse_duration, parse_weekdays


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30s", timedelta(seconds=30)),
        ("45m", timedelta(minutes=45)),
        ("1h30m", timedelta(minutes=90)),
        ("2d", timedelta(days=2)),
        (90, timedelta(seconds=90)),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("bad", ["", "10", "5 minutes", "-5m", -1, True, None])
def test_parse_duration_rejects(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_time_range_normal_and_wrapping():
    day = TimeRange.parse("08:00-17:00")
    assert time(8, 0) in day and time(16, 59) in day
    assert time(17, 0) not in day and time(7, 59) not in day

    night = TimeRange.parse("22:00-06:00")
    assert time(23, 0) in night and time(5, 0) in night
    assert time(12, 0) not in night


def test_weekdays():
    assert parse_weekdays("mon-fri") == frozenset(range(5))
    assert parse_weekdays("sat,sun") == frozenset({5, 6})
    assert parse_weekdays(["fri-mon"]) == frozenset({4, 5, 6, 0})
    with pytest.raises(ValueError):
        parse_weekdays("monday")


@pytest.mark.parametrize("text", ["30s", "45m", "1h30m", "2d", "1d2h"])
def test_format_duration_round_trips(text):
    assert format_duration(parse_duration(text)) == text


def test_format_weekdays():
    assert format_weekdays(frozenset(range(5))) == "mon-fri"
    assert format_weekdays(frozenset({5, 6})) == "sat,sun"
    assert format_weekdays(frozenset({0, 2, 3, 4, 6})) == "mon,wed-fri,sun"
