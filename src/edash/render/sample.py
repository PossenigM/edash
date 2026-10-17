"""Realistic fake data for previews and tests, relative to a given time."""

from __future__ import annotations

from datetime import datetime, timedelta

from edash.protocol import (
    DATA_TOPICS,
    CalendarData,
    ChatItem,
    Event,
    MailData,
    MailItem,
    TeamsData,
    WeatherData,
    WeatherDay,
)
from edash.state import Away, DashboardState
from edash.timeutil import start_of_day


def sample_state(now: datetime) -> DashboardState:
    base = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
    day0 = start_of_day(now)

    def at(minutes: int, duration: int, subject: str, **extra) -> Event:
        start = base + timedelta(minutes=minutes)
        return Event(subject=subject, start=start, end=start + timedelta(minutes=duration), **extra)

    events = [
        Event(subject="Release week", start=day0, end=day0 + timedelta(days=1), all_day=True),
        at(-75, 15, "Daily stand-up", online=True),
        at(-15, 45, "Design review: dashboard enclosure", location="Room 2.14"),
        at(45, 30, "1:1 with team lead", online=True),
        at(120, 60, "Sprint planning", location="Large conference room"),
        at(240, 30, "Supplier call: e-paper panels", online=True, tentative=True),
        at(24 * 60, 30, "Daily stand-up", online=True),
        at(24 * 60 + 90, 90, "Architecture workshop", location="Room 3.01"),
    ]
    mail = MailData(
        unread_count=7,
        items=[
            MailItem(sender="Facilities", subject="Office closed on Friday afternoon", received=now - timedelta(minutes=4)),
            MailItem(
                sender="Finance team",
                subject="Action required: approve Q4 hardware budget",
                received=now - timedelta(minutes=38),
                important=True,
            ),
            MailItem(sender="Build server", subject="Nightly build #1423 succeeded", received=now - timedelta(hours=2)),
            MailItem(sender="HR", subject="Reminder: submit your time sheet", received=now - timedelta(hours=5)),
            MailItem(sender="Newsletter", subject="This week in engineering", received=now - timedelta(days=1)),
        ],
    )
    teams = TeamsData(
        unread_count=2,
        items=[
            ChatItem(chat="Platform team", sender="Sam", preview="Deploy is done, can you check the logs?", at=now - timedelta(minutes=2)),
            ChatItem(chat="Alex", sender="Alex", preview="Lunch at 12:30?", at=now - timedelta(minutes=20)),
            ChatItem(
                chat="Hardware guild",
                sender="Robin",
                preview="Uploaded the new STL files for the bracket",
                at=now - timedelta(hours=3),
                unread=False,
            ),
        ],
    )
    codes = [2, 61, 3, 0, 80, 71, 95]
    weather = WeatherData(
        location="Munich",
        temperature=13.6,
        code=2,
        days=[
            WeatherDay(date=(day0 + timedelta(days=i)).date(), code=codes[i], temp_max=16 - i, temp_min=7 - i / 2, precip_prob=20 * (i % 4))
            for i in range(7)
        ],
    )
    return DashboardState(
        mail=mail,
        calendar=CalendarData(events=events),
        teams=teams,
        weather=weather,
        fetched={topic: now for topic in DATA_TOPICS},
        fresh_until={topic: now + timedelta(minutes=10) for topic in DATA_TOPICS},
        host_connected=True,
        # Only the away screen reads this; it shows what the screen looks like after a lock.
        away=Away(reason="locked", since=now - timedelta(minutes=25)),
    )
