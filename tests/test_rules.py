from datetime import timedelta

import pytest

from edash.protocol import CalendarData, Event, MailData
from edash.rules import parse_condition
from edash.state import DashboardState


def state_with_meeting(now, starts_in: timedelta, minutes: int = 30) -> DashboardState:
    start = now + starts_in
    event = Event(subject="Sync", start=start, end=start + timedelta(minutes=minutes))
    return DashboardState(calendar=CalendarData(events=[event]))


def test_meeting_starts_in(now):
    rule = parse_condition("meeting_starts_in <= 5m")
    assert rule(state_with_meeting(now, timedelta(minutes=4)), now)
    assert not rule(state_with_meeting(now, timedelta(minutes=6)), now)
    assert not rule(DashboardState(), now)  # no meeting at all


def test_meeting_active_and_not(now):
    running = state_with_meeting(now, timedelta(minutes=-10))
    assert parse_condition("meeting_active")(running, now)
    assert not parse_condition("not meeting_active")(running, now)


def test_all_day_events_do_not_count_as_meetings(now):
    day = now.replace(hour=0, minute=0)
    state = DashboardState(calendar=CalendarData(events=[Event(subject="Holiday", start=day, end=day + timedelta(days=1), all_day=True)]))
    assert not parse_condition("meeting_active")(state, now)


def test_counts_time_weekday_and_combination(now):
    state = DashboardState(mail=MailData(unread_count=3))
    assert parse_condition("unread_mail > 2")(state, now)
    assert not parse_condition("unread_teams > 0")(state, now)
    assert parse_condition("time in 09:00-10:00")(state, now)
    assert parse_condition("weekday in mon-fri")(state, now)
    assert parse_condition("weekday in mon and time in 09:00-10:00 and unread_mail >= 3")(state, now)
    assert not parse_condition("weekday in sat,sun")(state, now)


@pytest.mark.parametrize("bad", ["", "foo", "unread_mail > lots", "time > 10:00", "location in office", "meeting_starts_in < soon"])
def test_invalid_conditions(bad):
    with pytest.raises(ValueError):
        parse_condition(bad)
