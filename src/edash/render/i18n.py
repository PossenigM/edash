"""Display language: day/month names and widget texts, built in so the Pi's system locale does not matter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Language = Literal["en", "de"]

_NAME_RE = re.compile(r"%(.)")


@dataclass(frozen=True)
class Locale:
    days: tuple[str, ...]
    days_short: tuple[str, ...]
    months: tuple[str, ...]
    months_short: tuple[str, ...]
    strings: dict[str, str] = field(default_factory=dict)

    def t(self, key: str, **values: object) -> str:
        return self.strings[key].format(**values)

    def plural(self, key: str, n: int) -> str:
        return self.t(f"{key}.{'one' if n == 1 else 'other'}", n=n)

    def strftime(self, dt: datetime, fmt: str) -> str:
        """strftime with %A %a %B %b taken from this locale instead of the C library."""

        def name(m: re.Match[str]) -> str:
            code = m.group(1)
            if code == "A":
                return self.days[dt.weekday()]
            if code == "a":
                return self.days_short[dt.weekday()]
            if code == "B":
                return self.months[dt.month - 1]
            if code == "b":
                return self.months_short[dt.month - 1]
            return m.group(0)  # incl. "%%", left for strftime

        return dt.strftime(_NAME_RE.sub(name, fmt))

    def when(self, dt: datetime, now: datetime) -> str:
        """``14:05`` today, ``Tue 09:00`` on other days."""
        local = dt.astimezone(now.tzinfo)
        return f"{local:%H:%M}" if local.date() == now.date() else self.strftime(local, "%a %H:%M")


EN = Locale(
    days=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    days_short=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    months=(
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    months_short=("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    strings={
        "date_long": "%A, %d %B",
        "date_short": "%d %b",
        "day_header": "%A, %d %b",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "yesterday": "yesterday",
        "waiting_mail": "Waiting for mail…",
        "waiting_calendar": "Waiting for calendar…",
        "waiting_teams": "Waiting for Teams…",
        "waiting_weather": "Waiting for weather…",
        "unread": "{n} unread",
        "unread_chats.one": "{n} unread chat",
        "unread_chats.other": "{n} unread chats",
        "inbox_zero": "Inbox zero",
        "no_messages": "No new messages",
        "more": "+{n} more",
        "no_more_meetings": "No more meetings today",
        "no_meetings": "No meetings",
        "no_upcoming": "No upcoming meetings",
        "all_day": "all day",
        "until": "until {t}",
        "online": "Online",
        "online_meeting": "Online meeting",
        "tentative": "tentative",
        "now_until": "NOW · until {t}",
        "in_minutes": "IN {n} MIN",
        "at": "AT {t}",
        "next_at": "next {t}",
        "next_meeting": "Next: {subject} · {t}",
        "away": "Away",
        "away.locked": "Laptop locked since {t}",
        "away.sleep": "Laptop asleep since {t}",
        "away.shutdown": "Laptop shut down at {t}",
        "away.stopped": "eDash host stopped at {t}",
        "connected": "Laptop connected",
        "not_connected": "Laptop not connected",
        "updated": "updated {t}",
        "as_of": "as of {t}",
    },
)

DE = Locale(
    days=("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    days_short=("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    months=(
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
    months_short=("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"),
    strings={
        "date_long": "%A, %d. %B",
        "date_short": "%d.%m.",
        "day_header": "%A, %d.%m.",
        "today": "Heute",
        "tomorrow": "Morgen",
        "yesterday": "gestern",
        "waiting_mail": "Warte auf E-Mails…",
        "waiting_calendar": "Warte auf den Kalender…",
        "waiting_teams": "Warte auf Teams…",
        "waiting_weather": "Warte auf das Wetter…",
        "unread": "{n} ungelesen",
        "unread_chats.one": "{n} ungelesener Chat",
        "unread_chats.other": "{n} ungelesene Chats",
        "inbox_zero": "Keine ungelesenen E-Mails",
        "no_messages": "Keine neuen Nachrichten",
        "more": "+{n} weitere",
        "no_more_meetings": "Heute keine Termine mehr",
        "no_meetings": "Keine Termine",
        "no_upcoming": "Keine anstehenden Termine",
        "all_day": "ganztägig",
        "until": "bis {t}",
        "online": "Online",
        "online_meeting": "Online-Meeting",
        "tentative": "vorläufig",
        "now_until": "JETZT · bis {t}",
        "in_minutes": "IN {n} MIN",
        "at": "UM {t}",
        "next_at": "nächste: {t}",
        "next_meeting": "Nächster Termin: {subject} · {t}",
        "away": "Abwesend",
        "away.locked": "Laptop gesperrt seit {t}",
        "away.sleep": "Laptop im Ruhezustand seit {t}",
        "away.shutdown": "Laptop um {t} heruntergefahren",
        "away.stopped": "eDash-Host um {t} beendet",
        "connected": "Laptop verbunden",
        "not_connected": "Laptop nicht verbunden",
        "updated": "aktualisiert {t}",
        "as_of": "Stand {t}",
    },
)

LOCALES: dict[str, Locale] = {"en": EN, "de": DE}


def get_locale(language: str) -> Locale:
    return LOCALES[language]
