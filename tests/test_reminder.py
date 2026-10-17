from datetime import datetime, timedelta

from edash.render.widgets.reminder import ReminderOptions, reminder_status
from tests.conftest import CEST


def at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=CEST)  # 19 = Monday


def options(**overrides) -> ReminderOptions:
    return ReminderOptions.model_validate({"label": "Drink", "every": "45m", "active": "08:00-17:00", **overrides})


def test_schedule_starts_one_interval_after_window_start():
    status = reminder_status(options(), at(19, 8, 10))
    assert not status.due
    assert status.next_due == at(19, 8, 45)
    assert status.next_change == at(19, 8, 45)


def test_due_with_highlight_window():
    status = reminder_status(options(), at(19, 8, 50))
    assert status.due
    assert status.next_change == at(19, 8, 55)  # highlight ends
    assert status.next_due == at(19, 9, 30)

    assert not reminder_status(options(), at(19, 8, 56)).due


def test_no_reminder_at_or_after_window_end():
    # 08:00 + k*45m: ..., 16:15, 17:00 (= end, excluded)
    status = reminder_status(options(), at(19, 16, 30))
    assert status.next_due == at(20, 8, 45)


def test_weekend_is_skipped():
    status = reminder_status(options(), at(23, 18, 0))  # Friday evening
    assert status.next_due == at(26, 8, 45)  # Monday
    assert not reminder_status(options(), at(24, 10, 0)).due


def test_window_across_midnight():
    o = options(active="22:00-02:00", every="1h", days="mon-sun")
    status = reminder_status(o, at(20, 1, 5))
    assert status.due  # 01:00 reminder from Monday's window
    assert status.next_due == at(20, 22, 0) + timedelta(hours=1)
